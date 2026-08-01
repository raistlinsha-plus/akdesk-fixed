from datetime import datetime
import json
import sqlite3

import pytest
from pydantic import ValidationError

from app.database import Database
from app.models import (
    AlertCreate,
    Dataset,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
    ResearchProjectUpdate,
    SourceMeta,
    WatchlistCreate,
    WatchlistUpdate,
)


def test_watchlist_and_alert_roundtrip(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    watched = database.add_watchlist(
        WatchlistCreate(
            object_type="bond",
            object_id="240011",
            name="24附息国债11",
        )
    )
    alert = database.add_alert(
        AlertCreate(
            object_type="bond",
            object_id="240011",
            name="收益率突破",
            metric="yield",
            operator=">",
            threshold=2.0,
        )
    )

    assert database.list_watchlist()[0].object_id == "240011"
    assert database.list_alerts()[0].threshold == 2.0

    database.delete_watchlist(watched.id)
    database.delete_alert(alert.id)
    assert database.list_watchlist() == []
    assert database.list_alerts() == []


def test_market_history_calibration_removes_future_and_pre_open_futures(
    tmp_path,
) -> None:
    database = Database(tmp_path / "history-calibration.db")
    rows = [
        ("treasury_futures", "T", "T2609", "price", "2026-07-15", 109.0, "test", 100, "2026-07-15T06:28:00"),
        ("treasury_futures", "T", "T2609", "price", "2026-07-16", 110.0, "test", 100, "2026-07-15T10:00:00"),
        ("treasury_futures", "T", "T2609", "price", "2026-07-14", 108.0, "test", 100, "2026-07-14T15:20:00"),
    ]
    with database._connect() as connection:
        connection.executemany(
            """
            INSERT INTO market_history
                (adapter, series_key, label, metric, observation_time,
                 value, source, quality_score, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )

    result = database.calibrate_market_history(
        now=datetime(2026, 7, 15, 12, 0)
    )

    assert result == {
        "future_points_deleted": 1,
        "pre_open_futures_deleted": 1,
    }
    with database._connect() as connection:
        remaining = connection.execute(
            "SELECT observation_time FROM market_history"
        ).fetchall()
    assert [row[0] for row in remaining] == ["2026-07-14"]


def test_market_history_rejects_future_observation(tmp_path) -> None:
    database = Database(tmp_path / "future-history.db")
    dataset = Dataset(
        data=[
            {
                "product": "T",
                "contract": "T2609",
                "price": 109.0,
                "change_pct": 0.1,
                "volume": 10,
                "open_interest": 20,
            }
        ],
        meta=SourceMeta(
            source="test",
            observation_time="2099-01-01T15:15:00",
            fetched_at=datetime.now(),
        ),
    )

    assert database.record_market_history("treasury_futures", dataset) == 0
    assert database.history_stats()["points"] == 0


def test_instrument_index_supports_code_name_and_alias_search(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.upsert_instruments(
        "spot_bonds",
        [
            {
                "code": "240011",
                "name": "24附息国债11",
                "type": "国债",
            }
        ],
    )
    database.upsert_instruments(
        "convertibles",
        [
            {
                "code": "113000",
                "name": "示例转债A",
                "stock_name": "示例正股A",
            }
        ],
    )

    by_code = database.search_instruments("240011")
    by_name = database.search_instruments("附息国债")
    by_alias = database.search_instruments("示例正股")

    assert by_code[0].page == "bonds"
    assert by_name[0].object_id == "240011"
    assert by_alias[0].page == "convertibles"


def test_demo_instruments_are_labeled_in_search(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.upsert_instruments(
        "spot_bonds",
        [{"code": "240011", "name": "示例国债", "type": "国债"}],
        demo=True,
    )

    assert database.search_instruments("240011")[0].subtitle == "演示 · 国债"


def test_inferred_bond_codes_are_marked_for_verification_in_search(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    database.upsert_instruments(
        "spot_bonds",
        [
            {
                "code": "240011",
                "name": "24附息国债11",
                "type": "国债",
                "code_verified": False,
            }
        ],
    )

    assert database.search_instruments("240011")[0].subtitle == "需核验 · 国债"


def test_trusted_curve_history_is_compacted_and_queryable(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    dataset = Dataset(
        data={
            "history": [
                {
                    "date": "2026-07-10",
                    "values": {"1Y": 1.4, "10Y": 1.8},
                    "spreads_bp": {"10Y-1Y": 40.0},
                },
                {
                    "date": "2026-07-13",
                    "values": {"1Y": 1.42, "10Y": 1.79},
                    "spreads_bp": {"10Y-1Y": 37.0},
                },
            ]
        },
        meta=SourceMeta(
            source="test",
            observation_time="2026-07-13",
            fetched_at=datetime.now(),
        ),
    )

    assert database.record_market_history("yield_curves", dataset) == 6
    result = database.market_history(
        "yield_curves",
        "spread_bp",
        series_keys=["10Y-1Y"],
        days=30,
    )

    assert result["dates"] == ["2026-07-10", "2026-07-13"]
    assert result["series"][0]["values"] == [40.0, 37.0]
    assert database.history_stats()["points"] == 6


def test_demo_or_stale_data_never_enters_history(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    dataset = Dataset(
        data=[{"name": "Shibor O/N", "value": 1.4}],
        meta=SourceMeta(
            source="demo",
            fetched_at=datetime.now(),
            demo=True,
            stale=True,
        ),
    )

    assert database.record_market_history("money_rates", dataset) == 0
    assert database.history_stats()["points"] == 0


def test_intraday_refresh_overwrites_same_daily_research_point(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    for observed, price in (
        ("2026-07-13T10:00:00", 108.1),
        ("2026-07-13T15:15:00", 108.6),
    ):
        database.record_market_history(
            "treasury_futures",
            Dataset(
                data=[{"product": "T", "contract": "T2609", "price": price}],
                meta=SourceMeta(
                    source="test",
                    observation_time=observed,
                    fetched_at=datetime.now(),
                ),
            ),
        )

    result = database.market_history(
        "treasury_futures", "price", series_keys=["T"], days=30
    )
    assert result["dates"] == ["2026-07-13"]
    assert result["series"][0]["values"] == [108.6]


def test_suspicious_rows_never_enter_research_history(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    dataset = Dataset(
        data=[
            {
                "code": "112233",
                "name": "异常债券",
                "yield": 2.9,
                "change_bp": 147.22,
                "quality_state": "suspicious",
            },
            {
                "code": "240011",
                "name": "24附息国债11",
                "yield": 1.8,
                "change_bp": -1.2,
            },
        ],
        meta=SourceMeta(
            source="test",
            observation_time="2026-07-13",
            fetched_at=datetime.now(),
            trust_level="suspicious",
            suspicious_rows=1,
        ),
    )

    database.record_market_history("spot_bonds", dataset)
    result = database.market_history("spot_bonds", "change_bp", days=30)

    assert [series["key"] for series in result["series"]] == ["240011"]


def test_daily_report_archive_roundtrip_and_update(tmp_path) -> None:
    database = Database(tmp_path / "test.db")
    report = {
        "report_date": "2026-07-13",
        "report_mode": "close",
        "headline": "资金面变化有限",
        "confidence": {"level": "high", "score": 92},
    }
    database.save_daily_report(report)
    report["headline"] = "资金面边际转松"
    database.save_daily_report(report)

    restored = database.get_daily_report("2026-07-13")
    archives = database.list_daily_reports()

    assert restored is not None
    assert restored["headline"] == "资金面边际转松"
    assert archives[0]["report_date"] == "2026-07-13"
    assert archives[0]["confidence_level"] == "high"


def test_old_alert_schema_is_migrated_without_losing_rules(tmp_path) -> None:
    path = tmp_path / "legacy.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE alert_rules (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                name TEXT NOT NULL,
                metric TEXT NOT NULL,
                operator TEXT NOT NULL,
                threshold REAL NOT NULL,
                cooldown_minutes INTEGER NOT NULL DEFAULT 30,
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            INSERT INTO alert_rules
                (object_type, object_id, name, metric, operator, threshold,
                 cooldown_minutes, enabled, created_at)
            VALUES ('bond', '240011', '旧提醒', 'yield', '>', 2.0, 30, 1, ?)
            """,
            (datetime.now().isoformat(),),
        )

    database = Database(path)
    rule = database.list_alerts()[0]

    assert rule.name == "旧提醒"
    assert rule.max_triggers_per_day == 3
    assert rule.quiet_start is None


def test_unified_watchlist_metadata_and_research_project_roundtrip(tmp_path) -> None:
    database = Database(tmp_path / "research-workspace.db")
    macro = database.add_watchlist(
        WatchlistCreate(
            object_type="macro",
            object_id="DGS10",
            name="美国国债 10Y",
            group_name="美国利率",
            tags=["重点"],
        )
    )
    updated = database.update_watchlist(
        macro.id,
        WatchlistUpdate(
            research_status="tracking",
            pinned=True,
            next_review_date="2026-07-20",
        ),
    )
    project = database.add_research_project(
        ResearchProjectCreate(
            title="实际利率对长端美债的影响",
            question="实际利率是否继续上行？",
            hypothesis="通胀回落慢于预期",
            tags=["美债", "通胀"],
        )
    )
    evidence = database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="DGS10 与 DFII10",
            payload={
                "schema_version": 2,
                "storage_mode": "reference_only",
                "series": [
                    {"series_id": "DGS10"},
                    {"series_id": "DFII10"},
                ],
                "frozen": False,
            },
            source_summary="FRED",
            observation_start="2025-01-01",
            observation_end="2026-07-14",
        ),
    )
    revised = database.update_research_project(
        project.id,
        ResearchProjectUpdate(status="tracking", confidence=65),
    )

    assert updated is not None and updated.object_type == "macro"
    assert updated.pinned is True
    assert revised is not None and revised.status == "tracking"
    assert revised.confidence == 65
    assert evidence is not None and evidence.payload["frozen"] is False
    restored = database.get_research_project(project.id)
    assert restored is not None and restored.evidence[0].id == evidence.id
    assert {event.event_type for event in restored.activity} >= {
        "created",
        "updated",
        "evidence_added",
    }
    updated_event = next(
        event for event in restored.activity if event.event_type == "updated"
    )
    assert updated_event.details["confidence"] == {"before": 50, "after": 65}

    assert database.delete_research_evidence(evidence.id) is True
    restored = database.get_research_project(project.id)
    assert restored is not None
    assert restored.activity[0].event_type == "evidence_removed"
    assert database.delete_research_project(project.id) is True


