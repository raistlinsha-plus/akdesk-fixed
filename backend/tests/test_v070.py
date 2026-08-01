from __future__ import annotations

import sqlite3
from datetime import date, datetime

import pytest

from app import demo_data
from app.credit import credit_coverage, evaluate_credit_observation
from app.database import Database
from app.models import (
    CreditObservationCreate,
    Dataset,
    ReleaseReviewCreate,
    ResearchEntryCreate,
    ResearchEntryUpdate,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
    ResearchProjectTemplateCreate,
    ResearchSignalSettings,
    SourceMeta,
    WatchlistCreate,
)
from app.provider import DataService
from app.release_review import evaluate_release_review
from app.research import build_market_brief
from app.research_workspace import create_project_from_template, weekly_report
from app.watchlist import enrich_watchlist


def _dataset(data, observation: str = "2026-07-15") -> Dataset:
    return Dataset(
        data=data,
        meta=SourceMeta(
            source="v0.7 test source",
            observation_time=observation,
            fetched_at=datetime.now(),
        ),
    )


def test_v070_schema_and_research_entry_lifecycle(tmp_path) -> None:
    database = Database(tmp_path / "v070.db")
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    assert {
        "research_entries",
        "research_project_origins",
        "release_reviews",
        "credit_observations",
        "app_settings",
        "world_bank_countries",
        "world_bank_indicators",
        "world_bank_observations",
    } <= tables

    project = database.add_research_project(ResearchProjectCreate(title="久期研究"))
    entry = database.add_research_entry(
        project.id,
        ResearchEntryCreate(
            entry_type="counter_evidence",
            title="供给压力",
            content="专项债发行可能快于预期",
        ),
    )
    assert entry is not None and entry.status == "open"
    updated = database.update_research_entry(entry.id, ResearchEntryUpdate(status="done"))
    assert updated is not None and updated.status == "done"
    saved = database.get_research_project(project.id)
    assert saved is not None
    assert saved.entries[0].entry_type == "counter_evidence"
    assert {item.event_type for item in saved.activity} >= {"created", "entry_added", "entry_updated"}
    assert database.delete_research_entry(entry.id) is True
    assert database.get_research_project(project.id).entries == []  # type: ignore[union-attr]


def test_schema_800_migration_preserves_v070_projects(tmp_path) -> None:
    path = tmp_path / "upgrade.db"
    database = Database(path)
    project = database.add_research_project(ResearchProjectCreate(title="升级前项目"))
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE world_bank_observations")
        connection.execute("DROP TABLE world_bank_indicators")
        connection.execute("DROP TABLE world_bank_countries")
        connection.execute("DELETE FROM schema_migrations WHERE version = 800")
        connection.execute("PRAGMA user_version=701")

    upgraded = Database(path)

    assert upgraded.get_research_project(project.id).title == "升级前项目"  # type: ignore[union-attr]
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
        assert connection.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version = 800"
        ).fetchone()[0] == 1


def test_template_export_import_and_fred_reference_boundary(tmp_path) -> None:
    database = Database(tmp_path / "projects.db")
    project = create_project_from_template(
        database,
        ResearchProjectTemplateCreate(
            template_id="macro_release",
            object_type="macro",
            object_id="CPIAUCSL",
            object_name="美国 CPI",
            source="FRED",
            observation_time="2026-06-01",
        ),
    )
    same_project = create_project_from_template(
        database,
        ResearchProjectTemplateCreate(
            template_id="macro_release",
            object_type="macro",
            object_id="CPIAUCSL",
            object_name="美国 CPI",
        ),
    )
    assert same_project.id == project.id
    assert len(database.list_research_projects()) == 1
    database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="CPI 引用",
            source_summary="FRED · CPIAUCSL",
            payload={
                "storage_mode": "reference_only",
                "series": [{"series_id": "CPIAUCSL", "source_url": "https://fred.stlouisfed.org/series/CPIAUCSL"}],
                "transform": "level",
            },
        ),
    )

    bundle = database.project_bundle(project.id)
    assert bundle is not None
    assert bundle["schema_version"] == 1
    assert "values" not in bundle["evidence"][0]["payload"]
    imported = database.import_project_bundle(bundle)
    assert imported.title.endswith("（导入）")
    assert len(imported.evidence) == 1
    assert imported.evidence[0].payload["storage_mode"] == "reference_only"
    assert any(item.event_type == "imported" for item in imported.activity)

    unsafe = database.project_bundle(project.id)
    assert unsafe is not None
    unsafe["evidence"][0]["payload"]["values"] = [1.0]
    with pytest.raises(ValueError, match="不得包含观测值"):
        database.import_project_bundle(unsafe)

    with pytest.raises(ValueError, match="不得包含观测值"):
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="绕过前缀的 FRED 快照",
            source_summary="宏观来源 · FRED",
            payload={
                "storage_mode": "reference_only",
                "provider": "fred",
                "series": [{"series_id": "DGS10", "actual_value": 4.2}],
            },
        )


