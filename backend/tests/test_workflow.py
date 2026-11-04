from __future__ import annotations

import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import workflow
from app.database import Database
from app.models import (
    ResearchEntryCreate,
    ResearchEntryUpdate,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
    ResearchProjectUpdate,
    ResearchTopicCreate,
    ReviewCheckpointCreate,
    WorkflowCaptureCreate,
)


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(workflow, "_today", lambda: date(2026, 11, 4))
    database = Database(tmp_path / "workflow.db")
    project = database.add_research_project(
        ResearchProjectCreate(title="临时研究项目", question="问题")
    )
    return database, project


def brief_request(**overrides):
    return WorkflowCaptureCreate.model_validate(
        {
            "kind": "brief_note",
            "request_id": str(uuid4()),
            "confirmed": True,
            "report_date": "2026-11-04",
            "note": "我独立写的复盘备注",
            **overrides,
        }
    )


def market_request(**overrides):
    return WorkflowCaptureCreate.model_validate(
        {
            "kind": "market_signal",
            "request_id": str(uuid4()),
            "confirmed": True,
            "signal_id": "curve-10y",
            "expected_fetched_at": "2026-11-04T10:00:00+08:00",
            "note": "自己的核验思路",
            **overrides,
        }
    )


def signal_fixture(**overrides):
    return {
        "id": "curve-10y",
        "category": "curve",
        "title": "10Y 样例变化",
        "summary": "测试合成变化，非真实行情",
        "value": -2.0,
        "unit": "BP",
        "object_type": None,
        "object_id": None,
        "object_name": None,
        "adapter": "yield_curves",
        "source": "测试合成源",
        "source_url": "https://example.com/curve?api_key=secret#private",
        "observation_time": "2026-11-04",
        "fetched_at": "2026-11-04T10:00:00+08:00",
        "trust_level": "trusted",
        "quality_score": 100,
        "data_state": "latest",
        "demo": False,
        "actionable": True,
        **overrides,
    }


def trusted_service():
    cached = SimpleNamespace(
        meta=SimpleNamespace(
            fetched_at=datetime.fromisoformat("2026-11-04T10:00:00+08:00")
        )
    )
    return SimpleNamespace(_cached_dataset=lambda _adapter, **_kwargs: cached)


def checkpoint(database, project_id, note=""):
    delta = workflow.review_delta(database, project_id)
    return workflow.review_checkpoint(
        database,
        project_id,
        ReviewCheckpointCreate(
            expected_fingerprint=delta["fingerprint"], confirmed=True, note=note
        ),
    )


def test_read_delta_does_not_write_or_consult_any_provider(workspace):
    database, project = workspace
    before = database.path.read_bytes()
    delta = workflow.review_delta(database, project.id)
    assert delta["baseline"] is None
    assert delta["counts"]["project_changed"] is False
    assert delta["counts"]["new_entries"] == 0
    assert database.path.read_bytes() == before
    with database._connect() as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM app_settings WHERE setting_key LIKE 'workflow.%'"
            ).fetchone()[0]
            == 0
        )
    assert "不调用外部数据或AI" in delta["notice"]


def test_brief_note_saves_only_explicit_manual_text_and_is_idempotent(workspace):
    database, project = workspace
    request = brief_request(note="字" * 8000)
    saved = workflow.workflow_capture(database, None, project.id, request)
    retry = workflow.workflow_capture(database, None, project.id, request)
    assert retry == {**saved, "deduplicated": True}
    project = database.get_research_project(project.id)
    assert len(project.entries) == 1
    assert project.entries[0].title == "简报备注 · 2026-11-04"
    assert project.entries[0].content == "字" * 8000
    assert project.evidence == []
    with database._connect() as connection:
        setting = connection.execute(
            "SELECT payload FROM app_settings WHERE setting_key LIKE 'workflow.capture:%'"
        ).fetchone()[0]
    assert "字字" not in setting
    assert "request_hash" in setting


def test_same_request_identifier_with_different_content_or_project_conflicts(workspace):
    database, project = workspace
    request = brief_request()
    workflow.workflow_capture(database, None, project.id, request)
    other = database.add_research_project(ResearchProjectCreate(title="第二项目"))
    for project_id, payload in (
        (project.id, request.model_copy(update={"note": "不同内容"})),
        (other.id, request),
    ):
        with pytest.raises(workflow.WorkflowConflict, match="标识"):
            workflow.workflow_capture(database, None, project_id, payload)
    assert len(database.get_research_project(project.id).entries) == 1
    assert database.get_research_project(other.id).entries == []