def test_legacy_watchlist_is_migrated_without_losing_items(tmp_path) -> None:
    path = tmp_path / "legacy-watchlist.db"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE watchlist_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                object_type TEXT NOT NULL,
                object_id TEXT NOT NULL,
                name TEXT NOT NULL,
                note TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                UNIQUE(object_type, object_id)
            )
            """
        )
        connection.execute(
            """
            INSERT INTO watchlist_items
                (object_type, object_id, name, note, created_at)
            VALUES ('bond', '240011', '旧版自选', '', ?)
            """,
            (datetime.now().isoformat(),),
        )

    database = Database(path)
    item = database.list_watchlist()[0]

    assert item.name == "旧版自选"
    assert item.group_name == "默认分组"
    assert item.research_status == "draft"
    assert item.updated_at == item.created_at


def test_fred_storage_calibration_removes_values_and_preserves_reference(tmp_path) -> None:
    database = Database(tmp_path / "fred-migration.db")
    project = database.add_research_project(ResearchProjectCreate(title="旧版 FRED 研究"))
    now = datetime.now().isoformat()
    legacy_payload = {
        "frozen": True,
        "captured_at": now,
        "source_meta": {"source": "FRED"},
        "chart": {
            "dates": ["2026-07-13"],
            "series": [
                {
                    "key": "DGS10",
                    "name": "美国国债 10Y",
                    "values": [4.12],
                    "source_url": "https://fred.stlouisfed.org/series/DGS10",
                }
            ],
            "transform": "level",
            "years": 1,
        },
    }
    with database._connect() as connection:
        connection.execute(
            """
            INSERT INTO research_evidence
                (project_id, evidence_type, title, payload, source_summary,
                 observation_start, observation_end, created_at)
            VALUES (?, 'chart', '旧图表', ?, 'FRED · DGS10',
                    '2026-07-13', '2026-07-13', ?)
            """,
            (project.id, json.dumps(legacy_payload), now),
        )
    database.upsert_macro_series(
        {
            "provider": "fred",
            "series_id": "DGS10",
            "title": "DGS10",
            "fetched_at": now,
        }
    )
    database.upsert_macro_observations(
        "fred",
        "DGS10",
        [
            {
                "date": "2026-07-13",
                "value": 4.12,
                "realtime_start": "2026-07-14",
                "realtime_end": "9999-12-31",
            }
        ],
        fetched_at=now,
    )

    result = database.calibrate_fred_storage()
    evidence = database.get_research_project(project.id).evidence[0]

    assert result == {
        "evidence_migrated": 1,
        "observations_deleted": 1,
        "series_deleted": 1,
    }
    assert evidence.payload["storage_mode"] == "reference_only"
    assert evidence.payload["series"][0]["series_id"] == "DGS10"
    assert "chart" not in evidence.payload
    assert "values" not in json.dumps(evidence.payload)
    assert database.macro_stats()["points"] == 0
    assert database.calibrate_fred_storage()["evidence_migrated"] == 0


def test_fred_evidence_rejects_persisted_values_and_oversized_payloads() -> None:
    with pytest.raises(ValidationError, match="仅允许保存引用"):
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="不合规 FRED 快照",
            source_summary="FRED · DGS10",
            payload={"chart": {"values": [4.12]}},
        )
    with pytest.raises(ValidationError, match="128 KB"):
        ResearchEvidenceCreate(
            evidence_type="note",
            title="过大证据",
            payload={"note": "x" * (129 * 1024)},
        )