def test_database_backup_restore_is_a_roundtrip(tmp_path) -> None:
    database = Database(tmp_path / "live.db")
    database.add_research_project(ResearchProjectCreate(title="备份前项目"))
    backup = tmp_path / "backup.db"
    database.backup_to(backup)
    database.add_research_project(ResearchProjectCreate(title="备份后项目"))

    database.restore_from(backup)

    assert [item.title for item in database.list_research_projects()] == ["备份前项目"]
    with sqlite3.connect(database.path) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600


def test_signal_settings_control_threshold_and_explain_trigger() -> None:
    service = DataService()
    service.cache.set(
        "money_rates",
        _dataset([
            {"name": "DR001", "value": 1.4, "change_bp": 2.0},
            {"name": "DR007", "value": 1.5, "change_bp": 2.0},
        ]),
        3_600,
    )

    quiet = build_market_brief(service, ResearchSignalSettings(funding_change_bp=3))
    sensitive = build_market_brief(service, ResearchSignalSettings(funding_change_bp=1))
    quiet_signal = next(item for item in quiet["signals"] if item["id"] == "funding-average")
    sensitive_signal = next(item for item in sensitive["signals"] if item["id"] == "funding-average")

    assert quiet_signal["severity"] == "info"
    assert sensitive_signal["severity"] == "watch"
    assert sensitive_signal["threshold"] == 1
    assert "1 BP" in sensitive_signal["trigger_reason"]
    assert sensitive["settings"]["funding_change_bp"] == 1


def test_enriched_watchlist_uses_cached_trusted_quote_and_deep_link(tmp_path) -> None:
    database = Database(tmp_path / "watch.db")
    watched = database.add_watchlist(
        WatchlistCreate(object_type="bond", object_id="240011", name="24附息国债11")
    )
    database.add_watchlist(
        WatchlistCreate(object_type="macro", object_id="DGS10", name="美国国债 10Y")
    )
    service = DataService()
    service.cache.set(
        "spot_bonds",
        _dataset([{"code": "240011", "name": "24附息国债11", "yield": 1.83, "change_bp": -0.8}]),
        3_600,
    )

    items = enrich_watchlist(service, database.list_watchlist())
    bond = next(item for item in items if item["id"] == watched.id)
    macro = next(item for item in items if item["object_type"] == "macro")
    assert bond["page"] == "bonds"
    assert bond["quote_status"] == "available"
    assert bond["quote"]["primary_value"] == 1.83
    assert bond["source_meta"]["trust_level"] == "trusted"
    assert macro["page"] == "macro" and macro["quote_status"] == "request_required"