def test_concurrent_retries_create_one_entry_and_one_receipt(workspace):
    database, project = workspace
    request = brief_request()
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: workflow.workflow_capture(
                    database, None, project.id, request
                ),
                range(6),
            )
        )
    assert len({row["entry_id"] for row in results}) == 1
    assert sum(not row["deduplicated"] for row in results) == 1
    assert len(database.get_research_project(project.id).entries) == 1


def test_market_capture_uses_current_server_signal_not_client_numbers(
    workspace, monkeypatch
):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    saved = workflow.workflow_capture(
        database, trusted_service(), project.id, market_request()
    )
    project = database.get_research_project(project.id)
    assert saved["evidence_id"] == project.evidence[0].id
    assert project.entries[0].content == "自己的核验思路"
    payload = project.evidence[0].payload
    assert len(payload["signals"]) == 1
    assert payload["signals"][0]["value"] == -2
    assert payload["signals"][0]["source_url"] == "https://example.com/curve"
    assert "secret" not in json.dumps(payload)


def test_response_lost_retry_is_resolved_before_consulting_changed_market(
    workspace, monkeypatch
):
    database, project = workspace
    request = market_request()
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    saved = workflow.workflow_capture(database, trusted_service(), project.id, request)
    monkeypatch.setattr(
        workflow,
        "build_market_brief",
        lambda *_: pytest.fail("retry must not consult market"),
    )
    retry = workflow.workflow_capture(database, None, project.id, request)
    assert retry == {**saved, "deduplicated": True}
    assert len(database.get_research_project(project.id).evidence) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"demo": True},
        {"actionable": False},
        {"trust_level": "partial"},
        {"data_state": "stale"},
        {"observation_time": None},
        {"observation_time": "2026-11-05"},
        {"observation_time": "2026-10-01"},
        {"value": None},
        {"value": float("nan")},
        {"source": "FRED"},
        {"category": "macro"},
    ],
)
def test_unsafe_market_signals_never_become_research_evidence(
    workspace, monkeypatch, changes
):
    database, project = workspace
    monkeypatch.setattr(
        workflow,
        "build_market_brief",
        lambda *_: {"signals": [signal_fixture(**changes)]},
    )
    with pytest.raises(workflow.WorkflowConflict):
        workflow.workflow_capture(
            database, trusted_service(), project.id, market_request()
        )
    saved = database.get_research_project(project.id)
    assert saved.entries == [] and saved.evidence == []


def test_stale_preview_and_expired_cache_are_rejected(workspace, monkeypatch):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    with pytest.raises(workflow.WorkflowConflict, match="时点"):
        workflow.workflow_capture(
            database,
            trusted_service(),
            project.id,
            market_request(expected_fetched_at="2026-11-04T09:00:00+08:00"),
        )
    with pytest.raises(workflow.WorkflowConflict, match="缓存已过期"):
        workflow.workflow_capture(
            database,
            SimpleNamespace(_cached_dataset=lambda *_args, **_kwargs: None),
            project.id,
            market_request(),
        )
    assert database.get_research_project(project.id).entries == []


def test_market_cache_changed_during_confirmation_requires_new_preview(
    workspace, monkeypatch
):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    cached = SimpleNamespace(
        meta=SimpleNamespace(
            fetched_at=datetime.fromisoformat("2026-11-04T10:01:00+08:00")
        )
    )
    service = SimpleNamespace(_cached_dataset=lambda *_args, **_kwargs: cached)
    with pytest.raises(workflow.WorkflowConflict, match="确认过程中已更新"):
        workflow.workflow_capture(database, service, project.id, market_request())
    assert database.get_research_project(project.id).entries == []


def test_capture_failure_rolls_back_entry_evidence_activity_and_receipt(
    workspace, monkeypatch
):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    monkeypatch.setattr(
        workflow,
        "_save_setting",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("simulated storage failure")),
    )
    with pytest.raises(RuntimeError, match="storage"):
        workflow.workflow_capture(
            database, trusted_service(), project.id, market_request()
        )
    saved = database.get_research_project(project.id)
    assert saved.entries == [] and saved.evidence == [] and len(saved.activity) == 1


