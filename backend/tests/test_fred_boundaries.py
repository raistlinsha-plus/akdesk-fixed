from __future__ import annotations

import json
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.database import Database
from app.models import (
    EvidenceBasketCreate,
    ReleaseReviewCreate,
    ReleaseReviewUpdate,
    ResearchEntryCreate,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
)


def reference(**extra):
    return {
        "storage_mode": "reference_only",
        "provider": "FRED",
        "series": [{"series_id": "DGS10"}],
        "years": 10,
        "transform": "level",
        **extra,
    }


@pytest.mark.parametrize(
    "payload",
    [
        reference(notes="API metadata"),
        reference(raw=[4.2]),
        reference(observation_start="2026-01-01"),
        reference(series=[{"series_id": "DGS10", "units": "Percent"}]),
        reference(series=[{"series_id": "DGS10", "name": "API series title"}]),
        reference(series=[{"series_id": "DGS10", "source_url": "https://example.com"}]),
        reference(notice="API metadata hidden in a notice"),
        reference(transform={"hidden": [4.2]}),
    ],
)
def test_reference_label_does_not_allow_api_metadata_or_arbitrary_content(payload):
    for model in (ResearchEvidenceCreate, EvidenceBasketCreate):
        with pytest.raises(ValidationError):
            model(evidence_type="chart", title="用户标题", payload=payload)


def test_fred_reference_has_only_query_parameters_and_no_observed_range(tmp_path):
    database = Database(tmp_path / "query-only.db")
    project = database.add_research_project(ResearchProjectCreate(title="用户自己的研究"))
    evidence = database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="我自己的引用标题",
            source_summary="FRED · copied API attribution",
            observation_start="2026-01-01",
            observation_end="2026-10-01",
            payload=reference(captured_at="2026-11-02T10:30:00+08:00"),
        ),
    )
    assert evidence.title == "我自己的引用标题"
    assert evidence.source_summary == "FRED · DGS10"
    assert evidence.observation_start is None and evidence.observation_end is None
    assert evidence.payload["schema_version"] == 3
    assert evidence.payload["series"] == [{
        "series_id": "DGS10",
        "source_url": "https://fred.stlouisfed.org/series/DGS10",
    }]
    summary = database.project_summary(project.id)["supporting_evidence"][0]
    assert summary["provider"] == "FRED"
    assert summary["ai_processing_allowed"] is False
    assert "payload" not in summary
    assert "copied API attribution" not in json.dumps(database.project_bundle(project.id))


def seed_legacy_content(database):
    project = database.add_research_project(ResearchProjectCreate(
        title="用户项目", conclusion="我的独立判断，不应被迁移删掉"
    ))
    database.add_research_entry(project.id, ResearchEntryCreate(
        title="用户笔记", content="我自己写的 FRED 使用方法与研究分歧。"
    ))
    review = database.add_release_review(ReleaseReviewCreate(
        title="用户发布复盘", series_id="DGS10", release_date="2026-01-01",
        observation_period="2026-01-01", expected_value=4.2,
        notes="用户自己记录的发布前预期与理由",
    ))
    now = datetime.now().isoformat()
    payload = reference(
        schema_version=2,
        notes="API_NOTES_DO_NOT_ARCHIVE",
        series=[{
            "series_id": "DGS10", "name": "API_TITLE_DO_NOT_ARCHIVE",
            "units": "API_UNITS", "last_updated": "2026-10-21",
            "values": [4.12345],
        }],
    )
    with database._connect() as connection:
        connection.execute(
            "UPDATE release_reviews SET reviewed_realtime_start = ?, reviewed_at = ? WHERE id = ?",
            ("2026-10-21", "2026-11-02T12:34:56+08:00", review.id),
        )
        connection.execute(
            """INSERT INTO research_evidence
               (project_id,evidence_type,title,payload,source_summary,
                observation_start,observation_end,created_at)
               VALUES (?,'chart','用户自写证据标题',?,'FRED · DGS10',
                       '2026-01-01','2026-10-21',?)""",
            (project.id, json.dumps(payload), now),
        )
        connection.execute(
            """INSERT INTO research_evidence_basket
               (evidence_type,title,payload,source_summary,
                observation_start,observation_end,created_at)
               VALUES ('chart','用户证据篮标题',?,'FRED · DGS10',
                       '2026-01-01','2026-10-21',?)""",
            (json.dumps(payload), now),
        )
    database.upsert_macro_series({
        "provider": "fred", "series_id": "DGS10", "title": "API_TITLE",
        "notes": "API_NOTES", "fetched_at": now,
    })
    database.upsert_macro_observations("fred", "DGS10", [{
        "date": "2026-01-01", "value": 4.12345,
    }], fetched_at=now)
    return project.id


