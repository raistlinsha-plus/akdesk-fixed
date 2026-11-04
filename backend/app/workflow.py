"""Explicit, local-only research capture and hash-only review checkpoints.

Uses the existing transactional app_settings store; no schema migration, new
credentials, background network calls or copied FRED payloads are introduced.
"""

from __future__ import annotations

import hashlib
import json
import math
import sqlite3
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from pydantic import ValidationError

from .models import (
    ResearchEntryCreate,
    ResearchEvidenceCreate,
    ReviewCheckpointCreate,
    WorkflowCaptureCreate,
    _is_fred_evidence,
)
from .research import build_market_brief

if TYPE_CHECKING:
    from .database import Database
    from .provider import DataService
    from .models import ResearchSignalSettings

MAX_ROWS = 100
SNAPSHOT_REVIEW_DAYS = 7
NOTICE = (
    "仅比较本地项目与上次主动确认的哈希基线；首次复盘没有历史基线。"
    "近期快照仍需核验，7天只是人工复核提示窗口，不代表数据实时性、授权或业务有效性。"
    "FRED查询引用不是已保存的官方数据版本，重新请求可能修订；本页不调用外部数据或AI。"
)


class WorkflowConflict(ValueError):
    pass


class WorkflowNotFound(LookupError):
    pass


def _digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=False,
            default=str,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


def _source_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        if (
            parsed.scheme not in {"https", "http"}
            or not parsed.hostname
            or parsed.username is not None
            or parsed.password is not None
        ):
            return None
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return None


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


def _load_setting(connection: sqlite3.Connection, key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload FROM app_settings WHERE setting_key=?", (key,)
    ).fetchone()
    if row is None:
        return None
    try:
        value = json.loads(row["payload"])
    except (ValueError, TypeError) as exc:
        raise WorkflowConflict("工作流记录损坏，请先核查备份，不自动覆盖") from exc
    if not isinstance(value, dict):
        raise WorkflowConflict("工作流记录格式不符，请先核查备份")
    return value


def _save_setting(
    connection: sqlite3.Connection, key: str, payload: dict[str, Any], now: str
) -> None:
    connection.execute(
        "INSERT INTO app_settings(setting_key,payload,updated_at) VALUES(?,?,?) "
        "ON CONFLICT(setting_key) DO UPDATE SET payload=excluded.payload,updated_at=excluded.updated_at",
        (key, json.dumps(payload, ensure_ascii=False), now),
    )


