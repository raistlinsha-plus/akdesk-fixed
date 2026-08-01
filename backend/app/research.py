from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from .database import Database
from .models import Dataset, ResearchSignalSettings
from .provider import DataService


REPORT_SOURCE_WEIGHTS = {
    "money_rates": 15,
    "yield_curves": 25,
    "spot_bonds": 25,
    "treasury_futures": 25,
    "issuance_events": 10,
}
STATE_FACTORS = {
    "healthy": 1.0,
    "cached": 0.75,
    "degraded": 0.35,
    "unavailable": 0.0,
    "not_checked": 0.0,
}
TRUST_FACTORS = {
    "trusted": 1.0,
    "partial": 0.6,
    "suspicious": 0.3,
    "unavailable": 0.0,
}


def _dataset(service: DataService, adapter: str) -> Dataset | None:
    value = service._cached_dataset(adapter, allow_stale=True)
    if not isinstance(value, Dataset):
        return None
    return service._decorate_dataset(
        adapter,
        value,
        cache_age_seconds=service.cache.age_seconds(adapter),
        from_cache=True,
    )


def _number(value: object) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _curve_summary(dataset: Dataset | None) -> dict[str, Any]:
    empty = {"tenors": {}, "spreads_bp": {}, "ten_year_change_bp": None}
    if dataset is None or not isinstance(dataset.data, dict):
        return empty
    data = dataset.data
    tenors = data.get("tenors", [])
    series = data.get("series", [])
    government = next(
        (
            item
            for item in series
            if isinstance(item, dict)
            and "国债" in str(item.get("name", ""))
            and "最新" in str(item.get("name", ""))
        ),
        None,
    )
    if not government:
        return empty
    values = government.get("values", [])
    tenor_values = {
        str(tenor): _number(values[index]) if index < len(values) else None
        for index, tenor in enumerate(tenors)
    }

    def spread(long_tenor: str, short_tenor: str) -> float | None:
        long_value = tenor_values.get(long_tenor)
        short_value = tenor_values.get(short_tenor)
        if long_value is None or short_value is None:
            return None
        return round((long_value - short_value) * 100, 3)

    changes = data.get("changes", [])
    ten_year_index = tenors.index("10Y") if "10Y" in tenors else -1
    return {
        "tenors": tenor_values,
        "spreads_bp": {
            "10Y-1Y": spread("10Y", "1Y"),
            "10Y-5Y": spread("10Y", "5Y"),
            "30Y-10Y": spread("30Y", "10Y"),
        },
        "ten_year_change_bp": (
            _number(changes[ten_year_index])
            if 0 <= ten_year_index < len(changes)
            else None
        ),
    }