def assert_calibrated(database, project_id):
    project = database.get_research_project(project_id)
    assert project.title == "用户项目"
    assert project.conclusion == "我的独立判断，不应被迁移删掉"
    assert project.entries[0].content == "我自己写的 FRED 使用方法与研究分歧。"
    assert project.evidence[0].title == "用户自写证据标题"
    review = database.list_release_reviews()[0]
    assert review.reviewed_realtime_start is None
    assert review.reviewed_at.isoformat() == "2026-11-02T12:34:56+08:00"
    assert review.notes == "用户自己记录的发布前预期与理由"
    assert review.expected_value == 4.2
    with database._connect() as connection:
        assert connection.execute(
            "SELECT reviewed_realtime_start FROM release_reviews WHERE id = ?",
            (review.id,),
        ).fetchone()[0] is None
    basket = database.list_evidence_basket()[0]
    assert basket.title == "用户证据篮标题"
    for item in (project.evidence[0], basket):
        encoded = json.dumps(item.payload)
        assert item.payload["schema_version"] == 3
        assert item.observation_start is None and item.observation_end is None
        assert not any(text in encoded for text in (
            "API_NOTES", "API_TITLE", "API_UNITS", "4.12345", "2026-10-21"
        ))
    assert database.macro_stats()["points"] == 0
    assert database.macro_stats()["series"] == 0
    assert database.calibrate_fred_storage()["evidence_migrated"] == 0


def test_calibration_revisits_old_reference_only_rows_and_preserves_user_notes(tmp_path):
    database = Database(tmp_path / "legacy.db")
    project_id = seed_legacy_content(database)
    result = database.calibrate_fred_storage()
    assert result == {
        "evidence_migrated": 2, "observations_deleted": 1, "series_deleted": 1
    }
    assert_calibrated(database, project_id)


def test_restore_calibrates_only_working_copy_before_it_can_be_exported(tmp_path, monkeypatch):
    old = Database(tmp_path / "old-working.db")
    project_id = seed_legacy_content(old)
    backup = tmp_path / "user-supplied-backup.db"
    old.backup_to(backup)
    original_bytes = backup.read_bytes()
    restored = Database(tmp_path / "restored-working.db")
    restored.add_research_project(ResearchProjectCreate(title="恢复前的干净工作区"))
    concurrent_backup = tmp_path / "automatic-backup-during-calibration.db"
    calibrate = Database.calibrate_fred_storage

    def calibrate_while_backup_runs(staged):
        # Simulate the scheduler precisely between copy and calibration. It
        # must still see the previous live database, not the unclean backup.
        if staged.path != restored.path:
            restored.backup_to(concurrent_backup)
        return calibrate(staged)

    monkeypatch.setattr(Database, "calibrate_fred_storage", calibrate_while_backup_runs)
    restored.restore_from(backup)
    monkeypatch.setattr(Database, "calibrate_fred_storage", calibrate)
    during_restore = Database(concurrent_backup)
    assert [item.title for item in during_restore.list_research_projects()] == ["恢复前的干净工作区"]
    assert during_restore.macro_stats()["points"] == 0
    assert_calibrated(restored, project_id)
    assert backup.read_bytes() == original_bytes
    assert not list(tmp_path.glob(".akdesk-restore-*"))
    rebackup = tmp_path / "new-backup.db"
    restored.backup_to(rebackup)
    assert_calibrated(Database(rebackup), project_id)


def test_project_import_cannot_reintroduce_fred_metadata(tmp_path):
    database = Database(tmp_path / "import.db")
    project = database.add_research_project(ResearchProjectCreate(title="用户项目"))
    database.add_research_evidence(project.id, ResearchEvidenceCreate(
        evidence_type="chart", title="引用", payload=reference()
    ))
    bundle = database.project_bundle(project.id)
    bundle["evidence"][0]["payload"]["series"][0]["notes"] = "API_NOTES"
    with pytest.raises(ValueError):
        database.import_project_bundle(bundle)