def test_deleted_capture_is_not_resurrected_or_claimed_present(workspace):
    database, project = workspace
    request = brief_request()
    saved = workflow.workflow_capture(database, None, project.id, request)
    database.delete_research_entry(saved["entry_id"])
    with pytest.raises(workflow.WorkflowConflict, match="删除"):
        workflow.workflow_capture(database, None, project.id, request)
    assert database.get_research_project(project.id).entries == []


def test_deleted_market_evidence_retry_does_not_claim_capture_present(
    workspace, monkeypatch
):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    request = market_request()
    saved = workflow.workflow_capture(database, trusted_service(), project.id, request)
    database.delete_research_evidence(saved["evidence_id"])
    monkeypatch.setattr(
        workflow,
        "build_market_brief",
        lambda *_: pytest.fail("deleted receipt retry must not re-fetch market"),
    )
    with pytest.raises(workflow.WorkflowConflict, match="证据已被删除"):
        workflow.workflow_capture(database, None, project.id, request)
    assert database.get_research_project(project.id).evidence == []


def test_checkpoint_records_hashes_only_and_retry_does_not_add_review(workspace):
    database, project = workspace
    database.add_research_entry(
        project.id,
        ResearchEntryCreate(title="个人笔记", content="不应复制到基线的正文"),
    )
    delta = workflow.review_delta(database, project.id)
    request = ReviewCheckpointCreate(
        expected_fingerprint=delta["fingerprint"],
        confirmed=True,
        note="自己确认过本次资料",
    )
    saved = workflow.review_checkpoint(database, project.id, request)
    retry = workflow.review_checkpoint(database, project.id, request)
    assert retry["baseline"] == saved["baseline"]
    assert saved["counts"]["new_entries"] == 0
    assert len(database.get_research_project(project.id).entries) == 2
    raw = database.get_setting(f"workflow.review:{project.id}", {})
    assert "不应复制到基线的正文" not in json.dumps(raw, ensure_ascii=False)
    assert "自己确认过" not in json.dumps(raw, ensure_ascii=False)
    assert "hashes" in raw


def test_concurrent_checkpoint_confirmations_create_one_review_entry(workspace):
    database, project = workspace
    delta = workflow.review_delta(database, project.id)
    request = ReviewCheckpointCreate(
        expected_fingerprint=delta["fingerprint"], confirmed=True, note="人工确认"
    )
    with ThreadPoolExecutor(max_workers=6) as pool:
        results = list(
            pool.map(
                lambda _: workflow.review_checkpoint(database, project.id, request),
                range(6),
            )
        )
    assert len({item["baseline"]["entry_id"] for item in results}) == 1
    assert len(database.get_research_project(project.id).entries) == 1


@pytest.mark.parametrize("bad_keys", ["not-an-id", "9" * 5000])
def test_corrupt_baseline_never_gets_silently_overwritten(workspace, bad_keys):
    database, project = workspace
    checkpoint(database, project.id)
    key = f"workflow.review:{project.id}"
    baseline = database.get_setting(key, {})
    baseline["hashes"]["entries"] = {bad_keys: "a" * 64}
    with database._connect() as connection:
        connection.execute(
            "UPDATE app_settings SET payload=? WHERE setting_key=?",
            (json.dumps(baseline), key),
        )
    with pytest.raises(workflow.WorkflowConflict, match="基线损坏"):
        workflow.review_delta(database, project.id)
    assert database.get_setting(key, {}) == baseline


@pytest.mark.parametrize("missing_kind", ["project", "entries", "evidence"])
def test_incomplete_baseline_hash_maps_reject_read_and_confirmation(
    workspace, missing_kind
):
    database, project = workspace
    checkpoint(database, project.id)
    preview = workflow.review_delta(database, project.id)
    key = f"workflow.review:{project.id}"
    baseline = database.get_setting(key, {})
    baseline["hashes"].pop(missing_kind)
    with database._connect() as connection:
        connection.execute(
            "UPDATE app_settings SET payload=? WHERE setting_key=?",
            (json.dumps(baseline), key),
        )
    for operation in (
        lambda: workflow.review_delta(database, project.id),
        lambda: workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=preview["fingerprint"], confirmed=True
            ),
        ),
    ):
        with pytest.raises(workflow.WorkflowConflict, match="基线损坏"):
            operation()
    assert database.get_setting(key, {}) == baseline
    assert len(database.get_research_project(project.id).entries) == 1