def _state(connection: sqlite3.Connection, project_id: int) -> dict[str, Any]:
    row = connection.execute(
        "SELECT * FROM research_projects WHERE id=?", (project_id,)
    ).fetchone()
    if row is None:
        raise WorkflowNotFound("研究项目不存在")
    project = dict(row)
    entries = [
        dict(item)
        for item in connection.execute(
            "SELECT * FROM research_entries WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    ]
    evidence = [
        dict(item)
        for item in connection.execute(
            "SELECT * FROM research_evidence WHERE project_id=? ORDER BY id DESC",
            (project_id,),
        ).fetchall()
    ]
    # Association identity is meaningful project state, but the related object
    # or topic text is not copied into a checkpoint (in particular no source
    # series metadata or external-data payload is added here).
    object_ids = [
        item["object_id"]
        for item in connection.execute(
            "SELECT object_id FROM research_project_objects WHERE project_id=? ORDER BY object_id",
            (project_id,),
        ).fetchall()
    ]
    topic_ids = [
        item["topic_id"]
        for item in connection.execute(
            "SELECT topic_id FROM research_topic_projects WHERE project_id=? ORDER BY topic_id",
            (project_id,),
        ).fetchall()
    ]
    hashes = {
        "project": _digest(
            {
                "fields": {
                    key: value for key, value in project.items() if key != "updated_at"
                },
                "object_ids": object_ids,
                "topic_ids": topic_ids,
            }
        ),
        "entries": {str(item["id"]): _digest(item) for item in entries},
        "evidence": {str(item["id"]): _digest(item) for item in evidence},
    }
    return {
        "project": project,
        "entries": entries,
        "evidence": evidence,
        "hashes": hashes,
        "fingerprint": _digest({"as_of": _today().isoformat(), "hashes": hashes}),
    }


def _observation_date(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        if len(value) == 10:
            return date.fromisoformat(value)
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo("Asia/Shanghai"))
        return stamp.astimezone(ZoneInfo("Asia/Shanghai")).date()
    except (ValueError, OverflowError):
        return None


def _evidence_status(row: dict[str, Any], today: date) -> dict[str, Any]:
    result = {
        "id": row["id"],
        "title": row["title"],
        "evidence_type": row["evidence_type"],
        "created_at": row["created_at"],
        "observation_date": None,
    }
    try:
        payload = json.loads(row["payload"])
        if not isinstance(payload, dict):
            payload = {}
    except (ValueError, TypeError):
        payload = {}
    if (
        _is_fred_evidence(str(row.get("source_summary", "")), payload)
        or payload.get("storage_mode") == "reference_only"
    ):
        return {
            **result,
            "status": "reference_only",
            "reason": "查询引用不是官方历史快照；重新请求可能修订，需自行重新核验",
        }
    if row["evidence_type"] == "note":
        return {
            **result,
            "status": "manual_note",
            "reason": "人工文字，不以保存日期推定数据时效或事实有效性",
        }
    observed = _observation_date(row.get("observation_end")) or _observation_date(
        row.get("observation_start")
    )
    if observed is None:
        return {
            **result,
            "status": "missing_time",
            "reason": "缺少可解析的观测日期，保存时间不能代替数据时点",
        }
    result["observation_date"] = observed.isoformat()
    age = (today - observed).days
    if age < 0:
        return {
            **result,
            "status": "needs_verification",
            "reason": "观测日期在未来，需核对时间和来源",
        }
    if age > SNAPSHOT_REVIEW_DAYS:
        return {
            **result,
            "status": "expired",
            "reason": "观测超过7天人工复核提示窗口；不是当前行情，不应推定仍然有效",
        }
    return {
        **result,
        "status": "snapshot",
        "reason": "近期本地快照仍需核验；本页没有向源请求更新或验证内容",
    }


def _delta(state: dict[str, Any], checkpoint: dict[str, Any] | None) -> dict[str, Any]:
    baseline_hashes = checkpoint.get("hashes", {}) if checkpoint is not None else {}
    if not isinstance(baseline_hashes, dict) or (
        checkpoint is not None
        and (
            not {"project", "entries", "evidence"}.issubset(baseline_hashes)
            or type(checkpoint.get("entry_id")) is not int
            or checkpoint["entry_id"] <= 0
            or not isinstance(checkpoint.get("reviewed_at"), str)
            or not isinstance(baseline_hashes.get("project"), str)
            or len(baseline_hashes["project"]) != 64
            or any(
                char not in "0123456789abcdef" for char in baseline_hashes["project"]
            )
        )
    ):
        raise WorkflowConflict("复盘基线损坏，请先核查备份")
    changes: dict[str, Any] = {
        "project_changed": bool(
            checkpoint and baseline_hashes.get("project") != state["hashes"]["project"]
        )
    }
    counts: dict[str, Any] = {"project_changed": changes["project_changed"]}
    truncated: dict[str, bool] = {}
    for kind, singular in (("entries", "entry"), ("evidence", "evidence")):
        baseline = baseline_hashes.get(kind, {})
        if not isinstance(baseline, dict) or any(
            not isinstance(key, str)
            or len(key) > 19
            or not key.isascii()
            or not key.isdigit()
            or int(key) <= 0
            or not isinstance(value, str)
            or len(value) != 64
            or any(char not in "0123456789abcdef" for char in value)
            for key, value in baseline.items()
        ):
            raise WorkflowConflict("复盘基线损坏，请先核查备份")
        rows = []
        for row in state[kind]:
            key = str(row["id"])
            change = (
                "new"
                if key not in baseline
                else "updated"
                if baseline[key] != state["hashes"][kind][key]
                else None
            )
            if change:
                fields = (
                    ("id", "title", "entry_type", "status")
                    if kind == "entries"
                    else ("id", "title", "evidence_type")
                )
                rows.append(
                    {**{field: row[field] for field in fields}, "change": change}
                )
        removed = sorted(
            int(key) for key in baseline if key not in state["hashes"][kind]
        )
        counts[f"new_{kind}"] = sum(item["change"] == "new" for item in rows)
        counts[f"updated_{kind}"] = sum(item["change"] == "updated" for item in rows)
        counts[f"removed_{kind}"] = len(removed)
        changes[kind] = rows[:MAX_ROWS]
        removed_name = f"removed_{singular}_ids"
        changes[removed_name] = removed[:MAX_ROWS]
        truncated[kind] = len(rows) > MAX_ROWS
        truncated[f"removed_{kind}"] = len(removed) > MAX_ROWS
    today = _today()
    statuses = [_evidence_status(row, today) for row in state["evidence"]]
    tasks = [
        {
            "id": row["id"],
            "title": row["title"],
            "due_date": row["due_date"],
            "overdue": bool(
                _observation_date(row["due_date"])
                and _observation_date(row["due_date"]) < today
            ),
        }
        for row in state["entries"]
        if row["entry_type"] == "task" and row["status"] == "open"
    ]
    counts["open_tasks"] = len(tasks)
    counts["needs_verification"] = sum(
        item["status"] != "manual_note" for item in statuses
    )
    truncated["evidence"] = truncated["evidence"] or len(statuses) > MAX_ROWS
    truncated["tasks"] = len(tasks) > MAX_ROWS
    return {
        "project_id": state["project"]["id"],
        "fingerprint": state["fingerprint"],
        "baseline": {
            "reviewed_at": checkpoint["reviewed_at"],
            "entry_id": checkpoint["entry_id"],
        }
        if checkpoint
        else None,
        "counts": counts,
        "changes": changes,
        "evidence_status": statuses[:MAX_ROWS],
        "open_tasks": tasks[:MAX_ROWS],
        "truncated": truncated,
        "notice": NOTICE,
    }


def review_delta(database: Database, project_id: int) -> dict[str, Any]:
    with database._connect() as connection:
        connection.execute("BEGIN")
        state = _state(connection, project_id)
        checkpoint = _load_setting(connection, f"workflow.review:{project_id}")
        return _delta(state, checkpoint)


def _insert_entry(
    connection: sqlite3.Connection,
    database: Database,
    project_id: int,
    entry: ResearchEntryCreate,
    now: str,
) -> int:
    cursor = connection.execute(
        "INSERT INTO research_entries(project_id,entry_type,title,content,status,due_date,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            project_id,
            entry.entry_type,
            entry.title,
            entry.content,
            entry.status,
            entry.due_date,
            now,
            now,
        ),
    )
    entry_id = int(cursor.lastrowid)
    database._insert_research_activity(
        connection,
        project_id,
        "entry_added",
        f"新增{database._entry_type_label(entry.entry_type)}：{entry.title}",
        {"entry_type": entry.entry_type, "status": entry.status, "entry_id": entry_id},
        now,
    )
    return entry_id


def review_checkpoint(
    database: Database, project_id: int, request: ReviewCheckpointCreate
) -> dict[str, Any]:
    request = ReviewCheckpointCreate.model_validate(request.model_dump())
    with database._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        state = _state(connection, project_id)
        key = f"workflow.review:{project_id}"
        previous = _load_setting(connection, key)
        if previous is not None:
            # Never repair a damaged historical baseline as a side effect of
            # accepting an otherwise-current preview.
            _delta(state, previous)
        note_hash = _digest(request.note.strip())
        if (
            previous
            and previous.get("accepted_fingerprint") == request.expected_fingerprint
            and previous.get("post_fingerprint") == state["fingerprint"]
            and previous.get("note_hash") == note_hash
        ):
            return _delta(state, previous)
        if state["fingerprint"] != request.expected_fingerprint:
            raise WorkflowConflict(
                "项目已发生变化，请刷新并核对新增/修改/删除内容后重新确认"
            )
        if state["project"]["status"] == "archived":
            raise WorkflowConflict("已归档项目不能新增复盘，请先明确重新打开项目")
        now = datetime.now().isoformat()
        entry = ResearchEntryCreate(
            entry_type="review",
            title="主动确认本次研究复盘",
            content=request.note.strip(),
            status="done",
        )
        entry_id = _insert_entry(connection, database, project_id, entry, now)
        connection.execute(
            "UPDATE research_projects SET updated_at=? WHERE id=?", (now, project_id)
        )
        state = _state(connection, project_id)
        checkpoint = {
            "reviewed_at": now,
            "entry_id": entry_id,
            "hashes": state["hashes"],
            "accepted_fingerprint": request.expected_fingerprint,
            "post_fingerprint": state["fingerprint"],
            "note_hash": note_hash,
        }
        _save_setting(connection, key, checkpoint, now)
        return _delta(state, checkpoint)


def _receipt(
    connection: sqlite3.Connection,
    project_id: int,
    request: WorkflowCaptureCreate,
    request_hash: str,
) -> dict[str, Any] | None:
    if (
        connection.execute(
            "SELECT 1 FROM research_projects WHERE id=?", (project_id,)
        ).fetchone()
        is None
    ):
        raise WorkflowNotFound("研究项目不存在")
    saved = _load_setting(connection, f"workflow.capture:{request.request_id}")
    if saved is None:
        return None
    if (
        saved.get("request_hash") != request_hash
        or saved.get("project_id") != project_id
    ):
        raise WorkflowConflict("该请求标识已用于其他内容；请核对上次结果，不重复提交")
    if (
        type(saved.get("entry_id")) is not int
        or saved["entry_id"] <= 0
        or "evidence_id" not in saved
        or (
            request.kind == "market_signal"
            and (type(saved.get("evidence_id")) is not int or saved["evidence_id"] <= 0)
        )
        or (request.kind == "brief_note" and saved.get("evidence_id") is not None)
    ):
        raise WorkflowConflict("工作流回执损坏，请核对备份，不自动重建记录")
    if (
        connection.execute(
            "SELECT 1 FROM research_entries WHERE id=? AND project_id=?",
            (saved["entry_id"], project_id),
        ).fetchone()
        is None
    ):
        raise WorkflowConflict("该请求已保存过，但记录现已删除；不会自动重建")
    if (
        saved.get("evidence_id") is not None
        and connection.execute(
            "SELECT 1 FROM research_evidence WHERE id=? AND project_id=?",
            (saved["evidence_id"], project_id),
        ).fetchone()
        is None
    ):
        raise WorkflowConflict("该请求证据已被删除；不会自动重建")
    return {
        "project_id": project_id,
        "entry_id": saved["entry_id"],
        "evidence_id": saved.get("evidence_id"),
        "deduplicated": True,
    }


def _market_capture(
    signal: dict[str, Any], expected: str, note: str
) -> tuple[ResearchEntryCreate, ResearchEvidenceCreate]:
    if signal.get("fetched_at") != expected:
        raise WorkflowConflict("行情已更新或预览时点不匹配，请重新查看后确认")
    observed = _observation_date(signal.get("observation_time"))
    if (
        not signal.get("actionable")
        or signal.get("demo") is not False
        or signal.get("trust_level") != "trusted"
        or signal.get("data_state") not in {"live", "latest", "cached"}
        or observed is None
        or observed > _today()
        or observed < _today() - timedelta(days=SNAPSHOT_REVIEW_DAYS)
        or signal.get("category") not in {"funding", "curve", "future", "bond"}
    ):
        raise WorkflowConflict(
            "该信号未通过可信、时点或非演示门禁，请回原始模块核验；可单独保存自己的笔记"
        )
    value = signal.get("value")
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise WorkflowConflict("信号缺少有效数值，不保存为市场证据")
    if _is_fred_evidence(str(signal.get("source", "")), signal):
        raise WorkflowConflict("FRED来源内容不通过市场变化通道保存")
    selected = {
        key: signal.get(key)
        for key in (
            "id",
            "category",
            "title",
            "summary",
            "value",
            "unit",
            "object_type",
            "object_id",
            "object_name",
            "adapter",
            "source",
            "observation_time",
            "fetched_at",
            "trust_level",
            "quality_score",
            "data_state",
            "demo",
            "actionable",
        )
    }
    selected["source_url"] = _source_url(signal.get("source_url"))
    title = f"市场变化 · {signal.get('title', signal['id'])}"[:160]
    entry = ResearchEntryCreate(entry_type="note", title=title, content=note)
    evidence = ResearchEvidenceCreate(
        evidence_type="snapshot",
        title=title,
        source_summary=str(signal.get("source", "来源待核验"))[:500],
        observation_start=str(signal["observation_time"]),
        observation_end=str(signal["observation_time"]),
        payload={
            "schema_version": 1,
            "snapshot_type": "market_brief",
            "storage_mode": "local_snapshot",
            "signals": [selected],
            "generated_at": signal["fetched_at"],
            "notice": "只保存已选定的一条市场变化及其出处；这是本地快照，不自动更新，不证明数据授权或投资结论。",
        },
    )
    return entry, evidence


def workflow_capture(
    database: Database,
    service: DataService,
    project_id: int,
    request: WorkflowCaptureCreate,
    settings: ResearchSignalSettings | None = None,
) -> dict[str, Any]:
    request = WorkflowCaptureCreate.model_validate(request.model_dump())
    request_hash = _digest(
        {"project_id": project_id, "request": request.model_dump(mode="json")}
    )
    # Check receipt BEFORE consulting market state: a successful save whose
    # response was lost must remain retryable after the market changes.
    with database._connect() as connection:
        existing = _receipt(connection, project_id, request, request_hash)
        if existing:
            return existing
    evidence = None
    if request.kind == "market_signal":
        brief = build_market_brief(service, settings)
        signal = next(
            (item for item in brief["signals"] if item["id"] == request.signal_id), None
        )
        if signal is None:
            raise WorkflowConflict("选定市场变化已不存在，请刷新并核验")
        try:
            entry, evidence = _market_capture(
                signal, request.expected_fetched_at or "", request.note
            )
        except ValidationError as exc:
            raise WorkflowConflict(
                "来源字段不满足研究证据格式，请回原模块核验"
            ) from exc
        cached = service._cached_dataset(
            str(signal.get("adapter", "")), allow_stale=False
        )
        if cached is None:
            raise WorkflowConflict("该来源缓存已过期，请先刷新并核验后再保存为证据")
        if cached.meta.fetched_at.isoformat() != request.expected_fetched_at:
            raise WorkflowConflict("来源在确认过程中已更新，请重新查看后再保存证据")
    else:
        entry = ResearchEntryCreate(
            entry_type="note",
            title=f"简报备注 · {request.report_date.isoformat()}",
            content=request.note,
        )
    with database._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        existing = _receipt(connection, project_id, request, request_hash)
        if existing:
            return existing
        if (
            connection.execute(
                "SELECT status FROM research_projects WHERE id=?", (project_id,)
            ).fetchone()["status"]
            == "archived"
        ):
            raise WorkflowConflict("已归档项目不能新增记录，请先明确重新打开项目")
        now = datetime.now().isoformat()
        entry_id = _insert_entry(connection, database, project_id, entry, now)
        evidence_id = None
        if evidence:
            cursor = connection.execute(
                "INSERT INTO research_evidence(project_id,evidence_type,title,payload,source_summary,observation_start,observation_end,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (
                    project_id,
                    evidence.evidence_type,
                    evidence.title,
                    json.dumps(evidence.payload, ensure_ascii=False),
                    evidence.source_summary,
                    evidence.observation_start,
                    evidence.observation_end,
                    now,
                ),
            )
            evidence_id = int(cursor.lastrowid)
            connection.execute(
                "INSERT OR IGNORE INTO research_evidence_objects(evidence_id,object_id,created_at) SELECT ?,object_id,? FROM research_project_objects WHERE project_id=?",
                (evidence_id, now, project_id),
            )
            database._insert_research_activity(
                connection,
                project_id,
                "evidence_added",
                f"新增证据：{evidence.title}",
                {
                    "evidence_type": evidence.evidence_type,
                    "source_summary": evidence.source_summary,
                },
                now,
            )
        connection.execute(
            "UPDATE research_projects SET updated_at=? WHERE id=?", (now, project_id)
        )
        saved = {
            "project_id": project_id,
            "entry_id": entry_id,
            "evidence_id": evidence_id,
            "request_hash": request_hash,
        }
        _save_setting(connection, f"workflow.capture:{request.request_id}", saved, now)
        return {
            **{key: saved[key] for key in ("project_id", "entry_id", "evidence_id")},
            "deduplicated": False,
        }