def test_release_review_rejects_api_vintage_but_keeps_user_local_review_time(tmp_path):
    with pytest.raises(ValidationError, match="官方版本时点不得持久化"):
        ReleaseReviewUpdate(reviewed_realtime_start="2026-10-21")
    database = Database(tmp_path / "review-boundary.db")
    review = database.add_release_review(ReleaseReviewCreate(
        title="用户预期", series_id="DGS10", release_date="2026-01-01",
        observation_period="2026-01-01", expected_value=4.2, notes="个人判断",
    ))
    timestamp = datetime.fromisoformat("2026-11-02T12:34:56+08:00")
    saved = database.update_release_review(review.id, ReleaseReviewUpdate(reviewed_at=timestamp))
    assert saved.reviewed_at == timestamp
    assert saved.reviewed_realtime_start is None
    bypass = ReleaseReviewUpdate().model_copy(update={"reviewed_realtime_start": "2026-10-21"})
    with pytest.raises(ValueError, match="官方版本时点不得持久化"):
        database.update_release_review(review.id, bypass)
    changed = database.update_release_review(review.id, ReleaseReviewUpdate(notes="用户补充"))
    assert changed.reviewed_at == timestamp
    assert changed.notes == "用户补充"


def test_failed_restore_calibration_leaves_live_and_source_unchanged(tmp_path, monkeypatch):
    missing = tmp_path / "does-not-exist.db"
    with pytest.raises(ValueError, match="只读检查"):
        Database.validate_backup(missing)
    assert not missing.exists()
    old = Database(tmp_path / "old.db")
    seed_legacy_content(old)
    backup = tmp_path / "source.db"
    old.backup_to(backup)
    before = backup.read_bytes()
    live = Database(tmp_path / "live.db")
    live.add_research_project(ResearchProjectCreate(title="保留当前工作区"))

    def reject_calibration(_database):
        raise ValueError("模拟校准失败")

    monkeypatch.setattr(Database, "calibrate_fred_storage", reject_calibration)
    with pytest.raises(ValueError, match="模拟校准失败"):
        live.restore_from(backup)
    assert [item.title for item in live.list_research_projects()] == ["保留当前工作区"]
    assert backup.read_bytes() == before
    assert not list(tmp_path.glob(".akdesk-restore-*"))


def test_calibration_does_not_misclassify_alfred_or_foreign_url_queries(tmp_path):
    database = Database(tmp_path / "unrelated.db")
    project = database.add_research_project(ResearchProjectCreate(title="非 FRED 研究"))
    payload = {
        "provider": "Alfred",
        "source_url": "https://example.com/research?name=fred",
        "terms_url": "https://stlouisfed.org.example.com/?service=FRED",
        "notes": "用户自己整理的元数据，必须保留",
        "values": [7.125],
    }
    evidence = database.add_research_evidence(project.id, ResearchEvidenceCreate(
        evidence_type="snapshot", title="Alfred 资料",
        source_summary="Alfred · https://example.com/?provider=FRED",
        observation_start="2026-01-01", payload=payload,
    ))
    result = database.calibrate_fred_storage()
    assert result["evidence_migrated"] == 0
    saved = database.get_research_project(project.id).evidence[0]
    assert saved.id == evidence.id and saved.payload == payload
    assert saved.observation_start == "2026-01-01"
    assert database.project_summary(project.id)["supporting_evidence"][0]["ai_processing_allowed"] is True


@pytest.mark.parametrize("identity", [
    {"provider": "fred"},
    {"adapter": "fred_macro"},
    {"component_type": "fred_chart"},
    {"source_url": "https://fred.stlouisfed.org/series/DGS10"},
    {"source_url": "https://api.stlouisfed.org/fred/series"},
])
def test_real_fred_markers_cannot_bypass_the_content_boundary(identity):
    with pytest.raises(ValidationError, match="仅允许保存引用"):
        ResearchEvidenceCreate(
            evidence_type="snapshot", title="受限来源", source_summary="通用来源",
            payload={**identity, "notes": "API_METADATA"},
        )
