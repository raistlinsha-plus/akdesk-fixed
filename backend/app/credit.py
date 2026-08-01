from __future__ import annotations

import re
import hashlib
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from .models import CreditObservationCreate, CreditObservationItem, Dataset
from .provider import DataService

if TYPE_CHECKING:
    from .database import Database


TENOR_YEARS = {"1Y": 1.0, "3Y": 3.0, "5Y": 5.0, "7Y": 7.0, "10Y": 10.0}
RATING_PATTERN = re.compile(r"^(?:AAA|AA\+|AA|AA-|A\+|A|A-|BBB\+|BBB|BBB-)$")


def normalize_issuer(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("（", "(").replace("）", ")")


def evaluate_credit_observation(item: CreditObservationItem) -> dict[str, Any]:
    missing: list[str] = []
    reasons: list[str] = []
    required = {
        "bond_code": item.bond_code,
        "issuer": item.issuer,
        "maturity_date": item.maturity_date,
        "rating": item.rating,
        "rating_date": item.rating_date,
        "yield_pct": item.yield_pct,
        "yield_observation_date": item.yield_observation_date,
        "benchmark_tenor": item.benchmark_tenor,
        "benchmark_yield_pct": item.benchmark_yield_pct,
        "benchmark_observation_date": item.benchmark_observation_date,
        "source_note": item.source_note,
    }
    for field, value in required.items():
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)

    remaining_years: float | None = None
    if item.rating and not RATING_PATTERN.fullmatch(item.rating.strip().upper()):
        reasons.append("评级等级不在 R1 支持范围")
    try:
        yield_date = (
            date.fromisoformat(item.yield_observation_date)
            if item.yield_observation_date
            else None
        )
        maturity = date.fromisoformat(item.maturity_date) if item.maturity_date else None
        rating_date = date.fromisoformat(item.rating_date) if item.rating_date else None
        benchmark_date = (
            date.fromisoformat(item.benchmark_observation_date)
            if item.benchmark_observation_date
            else None
        )
    except ValueError:
        yield_date = maturity = rating_date = benchmark_date = None
        reasons.append("日期格式无效")

    if yield_date and maturity:
        remaining_years = round((maturity - yield_date).days / 365.25, 3)
        if remaining_years <= 0:
            reasons.append("债券在收益率观察日已到期")
    if yield_date and rating_date and rating_date > yield_date:
        reasons.append("评级日期晚于收益率观察日")
    if yield_date and benchmark_date and benchmark_date != yield_date:
        reasons.append("债券收益率与基准曲线不是同一观察日")
    if remaining_years is not None and item.benchmark_tenor:
        target = TENOR_YEARS[item.benchmark_tenor]
        tolerance = max(0.75, target * 0.25)
        if abs(remaining_years - target) > tolerance:
            reasons.append("剩余期限与所选基准期限不匹配")

    eligible = not missing and not reasons
    spread_bp = (
        round((float(item.yield_pct) - float(item.benchmark_yield_pct)) * 100, 3)
        if eligible
        and item.yield_pct is not None
        and item.benchmark_yield_pct is not None
        else None
    )
    return {
        **item.model_dump(mode="json"),
        "normalized_issuer": item.canonical_issuer.strip()
        or normalize_issuer(item.issuer),
        "remaining_years": remaining_years,
        "eligible": eligible,
        "spread_bp": spread_bp,
        "missing_fields": missing,
        "gate_reasons": reasons,
        "calculation_notice": (
            "仅为同日债券收益率减同期限国债基准的机械试算；不构成评级或违约概率。"
            if eligible
            else "覆盖门槛未通过，不计算信用利差。"
        ),
    }


def credit_coverage(items: list[CreditObservationItem]) -> dict[str, Any]:
    evaluated = [evaluate_credit_observation(item) for item in items]
    fields = [
        "issuer",
        "maturity_date",
        "rating",
        "rating_date",
        "yield_pct",
        "yield_observation_date",
        "benchmark_tenor",
        "benchmark_yield_pct",
        "benchmark_observation_date",
        "source_note",
    ]
    total = len(evaluated)
    field_coverage = {
        field: {
            "covered": sum(field not in item["missing_fields"] for item in evaluated),
            "total": total,
            "ratio": (
                round(sum(field not in item["missing_fields"] for item in evaluated) / total, 4)
                if total
                else 0.0
            ),
        }
        for field in fields
    }
    eligible = sum(bool(item["eligible"]) for item in evaluated)
    return {
        "total": total,
        "eligible": eligible,
        "blocked": total - eligible,
        "eligible_ratio": round(eligible / total, 4) if total else 0.0,
        "field_coverage": field_coverage,
        "items": evaluated,
        "policy": "代码、主体、到期日、评级及日期、收益率及日期、基准及日期和来源任一缺失时不计算。",
    }


