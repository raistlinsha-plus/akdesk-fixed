from __future__ import annotations

from typing import Any

from .models import Dataset, WatchlistItem
from .provider import DataService


WATCH_ADAPTERS = {
    "bond": ("spot_bonds", "bonds"),
    "future": ("treasury_futures", "futures"),
    "convertible": ("convertibles", "convertibles"),
    "macro": (None, "macro"),
    "fx": (None, "fx"),
}


def enrich_watchlist(
    service: DataService, items: list[WatchlistItem]
) -> list[dict[str, Any]]:
    enriched: list[dict[str, Any]] = []
    for item in items:
        adapter, page = WATCH_ADAPTERS[item.object_type]
        quote: dict[str, Any] | None = None
        meta: dict[str, Any] | None = None
        candidate_adapters = (
            ("fx_pairs", "fx_rmb_reference")
            if item.object_type == "fx"
            else (adapter,)
            if adapter
            else ()
        )
        for candidate_adapter in candidate_adapters:
            dataset = service._cached_dataset(candidate_adapter, allow_stale=True)
            if isinstance(dataset, Dataset):
                decorated = service._decorate_dataset(
                    candidate_adapter,
                    dataset,
                    cache_age_seconds=service.cache.age_seconds(candidate_adapter),
                    from_cache=True,
                )
                row = _find_row(item, decorated.data)
                quote = _quote(item.object_type, row) if row else None
                if quote is not None:
                    meta = {
                        "source": decorated.meta.source,
                        "observation_time": (
                            row.get("observation_date")
                            or decorated.meta.observation_time
                        ),
                        "fetched_at": decorated.meta.fetched_at.isoformat(),
                        "data_state": decorated.meta.data_state,
                        "trust_level": decorated.meta.trust_level,
                        "quality_score": decorated.meta.quality_score,
                        "market_status": decorated.meta.market_status_label,
                        "demo": decorated.meta.demo,
                    }
                    break
        enriched.append(
            {
                **item.model_dump(mode="json"),
                "page": page,
                "quote": quote,
                "source_meta": meta,
                "quote_status": (
                    "request_required"
                    if item.object_type == "macro"
                    else "available"
                    if quote is not None
                    else "not_found"
                ),
            }
        )
    return enriched


def _find_row(item: WatchlistItem, data: Any) -> dict[str, Any] | None:
    if not isinstance(data, list):
        return None
    for row in data:
        if not isinstance(row, dict):
            continue
        key = (
            row.get("product")
            if item.object_type == "future"
            else row.get("code")
        )
        if str(key or "") == item.object_id:
            return row
    return None


def _quote(object_type: str, row: dict[str, Any]) -> dict[str, Any]:
    if object_type == "bond":
        return {
            "primary_label": "收益率",
            "primary_value": row.get("yield"),
            "primary_unit": "%",
            "change_label": "收益率变动",
            "change_value": row.get("change_bp"),
            "change_unit": "BP",
        }
    if object_type == "future":
        return {
            "primary_label": "价格",
            "primary_value": row.get("price"),
            "primary_unit": "",
            "change_label": "涨跌幅",
            "change_value": row.get("change_pct"),
            "change_unit": "%",
        }
    if object_type == "fx":
        return {
            "primary_label": "中间值",
            "primary_value": row.get("mid"),
            "primary_unit": "",
            "change_label": "日变动",
            "change_value": row.get("change_pct"),
            "change_unit": "%",
        }
    return {
        "primary_label": "价格",
        "primary_value": row.get("price"),
        "primary_unit": "",
        "change_label": "涨跌幅",
        "change_value": row.get("change_pct"),
        "change_unit": "%",
        "premium_pct": row.get("premium_pct"),
        "ytm_pct": row.get("ytm_pct"),
    }