def test_corrupt_capture_receipt_does_not_recreate_entry(workspace):
    database, project = workspace
    request = brief_request()
    workflow.workflow_capture(database, None, project.id, request)
    key = f"workflow.capture:{request.request_id}"
    receipt = database.get_setting(key, {})
    receipt.pop("entry_id")
    with database._connect() as connection:
        connection.execute(
            "UPDATE app_settings SET payload=? WHERE setting_key=?",
            (json.dumps(receipt), key),
        )
    with pytest.raises(workflow.WorkflowConflict, match="回执损坏"):
        workflow.workflow_capture(database, None, project.id, request)
    assert len(database.get_research_project(project.id).entries) == 1


@pytest.mark.parametrize(
    "kind,invalid_evidence_id",
    [
        ("market_signal", "missing"),
        ("market_signal", None),
        ("market_signal", True),
        ("market_signal", 0),
        ("market_signal", "1"),
        ("brief_note", "missing"),
        ("brief_note", 1),
    ],
)
def test_receipt_evidence_field_must_match_capture_kind(
    workspace, monkeypatch, kind, invalid_evidence_id
):
    database, project = workspace
    monkeypatch.setattr(
        workflow, "build_market_brief", lambda *_: {"signals": [signal_fixture()]}
    )
    request = market_request() if kind == "market_signal" else brief_request()
    saved = workflow.workflow_capture(database, trusted_service(), project.id, request)
    if saved["evidence_id"] is not None:
        database.delete_research_evidence(saved["evidence_id"])
    key = f"workflow.capture:{request.request_id}"
    receipt = database.get_setting(key, {})
    if invalid_evidence_id == "missing":
        receipt.pop("evidence_id")
    else:
        receipt["evidence_id"] = invalid_evidence_id
    with database._connect() as connection:
        connection.execute(
            "UPDATE app_settings SET payload=? WHERE setting_key=?",
            (json.dumps(receipt), key),
        )
    monkeypatch.setattr(
        workflow,
        "build_market_brief",
        lambda *_: pytest.fail("damaged receipt must not re-fetch or recreate capture"),
    )
    with pytest.raises(workflow.WorkflowConflict, match="回执损坏"):
        workflow.workflow_capture(database, None, project.id, request)
    assert database.get_setting(key, {}) == receipt
    current = database.get_research_project(project.id)
    assert len(current.entries) == 1 and current.evidence == []


def test_empty_checkpoint_is_corruption_not_a_first_review(workspace):
    database, project = workspace
    before = workflow.review_delta(database, project.id)
    with database._connect() as connection:
        workflow._save_setting(
            connection,
            f"workflow.review:{project.id}",
            {},
            "2026-11-04T10:00:00",
        )
    for operation in (
        lambda: workflow.review_delta(database, project.id),
        lambda: workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=before["fingerprint"], confirmed=True
            ),
        ),
    ):
        with pytest.raises(workflow.WorkflowConflict, match="基线损坏"):
            operation()
    assert database.get_research_project(project.id).entries == []


def test_archived_project_allows_only_existing_capture_receipt_retry(workspace):
    database, project = workspace
    request = brief_request()
    saved = workflow.workflow_capture(database, None, project.id, request)
    database.update_research_project(
        project.id, ResearchProjectUpdate(status="archived")
    )
    assert workflow.workflow_capture(database, None, project.id, request) == {
        **saved,
        "deduplicated": True,
    }
    with pytest.raises(workflow.WorkflowConflict, match="归档"):
        workflow.workflow_capture(database, None, project.id, brief_request())
    assert len(database.get_research_project(project.id).entries) == 1


@pytest.mark.parametrize("change", ["entry", "evidence", "delete", "project"])
def test_checkpoint_rejects_unseen_content_changes(workspace, change):
    database, project = workspace
    entry = database.add_research_entry(project.id, ResearchEntryCreate(title="原记录"))
    old = workflow.review_delta(database, project.id)["fingerprint"]
    if change == "entry":
        database.update_research_entry(entry.id, ResearchEntryUpdate(content="新内容"))
    elif change == "evidence":
        database.add_research_evidence(
            project.id, ResearchEvidenceCreate(evidence_type="note", title="新证据")
        )
    elif change == "delete":
        database.delete_research_entry(entry.id)
    else:
        database.update_research_project(
            project.id, ResearchProjectUpdate(conclusion="新的人工观点")
        )
    with pytest.raises(workflow.WorkflowConflict, match="已发生变化"):
        workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(expected_fingerprint=old, confirmed=True),
        )
    assert database.get_setting(f"workflow.review:{project.id}", {}) == {}


