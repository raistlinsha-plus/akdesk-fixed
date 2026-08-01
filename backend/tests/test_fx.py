from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from app.database import Database
from app.models import Dataset, SourceMeta, WatchlistCreate
from app.provider import DataService
from app.watchlist import enrich_watchlist


class _FxAk:
    @staticmethod
    def fx_pair_quote():
        return pd.DataFrame(
            [
                {"货币对": "USD/JPY", "买报价": 162.48, "卖报价": 162.49},
                {"货币对": "EUR/USD", "买报价": 1.1433, "卖报价": 1.1434},
            ]
        )

    @staticmethod
    def currency_boc_sina(*, symbol: str, start_date: str, end_date: str):
        assert start_date <= end_date
        values = {
            "美元": (680.0, 679.0),
            "欧元": (775.0, 776.0),
            "日元": (4.2, 4.18),
            "英镑": (910.0, 917.0),
            "港币": (86.7, 86.6),
        }
        previous, current = values[symbol]
        return pd.DataFrame(
            [
                {
                    "日期": "2026-07-15",
                    "中行汇买价": previous - 2,
                    "中行钞卖价/汇卖价": previous + 2,
                    "央行中间价": previous,
                    "中行折算价": previous,
                },
                {
                    "日期": "2026-07-16",
                    "中行汇买价": previous - 1,
                    "中行钞卖价/汇卖价": previous + 1,
                    "央行中间价": None,
                    "中行折算价": previous + 0.5,
                },
                {
                    "日期": "2026-07-17",
                    "中行汇买价": current - 2,
                    "中行钞卖价/汇卖价": current + 2,
                    "央行中间价": current,
                    "中行折算价": current,
                },
            ]
        )


def _live_service(monkeypatch) -> DataService:
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    service = DataService()
    service._ak = _FxAk()
    return service


def test_fx_pairs_normalize_quotes_without_faking_observation_time(monkeypatch):
    service = _live_service(monkeypatch)

    result = service.fx_pairs()

    assert [item["code"] for item in result.data] == ["EURUSD", "USDJPY"]
    assert result.data[0]["mid"] == 1.14335
    assert result.data[1]["spread_pips"] == 1.0
    assert result.meta.observation_time is None
    assert result.meta.trust_level == "partial"
    assert "源未提供可信市场时间" in result.meta.quality_issues


def test_rmb_reference_uses_only_central_parity_and_normalizes_units(monkeypatch):
    service = _live_service(monkeypatch)

    result = service.fx_rmb_reference()

    assert result.meta.observation_time == "2026-07-17"
    assert result.meta.trust_level == "trusted"
    usd = next(item for item in result.data if item["code"] == "USDCNY")
    jpy = next(item for item in result.data if item["code"] == "JPYCNY")
    assert usd["mid"] == 6.79
    assert usd["change_pct"] == round((679 / 680 - 1) * 100, 4)
    assert [item["date"] for item in usd["history"]] == [
        "2026-07-15",
        "2026-07-17",
    ]
    assert jpy["display_basis"] == 100
    assert jpy["mid"] == 4.18


def test_fx_contract_quarantines_crossed_quote():
    service = DataService()
    result = service._decorate_dataset(
        "fx_pairs",
        Dataset(
            data=[
                {
                    "code": "EURUSD",
                    "name": "欧元/美元",
                    "bid": 1.2,
                    "ask": 1.1,
                    "mid": 1.15,
                }
            ],
            meta=SourceMeta(source="test", fetched_at=datetime.now()),
        ),
    )

    assert result.meta.trust_level == "suspicious"
    assert result.data[0]["quality_state"] == "suspicious"
    assert "卖报价低于买报价" in result.data[0]["quality_issues"]


def test_global_fx_clock_does_not_follow_china_holiday_calendar():
    service = DataService()
    service.cache.set(
        "trade_calendar",
        Dataset(
            data=["2026-09-30", "2026-10-09"],
            meta=SourceMeta(source="calendar", fetched_at=datetime.now()),
        ),
        ttl_seconds=86_400,
    )
    china_holiday = datetime(
        2026, 10, 1, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai")
    )

    assert service._market_status("fx_pairs", china_holiday) == (
        "trading",
        "交易中",
    )
    assert service._market_status("treasury_futures", china_holiday) == (
        "non_trading_day",
        "非交易日",
    )


def test_fx_history_search_and_watchlist_work_without_schema_change(
    tmp_path, monkeypatch
):
    database = Database(tmp_path / "fx.db")
    service = _live_service(monkeypatch)
    references = service.fx_rmb_reference()
    pairs = service.fx_pairs()

    assert database.record_market_history("fx_rmb_reference", references) == 6
    history = database.market_history(
        "fx_rmb_reference", "mid", series_keys=["USDCNY"], days=45
    )
    assert history["dates"] == ["2026-07-15", "2026-07-17"]
    database.upsert_instruments("fx_pairs", pairs.data)
    result = database.search_instruments("EURUSD")
    assert result[0].object_type == "fx"
    assert result[0].page == "fx"

    watch = database.add_watchlist(
        WatchlistCreate(
            object_type="fx",
            object_id="EURUSD",
            name="欧元/美元",
        )
    )
    service.cache.set("fx_pairs", pairs, ttl_seconds=120)
    enriched = enrich_watchlist(service, [watch])
    assert enriched[0]["page"] == "fx"
    assert enriched[0]["quote"]["primary_value"] == 1.14335
