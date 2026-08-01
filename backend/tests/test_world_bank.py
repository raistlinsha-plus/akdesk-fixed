from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

import httpx
import pytest

from app.database import Database
from app.world_bank import (
    WORLD_BANK_LICENSE,
    WorldBankProviderError,
    WorldBankService,
)


def world_bank_response(path: str, params: dict):
    if path == "/indicator/NY.GDP.MKTP.KD.ZG":
        return [
            {"page": 1, "pages": 1, "total": 1},
            [
                {
                    "id": "NY.GDP.MKTP.KD.ZG",
                    "name": "GDP growth (annual %)",
                    "unit": "",
                    "source": {
                        "id": "2",
                        "value": "World Development Indicators",
                    },
                    "sourceNote": "Annual percentage growth rate of GDP.",
                    "sourceOrganization": "World Bank national accounts data",
                }
            ],
        ]
    if path == "/country/CHN;USA":
        return [
            {"page": 1, "pages": 1, "total": 2},
            [
                {
                    "id": "CHN",
                    "iso2Code": "CN",
                    "name": "China",
                    "region": {"id": "EAS", "value": "East Asia & Pacific"},
                    "incomeLevel": {
                        "id": "UMC",
                        "value": "Upper middle income",
                    },
                    "capitalCity": "Beijing",
                    "longitude": "116.286",
                    "latitude": "40.0495",
                },
                {
                    "id": "USA",
                    "iso2Code": "US",
                    "name": "United States",
                    "region": {"id": "NAC", "value": "North America"},
                    "incomeLevel": {"id": "HIC", "value": "High income"},
                    "capitalCity": "Washington D.C.",
                    "longitude": "-77.032",
                    "latitude": "38.8895",
                },
            ],
        ]
    if path == "/country/CHN;USA/indicator/NY.GDP.MKTP.KD.ZG":
        if params["page"] == 1:
            return [
                {
                    "page": 1,
                    "pages": 2,
                    "total": 3,
                    "lastupdated": "2026-07-13",
                },
                [
                    {
                        "countryiso3code": "CHN",
                        "date": "2022",
                        "value": 3.0,
                        "obs_status": "",
                        "decimal": 1,
                    },
                    {
                        "countryiso3code": "USA",
                        "date": "2022",
                        "value": 2.1,
                        "obs_status": "",
                        "decimal": 1,
                    },
                ],
            ]
        return [
            {
                "page": 2,
                "pages": 2,
                "total": 3,
                "lastupdated": "2026-07-13",
            },
            [
                {
                    "countryiso3code": "CHN",
                    "date": "2021",
                    "value": 8.4,
                    "obs_status": "",
                    "decimal": 1,
                }
            ],
        ]
    raise AssertionError((path, params))


def test_world_bank_compare_paginates_aligns_missing_and_uses_cache(tmp_path) -> None:
    database = Database(tmp_path / "world-bank.db")
    calls: list[tuple[str, int]] = []

    def request(path: str, params: dict):
        calls.append((path, int(params.get("page") or 0)))
        return world_bank_response(path, params)

    service = WorldBankService(database, request)
    result = service.compare(
        ["CHN", "USA"],
        "NY.GDP.MKTP.KD.ZG",
        start_year=2020,
        end_year=2022,
    )
    calls_after_first = list(calls)
    cached = service.compare(
        ["CHN", "USA"],
        "NY.GDP.MKTP.KD.ZG",
        start_year=2020,
        end_year=2022,
    )

    assert [
        item[1]
        for item in calls
        if item[0].startswith("/country/") and "indicator/NY" in item[0]
    ] == [1, 2]
    assert calls == calls_after_first
    assert result.data["years"] == ["2020", "2021", "2022"]
    assert result.data["series"][0]["raw_values"] == [None, 8.4, 3.0]
    assert result.data["series"][1]["raw_values"] == [None, None, 2.1]
    assert result.data["latest_comparable_year"] == 2022
    assert result.data["coverage"] == {
        "available": 3,
        "total": 6,
        "ratio": 0.5,
        "by_country": {
            "CHN": {"available": 2, "total": 3},
            "USA": {"available": 1, "total": 3},
        },
    }
    assert result.data["indicator"]["license"] == WORLD_BANK_LICENSE
    assert result.data["indicator"]["source_organization"].startswith("World Bank")
    assert result.meta.data_state == "latest"
    assert cached.meta.data_state == "cached"
    assert cached.meta.fetched_at == result.meta.fetched_at
    assert database.world_bank_stats()["points"] == 6
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600