def test_review_delta_tracks_add_edit_remove_tasks_and_project_fields(workspace):
    database, project = workspace
    old_entry = database.add_research_entry(
        project.id, ResearchEntryCreate(title="待修改")
    )
    old_evidence = database.add_research_evidence(
        project.id, ResearchEvidenceCreate(evidence_type="note", title="待删除证据")
    )
    checkpoint(database, project.id)
    database.update_research_entry(old_entry.id, ResearchEntryUpdate(content="已更新"))
    task = database.add_research_entry(
        project.id,
        ResearchEntryCreate(entry_type="task", title="待办", due_date="2026-11-03"),
    )
    database.delete_research_evidence(old_evidence.id)
    database.update_research_project(
        project.id, ResearchProjectUpdate(conclusion="人工观点变化")
    )
    delta = workflow.review_delta(database, project.id)
    assert delta["counts"]["new_entries"] == 1
    assert delta["counts"]["updated_entries"] == 1
    assert delta["counts"]["removed_evidence"] == 1
    assert delta["counts"]["project_changed"] is True
    assert delta["changes"]["removed_evidence_ids"] == [old_evidence.id]
    assert delta["open_tasks"] == [
        {"id": task.id, "title": "待办", "due_date": "2026-11-03", "overdue": True}
    ]


@pytest.mark.parametrize("association", ["object", "topic"])
def test_project_association_additions_and_removals_invalidate_checkpoint(
    workspace, association
):
    database, project = workspace
    if association == "object":
        target = database.upsert_research_object(
            object_type="macro_theme", object_key="test-object", name="关联对象"
        )
        table, column = "research_project_objects", "object_id"
    else:
        target = database.add_research_topic(
            ResearchTopicCreate(
                title="关联专题", object_key="test-topic", object_name="专题对象"
            )
        )
        table, column = "research_topic_projects", "topic_id"
    checkpoint(database, project.id)
    before_add = workflow.review_delta(database, project.id)
    with database._connect() as connection:
        connection.execute(
            f"INSERT INTO {table}(project_id,{column},created_at) VALUES(?,?,?)",
            (project.id, target.id, "2026-11-04T10:00:00"),
        )
    assert workflow.review_delta(database, project.id)["counts"]["project_changed"]
    with pytest.raises(workflow.WorkflowConflict, match="已发生变化"):
        workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=before_add["fingerprint"], confirmed=True
            ),
        )
    checkpoint(database, project.id)
    before_remove = workflow.review_delta(database, project.id)
    with database._connect() as connection:
        connection.execute(
            f"DELETE FROM {table} WHERE project_id=? AND {column}=?",
            (project.id, target.id),
        )
    assert workflow.review_delta(database, project.id)["counts"]["project_changed"]
    with pytest.raises(workflow.WorkflowConflict, match="已发生变化"):
        workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=before_remove["fingerprint"], confirmed=True
            ),
        )


def test_evidence_dates_are_not_inferred_from_save_time_or_fred_reference(workspace):
    database, project = workspace
    for title, observed in (
        ("无观测日", None),
        ("旧快照", "2026-10-01"),
        ("带时区", "2026-11-03T18:00:00Z"),
        ("未来快照", "2026-12-01"),
    ):
        database.add_research_evidence(
            project.id,
            ResearchEvidenceCreate(
                evidence_type="snapshot", title=title, observation_end=observed
            ),
        )
    database.add_research_evidence(
        project.id,
        ResearchEvidenceCreate(
            evidence_type="chart",
            title="FRED查询引用",
            source_summary="FRED",
            payload={
                "storage_mode": "reference_only",
                "series": [{"series_id": "DGS10"}],
                "years": 1,
                "transform": "level",
            },
        ),
    )
    rows = {
        row["title"]: row
        for row in workflow.review_delta(database, project.id)["evidence_status"]
    }
    assert rows["无观测日"]["status"] == "missing_time"
    assert rows["旧快照"]["status"] == "expired"
    assert rows["带时区"]["status"] == "snapshot"
    assert rows["带时区"]["observation_date"] == "2026-11-04"
    assert rows["未来快照"]["status"] == "needs_verification"
    assert rows["FRED查询引用"]["status"] == "reference_only"
    assert rows["FRED查询引用"]["observation_date"] is None


