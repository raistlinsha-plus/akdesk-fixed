from __future__ import annotations

from datetime import date
from typing import Any

from .database import Database
from .macro import MacroService
from .models import ReleaseReviewItem


def evaluate_release_review(
    database: Database,
    macro_service: MacroService,
    review: ReleaseReviewItem,
) -> dict[str, Any]:
    observation_year = date.fromisoformat(review.observation_period).year
    years = max(1, min(50, date.today().year - observation_year + 2))
    dataset = macro_service.series(review.series_id, years=years, refresh=True)
    observations = dataset.data.get("observations", [])
    actual = next(
        (
            item
            for item in observations
            if isinstance(item, dict) and item.get("date") == review.observation_period
        ),
        None,
    )
    actual_value = actual.get("value") if actual else None
    realtime_start = str(actual.get("realtime_start") or "") if actual else None
    surprise = (
        round(float(actual_value) - review.expected_value, 8)
        if actual_value is not None
        else None
    )
    revision_status = (
        "not_reviewed"
        if not review.reviewed_realtime_start
        else "unchanged"
        if realtime_start == review.reviewed_realtime_start
        else "official_version_changed"
    )
    return {
        "review": review.model_dump(mode="json"),
        "actual": {
            "value": actual_value,
            "date": review.observation_period if actual else None,
            "realtime_start": realtime_start,
            "realtime_end": actual.get("realtime_end") if actual else None,
            "fetched_at": dataset.meta.fetched_at.isoformat(),
            "source": dataset.meta.source,
            "source_url": dataset.meta.source_url,
            "persisted": False,
        },
        "surprise": surprise,
        "revision_status": revision_status,
        "market_window": database.market_window(
            review.release_date,
            pre_days=review.pre_window_days,
            post_days=review.post_window_days,
        ),
        "storage_notice": "FRED 实际值仅在本次请求中处理，不写入 SQLite；本地只保存用户预期和 vintage 引用。",
    }

