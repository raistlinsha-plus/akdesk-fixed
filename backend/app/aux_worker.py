from __future__ import annotations

import json
import math
import re
import sys
from typing import Any

import pandas as pd


AUX_RESULT_MARKER = "__AKDESK_AUX_RESULT__="


def _number(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, str):
        value = value.replace(",", "").replace("%", "").strip()
        if value in {"", "-", "--", "—"}:
            return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _pick(row: pd.Series, *candidates: str, default: Any = None) -> Any:
    for candidate in candidates:
        if candidate in row and not pd.isna(row[candidate]):
            return row[candidate]
    return default


def _rate_row(
    frame: pd.DataFrame,
    *,
    field: str,
    name: str,
    tenor: str,
    date_fields: tuple[str, ...],
) -> tuple[dict[str, Any] | None, str | None]:
    if frame.empty:
        return None, None
    current = frame.iloc[-1]
    previous = frame.iloc[-2] if len(frame) > 1 else None
    value = _number(_pick(current, field))
    old = _number(_pick(previous, field)) if previous is not None else None
    if value is None:
        return None, None
    observation = str(_pick(current, *date_fields, default="")) or None
    return {
        "name": name,
        "tenor": tenor,
        "value": value,
        "change_bp": round((value - old) * 100, 3) if old is not None else None,
    }, observation


def money_extensions() -> dict[str, Any]:
    import akshare as ak

    rows: list[dict[str, Any]] = []
    observations: list[str] = []
    missing: list[str] = []
    calls = (
        (
            "FR",
            lambda: ak.repo_rate_query(symbol="回购定盘利率"),
            (("FR007", "FR007", "7D", ("date", "日期")),),
        ),
        (
            "FDR",
            lambda: ak.repo_rate_query(symbol="银银间回购定盘利率"),
            (("FDR007", "FDR007", "7D", ("date", "日期")),),
        ),
        (
            "LPR",
            ak.macro_china_lpr,
            (
                ("LPR1Y", "LPR 1Y", "1Y", ("TRADE_DATE", "日期")),
                ("LPR5Y", "LPR 5Y", "5Y", ("TRADE_DATE", "日期")),
            ),
        ),
    )
    for group, call, fields in calls:
        try:
            frame = call()
            before = len(rows)
            for field, name, tenor, date_fields in fields:
                row, observed = _rate_row(
                    frame,
                    field=field,
                    name=name,
                    tenor=tenor,
                    date_fields=date_fields,
                )
                if row:
                    rows.append(row)
                if observed:
                    observations.append(observed)
            if len(rows) == before:
                missing.append(group)
        except Exception:
            missing.append(group)
    return {
        "rows": rows,
        "observations": observations,
        "missing": missing,
    }


def convertibles_comparison() -> dict[str, Any]:
    import akshare as ak

    frame = ak.bond_cov_comparison()
    if frame.empty:
        raise ValueError("可转债比价为空")
    rows: list[dict[str, Any]] = []
    for _, row in frame.head(500).iterrows():
        price = _number(_pick(row, "转债最新价", "现价"))
        premium = _number(_pick(row, "转股溢价率"))
        rows.append(
            {
                "code": str(_pick(row, "转债代码", "代码", default="")),
                "name": str(_pick(row, "转债名称", "名称", default="")),
                "price": price,
                "change_pct": _number(_pick(row, "转债涨跌幅", "涨跌幅")),
                "stock_name": str(_pick(row, "正股名称", default="")),
                "convert_value": _number(_pick(row, "转股价值")),
                "premium_pct": premium,
                "double_low": (
                    round(price + premium, 3)
                    if price is not None and premium is not None
                    else None
                ),
                "ytm_pct": _number(_pick(row, "到期税前收益", "到期收益率")),
                "redeem_status": str(_pick(row, "强赎状态", default="数据未接入")),
                "data_tier": "comparison",
            }
        )
    return {"rows": rows, "observation_time": None, "fallback": False}


def convertibles_spot() -> dict[str, Any]:
    import akshare as ak

    frame = ak.bond_zh_hs_cov_spot()
    if frame.empty:
        raise ValueError("可转债备用行情为空")
    rows: list[dict[str, Any]] = []
    rejected = 0
    for _, row in frame.head(500).iterrows():
        code = str(_pick(row, "code", "代码", default="")).strip()
        name = str(_pick(row, "name", "名称", default="")).strip()
        price = _number(_pick(row, "trade", "最新价", "现价"))
        valid_code = bool(
            re.fullmatch(r"(?:110|111|113|118|123|127|128)\d{3}", code)
        )
        if (
            not valid_code
            or not name
            or "退市" in name
            or name.endswith("退")
            or price is None
            or price <= 0
            or price > 500
        ):
            rejected += 1
            continue
        rows.append(
            {
                "code": code,
                "name": name,
                "price": price,
                "change_pct": _number(_pick(row, "changepercent", "涨跌幅")),
                "stock_name": "",
                "convert_value": None,
                "premium_pct": None,
                "double_low": None,
                "ytm_pct": None,
                "redeem_status": "备用行情未提供",
                "data_tier": "price_only",
            }
        )
    if not rows:
        raise ValueError("可转债备用行情没有通过可信校验的记录")
    # This endpoint exposes a time-of-day but no trustworthy trading date.
    # Never combine it with the local date: weekends and stale snapshots would
    # otherwise be misrepresented as today's market observation.
    return {
        "rows": rows,
        "observation_time": None,
        "fallback": True,
        "rejected_rows": rejected,
    }


TASKS = {
    "money_extensions": money_extensions,
    "convertibles_comparison": convertibles_comparison,
    "convertibles_spot": convertibles_spot,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in TASKS:
        raise SystemExit("usage: python -m app.aux_worker <task>")
    try:
        payload = {"ok": True, "result": TASKS[sys.argv[1]]()}
    except Exception as exc:
        payload = {"ok": False, "error": f"{type(exc).__name__}: {exc}"[:500]}
    print(AUX_RESULT_MARKER + json.dumps(payload, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