def test_archived_and_missing_projects_reject_new_writes(workspace):
    database, project = workspace
    before = workflow.review_delta(database, project.id)
    database.update_research_project(
        project.id, ResearchProjectUpdate(status="archived")
    )
    with pytest.raises(workflow.WorkflowConflict, match="归档"):
        workflow.workflow_capture(database, None, project.id, brief_request())
    with pytest.raises(workflow.WorkflowConflict):
        workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=before["fingerprint"], confirmed=True
            ),
        )
    with pytest.raises(workflow.WorkflowNotFound):
        workflow.review_delta(database, 999999)


def test_checkpoint_failure_rolls_back_review_entry_and_baseline(
    workspace, monkeypatch
):
    database, project = workspace
    delta = workflow.review_delta(database, project.id)
    monkeypatch.setattr(
        workflow,
        "_save_setting",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("checkpoint failed")),
    )
    with pytest.raises(RuntimeError):
        workflow.review_checkpoint(
            database,
            project.id,
            ReviewCheckpointCreate(
                expected_fingerprint=delta["fingerprint"], confirmed=True
            ),
        )
    assert database.get_research_project(project.id).entries == []
    assert database.get_setting(f"workflow.review:{project.id}", {}) == {}


def test_delta_rows_are_bounded_while_counts_cover_all_records(workspace):
    database, project = workspace
    with database._connect() as connection:
        connection.executemany(
            "INSERT INTO research_entries(project_id,entry_type,title,content,status,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
            [
                (
                    project.id,
                    "task",
                    f"任务{index}",
                    "",
                    "open",
                    None,
                    "2026-11-04T01:00:00",
                    "2026-11-04T01:00:00",
                )
                for index in range(120)
            ],
        )
    delta = workflow.review_delta(database, project.id)
    assert delta["counts"]["new_entries"] == 120
    assert delta["counts"]["open_tasks"] == 120
    assert len(delta["changes"]["entries"]) == 100 and len(delta["open_tasks"]) == 100
    assert delta["truncated"]["entries"] and delta["truncated"]["tasks"]


@pytest.mark.parametrize(
    "payload",
    [
        {"confirmed": False},
        {"confirmed": 1},
        {"confirmed": True, "note": "", "report_date": "2026-11-04"},
        {"confirmed": True, "note": "手写", "report_date": "2026-02-31"},
        {
            "confirmed": True,
            "note": "手写",
            "report_date": "2026-11-04",
            "payload": {"values": [987]},
        },
    ],
)
def test_capture_rejects_implicit_confirmation_invalid_dates_and_injected_payloads(
    payload,
):
    with pytest.raises(ValidationError):
        WorkflowCaptureCreate.model_validate(
            {"kind": "brief_note", "request_id": str(uuid4()), **payload}
        )


def test_api_workflow_status_codes_and_read_only_routes(
    workspace, monkeypatch, tmp_path
):
    database, project = workspace
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path / "isolated-api"))
    monkeypatch.setenv("AKDESK_DEMO", "1")
    monkeypatch.setenv("AKDESK_NO_BROWSER", "1")
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    monkeypatch.setattr(main, "database", database)
    client = TestClient(main.app)
    assert (
        client.get(f"/api/v1/research/projects/{project.id}/review-delta").status_code
        == 200
    )
    assert (
        client.get("/api/v1/research/projects/999999/review-delta").status_code == 404
    )
    base = f"/api/v1/research/projects/{project.id}"
    request = brief_request()
    response = client.post(
        base + "/workflow-capture", json=request.model_dump(mode="json")
    )
    assert response.status_code == 200 and response.json()["evidence_id"] is None
    assert (
        client.post(
            base + "/workflow-capture",
            json={**request.model_dump(mode="json"), "note": "changed"},
        ).status_code
        == 409
    )
    assert (
        client.post(
            base + "/workflow-capture",
            json={**request.model_dump(mode="json"), "confirmed": False},
        ).status_code
        == 422
    )
    delta = client.get(base + "/review-delta").json()
    response = client.post(
        base + "/review-checkpoint",
        json={"expected_fingerprint": delta["fingerprint"], "confirmed": True},
    )
    assert response.status_code == 200 and response.json()["baseline"]["entry_id"]
