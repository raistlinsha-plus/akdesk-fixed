from datetime import datetime

from app import demo_data
from app.database import Database
from app.models import Dataset, HealthItem, SourceMeta
from app.provider import DataService
from app.research import build_daily_report, build_market_brief


def _dataset(data, observation: str = "2026-07-13") -> Dataset:
    return Dataset(
        data=data,
        meta=SourceMeta(
            source="test",
            observation_time=observation,
            fetched_at=datetime.now(),
        ),
    )


def test_daily_report_uses_cached_research_data(tmp_path) -> None:
    service = DataService()
    database = Database(tmp_path / "research.db")
    datasets = {
        "money_rates": _dataset(demo_data.money_rates()),
        "yield_curves": _dataset(demo_data.yield_curves()),
        "spot_bonds": _dataset(demo_data.spot_bonds()),
        "treasury_futures": _dataset(demo_data.futures()),
        "issuance_events": _dataset(demo_data.events()),
    }
    for adapter, dataset in datasets.items():
        service.cache.set(adapter, dataset, 3_600)
        database.record_market_history(adapter, dataset)

    report = build_daily_report(service, database)

    assert "资金面" in report["headline"]
    assert report["curve"]["spreads_bp"]["10Y-1Y"] == 40.0
    assert len(report["futures"]) == 4
    assert report["active_bonds"][0]["volume"] >= report["active_bonds"][-1]["volume"]
    assert report["data_health"]["history"]["points"] > 0
    assert report["report_date"]
    assert report["report_mode"] in {"intraday", "close", "latest"}
    assert report["confidence"]["level"] in {"high", "medium", "low"}
    assert "upcoming" in report["event_groups"]
    assert report["research_workflow"]["active_projects"] == 0
    assert report["research_workflow"]["macro_cache"]["points"] == 0


def test_daily_report_quarantines_suspicious_bond_movers(tmp_path) -> None:
    service = DataService()
    database = Database(tmp_path / "research.db")
    bonds = service._decorate_dataset(
        "spot_bonds",
        _dataset(
            [
                {
                    "code": "112233",
                    "name": "异常债券",
                    "type": "信用债",
                    "yield": 2.9,
                    "change_bp": 147.22,
                    "price": 99.5,
                    "volume": 10,
                },
                {
                    "code": "240011",
                    "name": "24附息国债11",
                    "type": "国债",
                    "yield": 1.8,
                    "change_bp": -1.2,
                    "price": 102.3,
                    "volume": 20,
                },
            ]
        ),
    )
    service.cache.set("spot_bonds", bonds, 3_600)

    report = build_daily_report(service, database)

    assert [item["code"] for item in report["bond_movers"]] == ["240011"]
    assert any("已隔离 1 条异常记录" in note for note in report["data_notes"])


def test_cached_core_sources_cannot_be_reported_as_high_confidence(tmp_path) -> None:
    service = DataService()
    database = Database(tmp_path / "research.db")
    datasets = {
        "money_rates": _dataset(demo_data.money_rates()),
        "yield_curves": _dataset(demo_data.yield_curves()),
        "spot_bonds": _dataset(demo_data.spot_bonds()),
        "treasury_futures": _dataset(demo_data.futures()),
        "issuance_events": _dataset(demo_data.events()),
    }
    for adapter, dataset in datasets.items():
        service.cache.set(adapter, dataset, 3_600)
        service.health[adapter] = HealthItem(
            adapter=adapter,
            label=adapter,
            state="cached",
        )

    report = build_daily_report(service, database)

    assert report["confidence"]["level"] == "medium"
    assert report["confidence"]["score"] == 75
    assert report["confidence"]["trusted_sources"] == 5
    assert report["data_health"]["healthy"] == 0


def test_high_confidence_requires_healthy_core_coverage(tmp_path) -> None:
    service = DataService()
    database = Database(tmp_path / "research.db")
    datasets = {
        "money_rates": _dataset(demo_data.money_rates()),
        "yield_curves": _dataset(demo_data.yield_curves()),
        "spot_bonds": _dataset(demo_data.spot_bonds()),
        "treasury_futures": _dataset(demo_data.futures()),
        "issuance_events": _dataset(demo_data.events()),
    }
    for adapter, dataset in datasets.items():
        service.cache.set(adapter, dataset, 3_600)
        service.health[adapter] = HealthItem(
            adapter=adapter,
            label=adapter,
            state="healthy",
        )

    report = build_daily_report(service, database)

    assert report["confidence"]["level"] == "high"
    assert report["confidence"]["score"] == 100
    assert report["confidence"]["trusted_sources"] == 5
    assert len(report["confidence"]["source_breakdown"]) == 5


def test_market_brief_builds_actionable_signals_with_provenance(tmp_path) -> None:
    service = DataService()
    datasets = {
        "money_rates": _dataset(demo_data.money_rates()),
        "yield_curves": _dataset(demo_data.yield_curves()),
        "spot_bonds": _dataset(demo_data.spot_bonds()),
        "treasury_futures": _dataset(demo_data.futures()),
    }
    for adapter, dataset in datasets.items():
        service.cache.set(adapter, dataset, 3_600)
    service._market_status = lambda adapter, now=None: (
        ("pre_open", "未开盘")
        if adapter in {"treasury_futures", "spot_bonds"}
        else ("daily", "日频数据")
    )

    brief = build_market_brief(service)

    assert brief["snapshot_eligible"] is True
    assert brief["market_status"] == "未开盘"
    assert {signal["category"] for signal in brief["signals"]} >= {
        "funding",
        "curve",
        "future",
        "bond",
    }
    assert all(signal["source"] == "test" for signal in brief["signals"])
    assert all(signal["observation_time"] == "2026-07-13" for signal in brief["signals"])
    assert set(brief["eligible_signal_ids"]) == {
        signal["id"] for signal in brief["signals"] if signal["actionable"]
    }
    assert "future-T主力" not in brief["eligible_signal_ids"]


def test_market_brief_excludes_suspicious_bond_rows_from_signals() -> None:
    service = DataService()
    bonds = _dataset(
        [
            {
                "code": "BAD001",
                "name": "异常债券",
                "yield": 4.2,
                "change_bp": 99,
                "quality_state": "suspicious",
            },
            {
                "code": "240011",
                "name": "24附息国债11",
                "yield": 1.8,
                "change_bp": -1.2,
                "quality_state": "trusted",
            },
        ]
    )
    bonds.meta.trust_level = "suspicious"
    bonds.meta.quality_score = 35
    service.cache.set("spot_bonds", bonds, 3_600)
    service.cache.set(
        "yield_curves",
        _dataset(demo_data.yield_curves()),
        3_600,
    )

    brief = build_market_brief(service)

    signal_ids = {signal["id"] for signal in brief["signals"]}
    assert "bond-BAD001" not in signal_ids
    assert "bond-240011" in signal_ids
    assert brief["signals"][0]["actionable"] is True
    assert "异常债券" not in brief["headline"]