def build_market_brief(
    service: DataService, settings: ResearchSignalSettings | None = None
) -> dict[str, Any]:
    """Build a compact, provenance-aware bridge from market data to research."""
    settings = settings or ResearchSignalSettings()
    rates = _dataset(service, "money_rates")
    curves = _dataset(service, "yield_curves")
    futures = _dataset(service, "treasury_futures")
    bonds = _dataset(service, "spot_bonds")
    datasets = {
        "money_rates": rates,
        "yield_curves": curves,
        "treasury_futures": futures,
        "spot_bonds": bonds,
    }
    signals: list[dict[str, Any]] = []

    def append_signal(
        *,
        signal_id: str,
        category: str,
        severity: str,
        direction: str,
        title: str,
        summary: str,
        value: float | None,
        unit: str,
        adapter: str,
        object_type: str | None = None,
        object_id: str | None = None,
        object_name: str | None = None,
        row_trusted: bool = True,
        threshold: float | None = None,
        trigger_reason: str = "",
    ) -> None:
        dataset = datasets.get(adapter)
        if dataset is None:
            return
        meta = dataset.meta
        actionable = bool(
            row_trusted
            and not meta.demo
            and meta.trust_level in {"trusted", "partial"}
            and meta.quality_score >= 60
        )
        signals.append(
            {
                "id": signal_id,
                "category": category,
                "severity": severity,
                "direction": direction,
                "title": title,
                "summary": summary,
                "value": value,
                "unit": unit,
                "object_type": object_type,
                "object_id": object_id,
                "object_name": object_name,
                "adapter": adapter,
                "source": meta.source,
                "source_url": meta.source_url,
                "observation_time": meta.observation_time,
                "fetched_at": meta.fetched_at.isoformat(),
                "trust_level": meta.trust_level,
                "quality_score": meta.quality_score,
                "data_state": meta.data_state,
                "demo": meta.demo,
                "actionable": actionable,
                "threshold": threshold,
                "trigger_reason": trigger_reason,
            }
        )

    rate_rows = rates.data if rates and isinstance(rates.data, list) else []
    rate_changes = [
        value
        for item in rate_rows
        if isinstance(item, dict)
        and (value := _number(item.get("change_bp"))) is not None
    ]
    average_rate_change = (
        round(sum(rate_changes) / len(rate_changes), 3) if rate_changes else None
    )
    if average_rate_change is not None:
        funding_direction = (
            "up" if average_rate_change > 0.1 else "down" if average_rate_change < -0.1 else "neutral"
        )
        funding_severity = (
            "high"
            if abs(average_rate_change) >= settings.funding_change_bp * 3
            else "watch"
            if abs(average_rate_change) >= settings.funding_change_bp
            else "info"
        )
        append_signal(
            signal_id="funding-average",
            category="funding",
            severity=funding_severity,
            direction=funding_direction,
            title="资金利率整体变化",
            summary=f"主要资金利率平均变动 {average_rate_change:+.2f} BP",
            value=average_rate_change,
            unit="BP",
            adapter="money_rates",
            threshold=settings.funding_change_bp,
            trigger_reason=f"主要资金利率平均绝对变动达到 {settings.funding_change_bp:g} BP 时进入关注。",
        )

    curve = _curve_summary(curves)
    ten_year = _number(curve["tenors"].get("10Y"))
    ten_year_change = _number(curve.get("ten_year_change_bp"))
    if ten_year is not None:
        curve_severity = (
            "high"
            if ten_year_change is not None
            and abs(ten_year_change) >= settings.curve_change_bp * 2
            else "watch"
            if ten_year_change is not None
            and abs(ten_year_change) >= settings.curve_change_bp
            else "info"
        )
        direction = (
            "up" if (ten_year_change or 0) > 0.1 else "down" if (ten_year_change or 0) < -0.1 else "neutral"
        )
        change_text = (
            f"，日变动 {ten_year_change:+.2f} BP" if ten_year_change is not None else ""
        )
        append_signal(
            signal_id="curve-10y",
            category="curve",
            severity=curve_severity,
            direction=direction,
            title="10Y 国债收益率",
            summary=f"10Y 国债收益率 {ten_year:.4f}%{change_text}",
            value=ten_year_change,
            unit="BP",
            adapter="yield_curves",
            object_type="curve",
            object_id="CGB-10Y",
            object_name="10Y 国债收益率",
            threshold=settings.curve_change_bp,
            trigger_reason=f"10Y 日变动绝对值达到 {settings.curve_change_bp:g} BP 时进入关注。",
        )
    ten_one = _number(curve["spreads_bp"].get("10Y-1Y"))
    if ten_one is not None:
        append_signal(
            signal_id="curve-10y-1y",
            category="curve",
            severity=(
                "watch"
                if ten_one < 0 or abs(ten_one) >= settings.curve_spread_bp
                else "info"
            ),
            direction="up" if ten_one > 0 else "down" if ten_one < 0 else "neutral",
            title="10Y–1Y 期限利差",
            summary=f"当前期限利差 {ten_one:.2f} BP",
            value=ten_one,
            unit="BP",
            adapter="yield_curves",
            object_type="curve",
            object_id="CGB-10Y-1Y",
            object_name="10Y–1Y 期限利差",
            threshold=settings.curve_spread_bp,
            trigger_reason=f"利差倒挂或绝对值达到 {settings.curve_spread_bp:g} BP 时进入关注。",
        )

    future_rows = futures.data if futures and isinstance(futures.data, list) else []
    valid_futures = [
        item
        for item in future_rows
        if isinstance(item, dict) and _number(item.get("change_pct")) is not None
    ]
    if valid_futures:
        future = max(
            valid_futures,
            key=lambda item: abs(_number(item.get("change_pct")) or 0),
        )
        change = _number(future.get("change_pct")) or 0
        contract = str(future.get("contract") or future.get("product") or "国债期货")
        append_signal(
            signal_id=f"future-{contract}",
            category="future",
            severity=(
                "high"
                if abs(change) >= settings.futures_change_pct * 2.5
                else "watch"
                if abs(change) >= settings.futures_change_pct
                else "info"
            ),
            direction="up" if change > 0 else "down" if change < 0 else "neutral",
            title=f"{contract} 期货变动",
            summary=f"最新价 {_number(future.get('price')) or 0:.3f}，涨跌 {change:+.3f}%",
            value=change,
            unit="%",
            adapter="treasury_futures",
            object_type="future",
            object_id=contract,
            object_name=contract,
            threshold=settings.futures_change_pct,
            trigger_reason=f"涨跌幅绝对值达到 {settings.futures_change_pct:g}% 时进入关注。",
        )

    bond_rows = bonds.data if bonds and isinstance(bonds.data, list) else []
    valid_bonds = [
        item
        for item in bond_rows
        if isinstance(item, dict)
        and item.get("quality_state") != "suspicious"
        and _number(item.get("change_bp")) is not None
    ]
    valid_bonds.sort(
        key=lambda item: abs(_number(item.get("change_bp")) or 0), reverse=True
    )
    for item in valid_bonds[:3]:
        change = _number(item.get("change_bp")) or 0
        code = str(item.get("code") or "")
        name = str(item.get("name") or code or "现券")
        bond_yield = _number(item.get("yield"))
        yield_text = f"收益率 {bond_yield:.4f}%" if bond_yield is not None else "收益率缺失"
        append_signal(
            signal_id=f"bond-{code or name}",
            category="bond",
            severity=(
                "high"
                if abs(change) >= settings.bond_change_bp * 2.5
                else "watch"
                if abs(change) >= settings.bond_change_bp
                else "info"
            ),
            direction="up" if change > 0 else "down" if change < 0 else "neutral",
            title=f"{name} 收益率异动",
            summary=f"{yield_text}，变动 {change:+.2f} BP",
            value=change,
            unit="BP",
            adapter="spot_bonds",
            object_type="bond",
            object_id=code or None,
            object_name=name,
            row_trusted=bool(code),
            threshold=settings.bond_change_bp,
            trigger_reason=f"收益率变动绝对值达到 {settings.bond_change_bp:g} BP 时进入关注。",
        )

    severity_order = {"high": 0, "watch": 1, "info": 2}
    signals.sort(
        key=lambda item: (
            0 if item["actionable"] else 1,
            severity_order[item["severity"]],
            item["id"],
        )
    )
    sources = [
        {
            "adapter": adapter,
            "source": dataset.meta.source,
            "source_url": dataset.meta.source_url,
            "observation_time": dataset.meta.observation_time,
            "fetched_at": dataset.meta.fetched_at.isoformat(),
            "data_state": dataset.meta.data_state,
            "trust_level": dataset.meta.trust_level,
            "quality_score": dataset.meta.quality_score,
            "demo": dataset.meta.demo,
        }
        for adapter, dataset in datasets.items()
        if dataset is not None
    ]
    status_priority = (
        "trading",
        "session_break",
        "pre_open",
        "closed",
        "non_trading_day",
        "daily",
        "unknown",
    )
    market_status = next(
        (
            dataset.meta.market_status_label
            for status in status_priority
            for dataset in datasets.values()
            if dataset is not None and dataset.meta.market_status == status
        ),
        "市场状态待确认",
    )
    headline_candidates = [signal for signal in signals if signal["actionable"]]
    if not headline_candidates:
        headline_candidates = signals
    headline_parts = [signal["summary"] for signal in headline_candidates[:2]]
    eligible_ids = [signal["id"] for signal in signals if signal["actionable"]]
    return {
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
        "market_status": market_status,
        "headline": "；".join(headline_parts) if headline_parts else "市场数据正在准备",
        "signals": signals[:8],
        "sources": sources,
        "eligible_signal_ids": eligible_ids,
        "snapshot_eligible": bool(eligible_ids),
        "notice": "仅将非演示、质量分不低于 60 且可信度为可信或部分可用的信号保存为研究证据。",
        "settings": settings.model_dump(),
    }