def _safe_date(value: object) -> date | None:
    try:
        return date.fromisoformat(str(value)) if value else None
    except ValueError:
        return None


def _signal_id(*parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    return hashlib.sha1(payload.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _history_evaluation(row: dict[str, Any]) -> dict[str, Any]:
    item = CreditObservationCreate(
        **{
            field: row.get(field)
            for field in CreditObservationCreate.model_fields
            if field in row
        }
    )
    evaluated = evaluate_credit_observation(item)
    return {
        **evaluated,
        "history_id": row.get("id"),
        "observation_id": row.get("observation_id"),
        "recorded_at": row.get("recorded_at"),
    }


def _spread_series(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_date: dict[str, dict[str, Any]] = {}
    for row in sorted(history, key=lambda item: str(item.get("recorded_at") or "")):
        if not row.get("eligible") or not row.get("yield_observation_date"):
            continue
        latest_by_date[str(row["yield_observation_date"])] = row
    return [latest_by_date[key] for key in sorted(latest_by_date)]


def _spread_percentile(series: list[dict[str, Any]]) -> float | None:
    values = [float(row["spread_bp"]) for row in series if row.get("spread_bp") is not None]
    if not values:
        return None
    current = values[-1]
    return round(sum(value <= current for value in values) / len(values) * 100, 1)


def credit_workspace(database: "Database", as_of: date | None = None) -> dict[str, Any]:
    today = as_of or datetime.now(ZoneInfo("Asia/Shanghai")).date()
    observations = database.list_credit_observations()
    coverage = credit_coverage(observations)
    raw_history = database.list_credit_history()
    history_map: dict[int, list[dict[str, Any]]] = {}
    for row in raw_history:
        evaluated = _history_evaluation(row)
        history_map.setdefault(int(row["observation_id"]), []).append(evaluated)

    confirmations = database.list_credit_signal_confirmations()
    signals: list[dict[str, Any]] = []
    calendar: list[dict[str, Any]] = []
    enriched_items: list[dict[str, Any]] = []

    def add_signal(
        item: dict[str, Any], kind: str, level: str, title: str, detail: str, key: object
    ) -> None:
        signal_id = _signal_id(kind, item["id"], key)
        source_note = str(item.get("source_note") or "")
        signals.append(
            {
                "id": signal_id,
                "kind": kind,
                "level": level,
                "title": title,
                "detail": detail,
                "bond_code": item["bond_code"],
                "bond_name": item["bond_name"],
                "issuer": item["normalized_issuer"],
                "observation_date": item.get("yield_observation_date"),
                "source_note": source_note,
                "quality_state": "confirmed_input" if source_note else "missing_source",
                "requires_manual_confirmation": True,
                "confirmation": confirmations.get(signal_id),
            }
        )

    for item in coverage["items"]:
        history = sorted(
            history_map.get(int(item["id"]), []),
            key=lambda row: (
                str(row.get("yield_observation_date") or ""),
                str(row.get("recorded_at") or ""),
            ),
        )
        series = _spread_series(history)
        spread_change = None
        if len(series) >= 2:
            spread_change = round(
                float(series[-1]["spread_bp"]) - float(series[-2]["spread_bp"]), 3
            )
            if abs(spread_change) >= 20 and item.get("watch_status") != "archived":
                direction = "走阔" if spread_change > 0 else "收窄"
                add_signal(
                    item,
                    "spread_move",
                    "high" if abs(spread_change) >= 40 else "watch",
                    f"{item['bond_name']} 利差{direction}",
                    f"相邻可信观察变化 {spread_change:+.2f} BP；仅为机械变化提示。",
                    series[-1].get("yield_observation_date"),
                )

        rating_date = _safe_date(item.get("rating_date"))
        if (
            item.get("watch_status") != "archived"
            and rating_date
            and rating_date + timedelta(days=365) <= today
        ):
            due = rating_date + timedelta(days=365)
            add_signal(
                item,
                "rating_review",
                "watch",
                f"{item['bond_name']} 评级资料待复核",
                f"当前评级日期为 {rating_date.isoformat()}；系统不判断评级是否仍然有效。",
                due,
            )
            calendar.append(
                {
                    "date": due.isoformat(),
                    "kind": "rating_review",
                    "title": f"{item['bond_name']} 评级资料复核",
                    "bond_code": item["bond_code"],
                    "issuer": item["normalized_issuer"],
                    "overdue": due < today,
                }
            )

        for field, kind, label in (
            ("put_date", "put", "回售日"),
            ("maturity_date", "maturity", "到期日"),
            ("next_review_date", "review", "复盘日"),
        ):
            if item.get("watch_status") == "archived":
                break
            event_date = _safe_date(item.get(field))
            if not event_date:
                continue
            days = (event_date - today).days
            calendar.append(
                {
                    "date": event_date.isoformat(),
                    "kind": kind,
                    "title": f"{item['bond_name']} {label}",
                    "bond_code": item["bond_code"],
                    "issuer": item["normalized_issuer"],
                    "overdue": days < 0,
                }
            )
            horizon = 180 if kind in {"put", "maturity"} else 30
            if days <= horizon:
                level = "high" if days < 0 or (kind in {"put", "maturity"} and days <= 30) else "watch"
                timing = f"已逾期 {abs(days)} 天" if days < 0 else f"还有 {days} 天"
                add_signal(
                    item,
                    f"{kind}_due",
                    level,
                    f"{item['bond_name']} {label}{'已到期' if days < 0 else '临近'}",
                    f"{label} {event_date.isoformat()}，{timing}。",
                    event_date,
                )

        enriched_items.append(
            {
                **item,
                "history": history[-50:],
                "history_points": len(series),
                "spread_change_bp": spread_change,
                "spread_percentile": _spread_percentile(series),
            }
        )

    item_by_id = {int(item["id"]): item for item in enriched_items}
    issuer_map: dict[str, list[dict[str, Any]]] = {}
    for item in enriched_items:
        issuer_map.setdefault(item["normalized_issuer"] or "主体待补", []).append(item)
    issuers = []
    for issuer, items in issuer_map.items():
        spreads = [float(item["spread_bp"]) for item in items if item.get("spread_bp") is not None]
        events = [
            event for event in calendar if event["issuer"] == issuer and event["date"] >= today.isoformat()
        ]
        issuers.append(
            {
                "issuer": issuer,
                "bond_count": len(items),
                "eligible_count": sum(bool(item["eligible"]) for item in items),
                "ratings": sorted({str(item["rating"]) for item in items if item.get("rating")}),
                "spread_range_bp": (
                    {
                        "minimum": round(min(spreads), 2),
                        "maximum": round(max(spreads), 2),
                        "count": len(spreads),
                    }
                    if spreads
                    else None
                ),
                "next_event": min(events, key=lambda event: event["date"]) if events else None,
                "sector": next((item["sector"] for item in items if item.get("sector")), ""),
                "region": next((item["region"] for item in items if item.get("region")), ""),
                "issuer_type": next((item["issuer_type"] for item in items if item.get("issuer_type")), ""),
                "observation_ids": [item["id"] for item in items],
            }
        )

    portfolios = []
    for portfolio in database.list_credit_portfolios():
        members = [
            item_by_id[item_id]
            for item_id in portfolio["observation_ids"]
            if item_id in item_by_id
        ]
        spreads = [float(item["spread_bp"]) for item in members if item.get("spread_bp") is not None]
        portfolios.append(
            {
                **portfolio,
                "members": members,
                "eligible_count": sum(bool(item["eligible"]) for item in members),
                "spread_range_bp": (
                    {
                        "minimum": round(min(spreads), 2),
                        "maximum": round(max(spreads), 2),
                        "count": len(spreads),
                    }
                    if spreads
                    else None
                ),
                "issuer_count": len({item["normalized_issuer"] for item in members}),
            }
        )

    signals.sort(key=lambda item: (item["confirmation"] is not None, item["level"] != "high", item["title"]))
    calendar.sort(key=lambda item: (item["date"], item["title"]))
    return {
        **coverage,
        "items": enriched_items,
        "issuers": sorted(issuers, key=lambda item: (-item["bond_count"], item["issuer"])),
        "portfolios": portfolios,
        "signals": signals,
        "calendar": calendar,
        "summary": {
            "issuers": len(issuers),
            "portfolios": len(portfolios),
            "history_points": sum(item["history_points"] for item in enriched_items),
            "unconfirmed_signals": sum(signal["confirmation"] is None for signal in signals),
        },
        "as_of": today.isoformat(),
        "r2_policy": "自动信号只基于用户核验字段和同日机械利差，不生成评级、违约概率或投资结论；信号须人工确认。",
    }


def _trusted_candidate_dataset(
    service: DataService, adapter: str
) -> tuple[Dataset | None, dict[str, Any]]:
    cached = service._cached_dataset(adapter, allow_stale=True)
    if not isinstance(cached, Dataset):
        return None, {
            "eligible": False,
            "source": None,
            "observation_time": None,
            "data_state": "unavailable",
            "trust_level": "unavailable",
            "quality_score": 0,
            "gate_reasons": ["本地暂无可验证缓存"],
        }

    dataset = service._decorate_dataset(
        adapter,
        cached,
        cache_age_seconds=service.cache.age_seconds(adapter),
        from_cache=True,
    )
    reasons: list[str] = []
    if dataset.meta.demo:
        reasons.append("演示数据不可用于信用试算")
    if dataset.meta.stale or dataset.meta.data_state == "stale":
        reasons.append("缓存已过期")
    if dataset.meta.trust_level != "trusted":
        reasons.append(f"数据可信等级为 {dataset.meta.trust_level}")
    if dataset.meta.quality_score < 80:
        reasons.append(f"数据质量分仅 {dataset.meta.quality_score}")
    if not dataset.meta.observation_time:
        reasons.append("缺少观察日期")
    status = {
        "eligible": not reasons,
        "source": dataset.meta.source,
        "observation_time": dataset.meta.observation_time,
        "data_state": dataset.meta.data_state,
        "trust_level": dataset.meta.trust_level,
        "quality_score": dataset.meta.quality_score,
        "gate_reasons": list(dict.fromkeys(reasons)),
    }
    return (dataset if not reasons else None), status


def credit_candidates(service: DataService) -> dict[str, Any]:
    bonds, bond_status = _trusted_candidate_dataset(service, "spot_bonds")
    curves, curve_status = _trusted_candidate_dataset(service, "yield_curves")
    curve_values: dict[str, float] = {}
    curve_date: str | None = None
    if isinstance(curves, Dataset) and isinstance(curves.data, dict):
        tenors = curves.data.get("tenors", [])
        latest = next(
            (
                row
                for row in curves.data.get("series", [])
                if isinstance(row, dict)
                and "国债" in str(row.get("name", ""))
                and "最新" in str(row.get("name", ""))
            ),
            None,
        )
        if latest:
            for tenor, value in zip(tenors, latest.get("values", [])):
                if tenor in TENOR_YEARS and value is not None:
                    curve_values[str(tenor)] = float(value)
        curve_date = curves.meta.observation_time

    rows: list[dict[str, Any]] = []
    if isinstance(bonds, Dataset) and isinstance(bonds.data, list):
        for item in bonds.data:
            if not isinstance(item, dict):
                continue
            code = str(item.get("code") or "").strip()
            if (
                not code
                or item.get("quality_state") == "suspicious"
                or item.get("yield") is None
            ):
                continue
            rows.append(
                {
                    "bond_code": code,
                    "bond_name": str(item.get("name") or code),
                    "yield_pct": item.get("yield"),
                    "yield_observation_date": bonds.meta.observation_time,
                    "source": bonds.meta.source,
                }
            )
    return {
        "candidates": rows[:200],
        "benchmark_curve": {
            "observation_date": curve_date,
            "values": curve_values,
            "source": curves.meta.source if isinstance(curves, Dataset) else None,
            **curve_status,
        },
        "candidate_source": bond_status,
        "notice": (
            "自动候选仅来自未过期、非演示且可信等级为 trusted 的本地缓存；"
            "主体、评级和到期日仍需校验后补充。"
        ),
    }
