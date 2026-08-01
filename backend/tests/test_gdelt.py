from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.database import Database
from app.gdelt import GdeltProviderError, GdeltService


def gdelt_response(_params: dict):
    return {
        "articles": [
            {
                "url": "https://example.com/news/1",
                "title": "Issuer refinancing plan draws investor attention",
                "seendate": "20260723T101500Z",
                "socialimage": "https://example.com/image.jpg",
                "domain": "example.com",
                "language": "English",
                "sourcecountry": "United Kingdom",
            },
            {
                "url": "https://second.example/news/2",
                "title": "Bondholders review new covenant package",
                "seendate": "20260722T091500Z",
                "domain": "second.example",
                "language": "English",
                "sourcecountry": "United States",
            },
            {
                "url": "javascript:alert(1)",
                "title": "Unsafe URL is discarded",
            },
        ]
    }


def test_gdelt_search_normalizes_metadata_and_reuses_cache(tmp_path) -> None:
    database = Database(tmp_path / "gdelt.db")
    calls: list[dict] = []

    def request(params: dict):
        calls.append(params)
        return gdelt_response(params)

    service = GdeltService(database, request_json=request, sleep=lambda _value: None)
    result = service.search("  issuer   refinancing ", days=7, limit=20)
    cached = service.search("issuer refinancing", days=7, limit=20)

    assert len(calls) == 1
    assert result.data.article_count == 2
    assert result.data.source_count == 2
    assert result.data.country_count == 2
    assert result.data.articles[0].seen_at == "2026-07-23T10:15:00+00:00"
    assert result.data.verification_status == "unverified_clue"
    assert result.meta.data_state == "latest"
    assert result.meta.trust_level == "partial"
    assert cached.meta.data_state == "cached"
    assert database.gdelt_stats()["articles"] == 2
    assert service.health_item().research_status == "limited"


def test_gdelt_refresh_failure_falls_back_to_stale_metadata(tmp_path) -> None:
    database = Database(tmp_path / "gdelt.db")
    service = GdeltService(
        database, request_json=gdelt_response, sleep=lambda _value: None
    )
    service.search('"issuer name"', days=30, limit=20)
    old = (datetime.now() - timedelta(days=2)).isoformat()
    with database._connect() as connection:
        connection.execute(
            "UPDATE gdelt_query_cache SET fetched_at = ?, expires_at = ?",
            (old, old),
        )

    def fail(_params: dict):
        raise GdeltProviderError("temporary failure")

    service._request_override = fail
    result = service.search('"issuer name"', days=30, limit=20)

    assert result.meta.stale is True
    assert result.meta.data_state == "stale"
    assert result.meta.trust_level == "partial"
    assert any("temporary failure" in item for item in result.meta.warnings)


@pytest.mark.parametrize(
    ("query", "days", "limit", "sort"),
    [
        ("x", 7, 20, "datedesc"),
        ("valid", 0, 20, "datedesc"),
        ("valid", 7, 51, "datedesc"),
        ("valid", 7, 20, "toneasc"),
    ],
)
def test_gdelt_rejects_unbounded_queries(
    tmp_path, query: str, days: int, limit: int, sort: str
) -> None:
    service = GdeltService(
        Database(tmp_path / f"{days}-{limit}.db"),
        request_json=gdelt_response,
    )
    with pytest.raises(ValueError):
        service.search(query, days=days, limit=limit, sort=sort)


def test_gdelt_cache_enforces_metadata_size_boundary(tmp_path) -> None:
    database = Database(tmp_path / "gdelt.db")
    with pytest.raises(ValueError, match="512 KB"):
        database.upsert_gdelt_cache(
            cache_key="oversized",
            query="issuer",
            days=7,
            result_limit=20,
            sort="datedesc",
            payload={"articles": [{"title": "x" * (513 * 1024)}]},
            fetched_at=datetime.now().isoformat(),
            expires_at=(datetime.now() + timedelta(hours=12)).isoformat(),
        )