def test_world_bank_views_keep_year_alignment() -> None:
    raw = {
        "CHN": [None, 8.4, 3.0],
        "USA": [None, None, 2.1],
        "JPN": [None, 2.7, 1.0],
    }

    changed = WorldBankService._transform(raw, "change")
    ranked = WorldBankService._transform(raw, "rank")
    standardized = WorldBankService._transform(raw, "zscore")

    assert changed["CHN"] == [None, None, -5.4]
    assert changed["USA"] == [None, None, None]
    assert ranked["CHN"] == [None, 1.0, 1.0]
    assert ranked["USA"] == [None, None, 2.0]
    assert standardized["USA"][1] is None
    assert standardized["CHN"][2] > standardized["USA"][2]


def test_world_bank_refresh_failure_falls_back_to_stale_cache(tmp_path) -> None:
    database = Database(tmp_path / "world-bank.db")
    service = WorldBankService(database, world_bank_response)
    service.compare(
        ["CHN", "USA"],
        "NY.GDP.MKTP.KD.ZG",
        start_year=2020,
        end_year=2022,
    )
    old = (datetime.now() - timedelta(days=8)).isoformat()
    with database._connect() as connection:
        connection.execute(
            "UPDATE world_bank_observations SET fetched_at = ?", (old,)
        )

    def fail(_path: str, _params: dict):
        raise WorldBankProviderError("temporary failure")

    service._request_override = fail
    result = service.compare(
        ["CHN", "USA"],
        "NY.GDP.MKTP.KD.ZG",
        start_year=2020,
        end_year=2022,
    )

    assert result.meta.stale is True
    assert result.meta.data_state == "stale"
    assert result.meta.trust_level == "partial"
    assert any("temporary failure" in warning for warning in result.meta.warnings)


def test_world_bank_health_ages_during_a_long_running_process(tmp_path) -> None:
    database = Database(tmp_path / "world-bank.db")
    service = WorldBankService(database, world_bank_response)
    service.compare(
        ["CHN", "USA"],
        "NY.GDP.MKTP.KD.ZG",
        start_year=2020,
        end_year=2022,
    )
    old = (datetime.now() - timedelta(days=8)).isoformat()
    with database._connect() as connection:
        connection.execute(
            "UPDATE world_bank_observations SET fetched_at = ?", (old,)
        )

    health = service.health_item()

    assert health.state == "degraded"
    assert health.trust_level == "partial"
    assert health.cache_age_seconds is not None
    assert health.cache_age_seconds > 7 * 24 * 60 * 60


def test_world_bank_rejects_invalid_scope(tmp_path) -> None:
    service = WorldBankService(Database(tmp_path / "world-bank.db"))

    with pytest.raises(ValueError, match="2–8"):
        service.compare(
            ["CHN"],
            "NY.GDP.MKTP.KD.ZG",
            start_year=2020,
            end_year=2022,
        )
    with pytest.raises(ValueError, match="不支持"):
        service.compare(
            ["CHN", "USA"],
            "UNKNOWN",
            start_year=2020,
            end_year=2022,
        )


def test_world_bank_prefers_direct_connection_then_system_proxy(
    tmp_path, monkeypatch
) -> None:
    connection_modes: list[bool] = []

    class FakeResponse:
        status_code = 200

        @staticmethod
        def raise_for_status() -> None:
            return None

        @staticmethod
        def json():
            return [{"page": 1, "pages": 1}, []]

    class FakeClient:
        def __init__(self, *, trust_env: bool, **_kwargs) -> None:
            self.trust_env = trust_env
            connection_modes.append(trust_env)

        def __enter__(self):
            return self

        def __exit__(self, *_args) -> None:
            return None

        def get(self, url: str, *, params: dict):
            if not self.trust_env:
                raise httpx.ConnectError(
                    "direct unavailable", request=httpx.Request("GET", url, params=params)
                )
            return FakeResponse()

    monkeypatch.setattr("app.world_bank.httpx.Client", FakeClient)
    service = WorldBankService(Database(tmp_path / "world-bank.db"), sleep=lambda _: None)

    assert service._request_json("/country/CHN", {"format": "json"})[1] == []
    assert connection_modes == [False, True]