def test_release_review_is_request_scoped_and_revision_aware(tmp_path) -> None:
    database = Database(tmp_path / "release.db")
    with database._connect() as connection:
        connection.executemany(
            """
            INSERT INTO market_history
                (adapter, series_key, label, metric, observation_time,
                 value, source, quality_score, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("treasury_futures", "T", "T2609", "price", "2026-07-13", 108.1, "test", 100, "2026-07-13T15:20:00"),
                ("treasury_futures", "T", "T2609", "price", "2026-07-14", 108.4, "test", 100, "2026-07-14T15:20:00"),
            ],
        )
    review = database.add_release_review(
        ReleaseReviewCreate(
            title="美国 CPI 复盘",
            series_id="CPIAUCSL",
            release_name="CPI",
            release_date="2026-07-14",
            observation_period="2026-06-01",
            expected_value=321.0,
            expected_unit="Index",
        )
    )

    class FakeMacroService:
        def series(self, series_id: str, *, years: int, refresh: bool) -> Dataset:
            assert (series_id, refresh) == ("CPIAUCSL", True)
            assert years >= 1
            return Dataset(
                data={
                    "observations": [
                        {
                            "date": "2026-06-01",
                            "value": 322.2,
                            "realtime_start": "2026-07-14",
                            "realtime_end": "9999-12-31",
                        }
                    ]
                },
                meta=SourceMeta(
                    source="FRED",
                    source_url="https://fred.stlouisfed.org/series/CPIAUCSL",
                    observation_time="2026-06-01",
                    fetched_at=datetime.now(),
                ),
            )

    result = evaluate_release_review(database, FakeMacroService(), review)  # type: ignore[arg-type]
    assert result["actual"]["value"] == 322.2
    assert result["surprise"] == pytest.approx(1.2)
    assert result["actual"]["persisted"] is False
    assert result["revision_status"] == "not_reviewed"
    window = result["market_window"]["series"][0]
    assert window["before"]["observation_time"] == "2026-07-13"
    assert window["after"]["observation_time"] == "2026-07-14"
    assert window["change"] == pytest.approx(0.3)
    assert database.macro_stats()["points"] == 0


def test_weekly_review_summarizes_research_cadence(tmp_path) -> None:
    database = Database(tmp_path / "weekly.db")
    project = database.add_research_project(
        ResearchProjectCreate(
            title="本周研究",
            conclusion="长端仍需等待资金面确认",
            next_review_date=date.today().isoformat(),
        )
    )
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(entry_type="note", title="资金观察"),
    )
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(entry_type="task", title="更新曲线", status="done"),
    )
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(entry_type="task", title="核对资金分位"),
    )

    report = weekly_report(database, date.today())

    assert report["summary"]["active_projects"] == 1
    assert report["summary"]["notes"] == 1
    assert report["summary"]["tasks_done"] == 1
    assert report["due_projects"][0]["title"] == "本周研究"
    assert report["conclusion_updates"][0]["conclusion"] == "长端仍需等待资金面确认"
    assert report["open_tasks"][0]["title"] == "核对资金分位"
    assert report["next_reviews"][0]["title"] == "本周研究"


def test_credit_r1_only_calculates_after_all_gates_pass(tmp_path) -> None:
    database = Database(tmp_path / "credit.db")
    eligible = database.add_credit_observation(
        CreditObservationCreate(
            bond_code="102600001",
            bond_name="示例中票",
            issuer="示例 集团（中国）有限公司",
            maturity_date="2031-07-15",
            rating="AAA",
            rating_date="2026-06-30",
            yield_pct=2.35,
            yield_observation_date="2026-07-15",
            benchmark_tenor="5Y",
            benchmark_yield_pct=1.85,
            benchmark_observation_date="2026-07-15",
            source_note="人工核验：交易中心成交与评级公告",
        )
    )
    blocked = database.add_credit_observation(
        CreditObservationCreate(
            bond_code="102600002",
            bond_name="日期错配中票",
            issuer="另一集团有限公司",
            maturity_date="2031-07-15",
            rating="AA+",
            rating_date="2026-06-30",
            yield_pct=2.55,
            yield_observation_date="2026-07-15",
            benchmark_tenor="5Y",
            benchmark_yield_pct=1.85,
            benchmark_observation_date="2026-07-14",
            source_note="人工核验",
        )
    )

    first = evaluate_credit_observation(eligible)
    second = evaluate_credit_observation(blocked)
    coverage = credit_coverage(database.list_credit_observations())

    assert first["eligible"] is True
    assert first["spread_bp"] == 50.0
    assert first["normalized_issuer"] == "示例集团(中国)有限公司"
    assert second["eligible"] is False and second["spread_bp"] is None
    assert any("同一观察日" in reason for reason in second["gate_reasons"])
    assert coverage["total"] == 2 and coverage["eligible"] == 1
    assert "不构成评级或违约概率" in first["calculation_notice"]


def test_credit_candidates_only_assist_with_trusted_market_fields() -> None:
    service = DataService()
    service.cache.set("spot_bonds", _dataset(demo_data.spot_bonds()), 3_600)
    service.cache.set("yield_curves", _dataset(demo_data.yield_curves()), 3_600)

    from app.credit import credit_candidates

    result = credit_candidates(service)
    assert result["candidates"]
    assert all(item["bond_code"] and item["yield_pct"] is not None for item in result["candidates"])
    assert "issuer" not in result["candidates"][0]
    assert set(result["benchmark_curve"]["values"]) >= {"1Y", "5Y", "10Y"}
    assert result["candidate_source"]["eligible"] is True
    assert result["benchmark_curve"]["eligible"] is True


def test_credit_candidates_reject_demo_and_partial_sources() -> None:
    service = DataService()
    demo_bonds = _dataset(demo_data.spot_bonds())
    demo_bonds.meta.demo = True
    partial_curves = _dataset(demo_data.yield_curves(), observation="")
    service.cache.set("spot_bonds", demo_bonds, 3_600)
    service.cache.set("yield_curves", partial_curves, 3_600)

    from app.credit import credit_candidates

    result = credit_candidates(service)
    assert result["candidates"] == []
    assert result["benchmark_curve"]["values"] == {}
    assert result["candidate_source"]["eligible"] is False
    assert any("演示数据" in reason for reason in result["candidate_source"]["gate_reasons"])
    assert result["benchmark_curve"]["eligible"] is False