def build_daily_report(service: DataService, database: Database) -> dict[str, Any]:
    rates = _dataset(service, "money_rates")
    curves = _dataset(service, "yield_curves")
    futures = _dataset(service, "treasury_futures")
    bonds = _dataset(service, "spot_bonds")
    events = _dataset(service, "issuance_events")
    health = service.health_items()

    rate_rows = rates.data if rates and isinstance(rates.data, list) else []
    rate_changes = [
        number
        for item in rate_rows
        if isinstance(item, dict)
        and (number := _number(item.get("change_bp"))) is not None
    ]
    average_rate_change = (
        round(sum(rate_changes) / len(rate_changes), 3) if rate_changes else None
    )
    funding_tone = (
        "边际收紧"
        if average_rate_change is not None and average_rate_change > 1
        else "边际转松"
        if average_rate_change is not None and average_rate_change < -1
        else "变化有限"
    )

    curve = _curve_summary(curves)
    ten_year_change = curve["ten_year_change_bp"]
    duration_tone = (
        "长端收益率上行"
        if ten_year_change is not None and ten_year_change > 0.5
        else "长端收益率下行"
        if ten_year_change is not None and ten_year_change < -0.5
        else "长端窄幅波动"
    )

    future_rows = futures.data if futures and isinstance(futures.data, list) else []
    bond_rows = bonds.data if bonds and isinstance(bonds.data, list) else []
    event_rows = events.data if events and isinstance(events.data, list) else []

    def numeric_sort(items: list[Any], field: str, *, absolute: bool = False) -> list[dict]:
        valid = [
            item
            for item in items
            if isinstance(item, dict)
            and item.get("quality_state") != "suspicious"
            and _number(item.get(field)) is not None
        ]
        return sorted(
            valid,
            key=lambda item: abs(_number(item.get(field)) or 0) if absolute else (_number(item.get(field)) or 0),
            reverse=True,
        )

    data_notes: list[str] = []
    for item in health:
        if item.state in {"degraded", "unavailable"}:
            data_notes.append(f"{item.label}：{item.message or item.state}")
    if rates and rates.meta.warnings:
        data_notes.extend(f"资金面：{warning}" for warning in rates.meta.warnings)
    for label, dataset in (
        ("资金面", rates),
        ("收益率曲线", curves),
        ("国债期货", futures),
        ("现券", bonds),
    ):
        if dataset and dataset.meta.suspicious_rows:
            data_notes.append(
                f"{label}：已隔离 {dataset.meta.suspicious_rows} 条异常记录，不参与榜单与提醒"
            )

    market_item = next(
        (
            item
            for item in health
            if item.adapter in {"treasury_futures", "spot_bonds", "convertibles"}
        ),
        None,
    )
    healthy_count = sum(item.state == "healthy" for item in health)
    cached_count = sum(item.state == "cached" for item in health)
    available_count = sum(
        item.state not in {"unavailable", "not_checked"}
        and item.trust_level != "unavailable"
        for item in health
    )
    trusted_count = sum(
        item.state not in {"unavailable", "not_checked"}
        and item.trust_level == "trusted"
        for item in health
    )
    suspicious_count = sum(item.suspicious_rows for item in health)
    health_by_adapter = {item.adapter: item for item in health}
    source_breakdown: list[dict[str, Any]] = []
    confidence_score = 0.0
    core_healthy = 0
    core_blocked = 0
    core_suspicious = 0
    for adapter, weight in REPORT_SOURCE_WEIGHTS.items():
        item = health_by_adapter.get(adapter)
        state = item.state if item else "not_checked"
        trust_level = item.trust_level if item else "unavailable"
        contribution = round(
            weight
            * STATE_FACTORS[state]
            * TRUST_FACTORS[trust_level],
            2,
        )
        confidence_score += contribution
        core_healthy += int(state == "healthy" and trust_level == "trusted")
        core_blocked += int(
            state in {"unavailable", "not_checked"}
            or trust_level == "unavailable"
        )
        core_suspicious += int(trust_level == "suspicious")
        source_breakdown.append(
            {
                "adapter": adapter,
                "label": item.label if item else adapter,
                "weight": weight,
                "state": state,
                "trust_level": trust_level,
                "contribution": contribution,
            }
        )
    confidence_score = round(confidence_score)
    confidence_level = (
        "high"
        if confidence_score >= 85
        and core_healthy >= 4
        and not core_blocked
        and not core_suspicious
        else "medium"
        if confidence_score >= 60 and core_blocked <= 1
        else "low"
    )
    confidence_message = {
        "high": "主要数据已验证，可用于日常研究复盘",
        "medium": "部分数据来自缓存或降级源，结论需结合数据说明",
        "low": "关键数据不完整，仅建议用于状态排查",
    }[confidence_level]

    now = datetime.now(ZoneInfo("Asia/Shanghai"))
    report_date = now.date().isoformat()
    report_mode = (
        "intraday"
        if any(item.market_status == "trading" for item in health)
        else "close"
        if any(item.market_status == "closed" for item in health)
        else "latest"
    )

    upcoming_events: list[dict[str, Any]] = []
    recent_events: list[dict[str, Any]] = []
    for item in sorted(
        [item for item in event_rows if isinstance(item, dict)],
        key=lambda item: str(item.get("date", "")),
    ):
        raw_date = str(item.get("date", "")).replace("/", "-")[:10]
        try:
            observed = date.fromisoformat(raw_date)
        except ValueError:
            recent_events.append(item)
            continue
        if observed >= now.date():
            upcoming_events.append(item)
        else:
            recent_events.append(item)
    recent_events = list(reversed(recent_events))
    projects = database.list_research_projects()
    research_watchlist = database.list_watchlist()
    research_workflow = {
        "active_projects": sum(item.status != "archived" for item in projects),
        "due_projects": sum(
            bool(item.next_review_date and item.next_review_date <= report_date)
            and item.status != "archived"
            for item in projects
        ),
        "macro_watchlist": sum(
            item.object_type == "macro" for item in research_watchlist
        ),
        "pinned_watchlist": sum(item.pinned for item in research_watchlist),
        "macro_cache": database.macro_stats(),
        "recent_projects": [
            {
                "id": item.id,
                "title": item.title,
                "status": item.status,
                "confidence": item.confidence,
                "next_review_date": item.next_review_date,
                "updated_at": item.updated_at.isoformat(),
            }
            for item in projects[:5]
        ],
    }
    return {
        "generated_at": now.isoformat(),
        "report_date": report_date,
        "report_mode": report_mode,
        "market_status": market_item.market_status_label if market_item else "状态未知",
        "headline": f"资金面{funding_tone}，{duration_tone}",
        "funding": {
            "tone": funding_tone,
            "average_change_bp": average_rate_change,
            "items": rate_rows,
        },
        "curve": curve,
        "futures": future_rows,
        "bond_movers": numeric_sort(bond_rows, "change_bp", absolute=True)[:8],
        "active_bonds": numeric_sort(bond_rows, "volume")[:8],
        "events": (upcoming_events[:6] + recent_events[:4])[:8],
        "event_groups": {
            "upcoming": upcoming_events[:8],
            "recent": recent_events[:8],
        },
        "confidence": {
            "level": confidence_level,
            "score": confidence_score,
            "message": confidence_message,
            "trusted_sources": trusted_count,
            "suspicious_rows": suspicious_count,
            "source_breakdown": source_breakdown,
        },
        "data_health": {
            "healthy": healthy_count,
            "cached": cached_count,
            "available": available_count,
            "total": len(health),
            "history": database.history_stats(),
        },
        "research_workflow": research_workflow,
        "data_notes": list(dict.fromkeys(data_notes)),
    }
