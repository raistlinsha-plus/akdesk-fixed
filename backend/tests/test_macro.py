from __future__ import annotations

from datetime import date, timedelta

import httpx
import pytest

from app.database import Database
from app.macro import (
    FredNotConfiguredError,
    MacroProviderError,
    MacroService,
    transform_observations,
)
from app.settings import SecretStatus


class FakeSecrets:
    def __init__(self, key: str | None = "a" * 32) -> None:
        self.key = key

    def get(self) -> str | None:
        return self.key

    def status(self) -> SecretStatus:
        return SecretStatus(self.key is not None, "test" if self.key else "none")


def fred_response(endpoint: str, params: dict):
    assert params["api_key"] == "a" * 32
    if endpoint == "series":
        return {
            "seriess": [
                {
                    "id": "DGS10",
                    "title": "Market Yield on U.S. Treasury Securities at 10-Year",
                    "units": "Percent",
                    "frequency": "Daily",
                    "seasonal_adjustment": "Not Seasonally Adjusted",
                    "last_updated": "2026-07-14 16:01:00-05",
                    "notes": "Test metadata",
                    "realtime_start": "2026-07-14",
                    "realtime_end": "2026-07-14",
                }
            ]
        }
    if endpoint == "series/observations":
        return {
            "observations": [
                {
                    "date": "2026-07-13",
                    "value": "4.12",
                    "realtime_start": "2026-07-14",
                    "realtime_end": "9999-12-31",
                },
                {
                    "date": "2026-07-14",
                    "value": ".",
                    "realtime_start": "2026-07-14",
                    "realtime_end": "9999-12-31",
                },
            ]
        }
    if endpoint == "series/release":
        return {
            "releases": [
                {"id": 18, "name": "H.15 Selected Interest Rates", "link": "https://www.federalreserve.gov/releases/h15/"}
            ]
        }
    if endpoint == "release/sources":
        return {
            "sources": [
                {"name": "Board of Governors of the Federal Reserve System", "link": "https://www.federalreserve.gov/"}
            ]
        }
    raise AssertionError(endpoint)


def test_fred_series_is_request_scoped_with_vintage_and_attribution(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    calls: list[str] = []

    def request(endpoint: str, params: dict):
        calls.append(endpoint)
        return fred_response(endpoint, params)

    service = MacroService(database, FakeSecrets(), request)
    result = service.series("DGS10", years=1)
    second = service.series("DGS10", years=1)

    assert calls == [
        "series",
        "series/observations",
        "series/release",
        "release/sources",
    ] * 2
    assert result.data["series"]["title_zh"] == "美国国债 10Y"
    assert result.data["series"]["source_organization"].startswith("Board of Governors")
    assert result.data["observations"][0]["value"] == 4.12
    assert result.data["observations"][1]["value"] is None
    assert result.data["observations"][0]["fetched_at"]
    assert second.meta.data_state == "live"
    assert database.macro_stats()["points"] == 0
    assert service.health_item().cache_persisted is False
    assert service.health_item().execution_mode == "in_process_http"
    assert service.integration_status()["verified"] is True


def test_fred_without_key_reports_configuration_and_no_cache(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    service = MacroService(database, FakeSecrets(None))

    with pytest.raises(FredNotConfiguredError, match="配置 FRED API Key"):
        service.series("DGS10", years=1)

    assert service.health_item().state == "not_checked"
    assert service.health_item().cache_persisted is False


def test_macro_transformations_preserve_actual_missing_boundaries() -> None:
    observations = [
        {"date": "2024-01-01", "value": 100},
        {"date": "2024-02-01", "value": None},
        {"date": "2024-03-01", "value": 110},
        {"date": "2024-04-01", "value": 120},
    ]

    level = transform_observations(observations, "level", "Monthly")
    changed = transform_observations(observations, "change", "Monthly")
    normalized = transform_observations(observations, "normalize", "Monthly")
    zscore = transform_observations(observations, "zscore", "Monthly")

    assert len(level) == 4 and level[1]["value"] is None
    assert [item["value"] for item in changed] == [None, None, None, 10]
    assert normalized[1]["value"] is None
    assert normalized[0]["value"] == 100
    assert zscore[1]["value"] is None
    assert round(sum(item["value"] for item in zscore if item["value"] is not None), 10) == 0
    with pytest.raises(ValueError, match="官方 pc1"):
        transform_observations(observations, "yoy", "Monthly")


def test_chart_uses_official_pc1_and_keeps_missing_dates(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    units: list[str] = []

    def request(endpoint: str, params: dict):
        if endpoint == "series/observations":
            units.append(params["units"])
        return fred_response(endpoint, params)

    chart = MacroService(database, FakeSecrets(), request).chart(
        ["DGS10"], years=1, transform="yoy"
    )

    assert units == ["pc1"]
    assert chart.data["dates"] == ["2026-07-13", "2026-07-14"]
    assert chart.data["series"][0]["values"] == [4.12, None]
    assert chart.data["series"][0]["realtime_start"] == [
        "2026-07-14",
        "2026-07-14",
    ]
    assert chart.data["transform_source"] == "FRED API units=pc1"


def test_release_calendar_sends_explicit_window(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    seen: dict = {}
    today = date.today()

    def request(endpoint: str, params: dict):
        assert endpoint == "releases/dates"
        seen.update(params)
        return {
            "count": 1,
            "release_dates": [
                {"date": today.isoformat(), "release_id": 1, "release_name": "Test release"}
            ]
        }

    result = MacroService(database, FakeSecrets(), request).release_calendar()

    assert seen["realtime_start"] == (today - timedelta(days=14)).isoformat()
    assert seen["realtime_end"] == (today + timedelta(days=45)).isoformat()
    assert seen["limit"] == 1000
    assert seen["offset"] == 0
    assert seen["sort_order"] == "asc"
    assert result.data[0]["name"] == "Test release"
    assert result.meta.data_state == "live"


def test_release_calendar_paginates_large_windows(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    offsets: list[int] = []
    today = date.today().isoformat()

    def request(endpoint: str, params: dict):
        assert endpoint == "releases/dates"
        offsets.append(params["offset"])
        if params["offset"] == 0:
            return {
                "count": 1001,
                "release_dates": [
                    {"date": today, "release_id": index, "release_name": f"Release {index}"}
                    for index in range(1000)
                ],
            }
        return {
            "count": 1001,
            "release_dates": [
                {"date": today, "release_id": 1000, "release_name": "Release 1000"}
            ],
        }

    result = MacroService(database, FakeSecrets(), request).release_calendar()

    assert offsets == [0, 1000]
    assert len(result.data) == 1001


def test_fred_circuit_opens_after_three_failed_requests(tmp_path) -> None:
    database = Database(tmp_path / "macro.db")
    calls = 0

    def request(_endpoint: str, _params: dict):
        nonlocal calls
        calls += 1
        raise MacroProviderError("temporary failure")

    service = MacroService(database, FakeSecrets(), request)
    for _ in range(3):
        with pytest.raises(MacroProviderError):
            service.series("DGS10", years=1)

    assert service.health_item().circuit_state == "open"
    assert service.health_item().next_retry_at is not None
    with pytest.raises(MacroProviderError, match="熔断"):
        service.series("DGS10", years=1)
    assert calls == 3


def test_fred_http_retries_429_and_classifies_authentication(tmp_path, monkeypatch) -> None:
    database = Database(tmp_path / "macro.db")
    request = httpx.Request("GET", "https://api.stlouisfed.org/fred/series")
    responses = [
        httpx.Response(429, headers={"Retry-After": "0"}, request=request),
        httpx.Response(503, request=request),
        httpx.Response(200, json={"ok": True}, request=request),
    ]
    delays: list[float] = []
    monkeypatch.setattr("app.macro.httpx.get", lambda *_args, **_kwargs: responses.pop(0))
    service = MacroService(database, FakeSecrets(), sleep=delays.append)

    assert service._request_json("series", {}) == {"ok": True}
    assert delays == [0.25, 0.5]

    monkeypatch.setattr(
        "app.macro.httpx.get",
        lambda *_args, **_kwargs: httpx.Response(401, request=request),
    )
    with pytest.raises(MacroProviderError, match="Key 验证失败"):
        service._request_json("series", {})
