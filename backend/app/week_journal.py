"""Local market-week judgments only; this module has no market or AI client."""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Annotated, Literal
from uuid import uuid4
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, StringConstraints

if TYPE_CHECKING:
    from .database import Database

ShortText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, max_length=2000)]
Revision = Annotated[str, StringConstraints(strict=True, pattern=r"^[0-9a-f]{32}$")]
Assessment = Literal["", "supported", "partial", "unsupported", "pending"]
FIELDS = "revision, week_end, judgment, next_question, assessment, assessment_note, previous_revision, created_at"
CONTENT = ("judgment", "next_question", "assessment", "assessment_note", "previous_revision")
PAGE_SIZE = 30


class JournalConflict(ValueError):
    pass


class WeekSave(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision | None
    judgment: ShortText = ""
    next_question: ShortText = ""
    assessment: Assessment = ""
    assessment_note: ShortText = ""
    previous_revision: Revision | None = None


class WeekDelete(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: Revision
    confirmed: Literal[True]


def valid_week(week: date) -> None:
    if week < date(1900, 1, 8) or week >= datetime.now(ZoneInfo("Asia/Shanghai")).date():
        raise ValueError("周结束日须早于今天，且不早于 1900-01-08。")


def _entry(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def _latest(connection: sqlite3.Connection, week: str) -> dict | None:
    row = connection.execute(
        f"SELECT {FIELDS} FROM market_week_revisions WHERE week_end=? ORDER BY id DESC LIMIT 1",
        (week,),
    ).fetchone()
    return _entry(row)


def _previous(connection: sqlite3.Connection, week: date, revision: str) -> dict | None:
    return _entry(connection.execute(
        f"SELECT {FIELDS} FROM market_week_revisions WHERE week_end=? AND revision=?",
        ((week - timedelta(days=7)).isoformat(), revision),
    ).fetchone())


def view_week(database: Database, week: date) -> dict:
    valid_week(week)
    with database._connect() as connection:
        connection.execute("BEGIN")
        latest = _latest(connection, week.isoformat())
        pinned = latest["previous_revision"] if latest else None
        return {
            "week_end": week.isoformat(),
            "current": latest,
            "previous": _latest(connection, (week - timedelta(days=7)).isoformat()),
            "assessed": _previous(connection, week, pinned) if pinned else None,
        }


def save_week(database: Database, week: date, item: WeekSave) -> dict:
    valid_week(week)
    values = item.model_dump(include=set(CONTENT))
    if not any((item.judgment, item.next_question, item.assessment)):
        raise ValueError("请留下判断、待核验事项或一次人工核验。")
    if (item.assessment and not item.previous_revision) or (item.assessment_note and not item.assessment):
        raise ValueError("请为核验选择上一周的记录和状态。")
    if item.assessment and item.assessment != "pending" and not item.assessment_note:
        raise ValueError("请简要说明人工核验依据。")
    with database._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        current = _latest(connection, week.isoformat())
        # A timed-out response can be retried without creating a second identical revision.
        if current and all(current[key] == values[key] for key in CONTENT):
            return current
        if (current["revision"] if current else None) != item.expected_revision:
            raise JournalConflict("该周记录已变化，请重新读取再确认，本次没有覆盖。")
        if item.previous_revision:
            previous = _previous(connection, week, item.previous_revision)
            if not previous or (item.assessment and not previous["next_question"]):
                raise JournalConflict("上一周的待核验记录已不可用，请重新读取。")
        revision = uuid4().hex
        connection.execute(
            f"INSERT INTO market_week_revisions ({FIELDS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (revision, week.isoformat(), *(values[key] for key in CONTENT),
             datetime.now(timezone.utc).isoformat()),
        )
        saved = _latest(connection, week.isoformat())
        assert saved is not None
        return saved


def delete_week(database: Database, week: date, item: WeekDelete) -> None:
    valid_week(week)
    with database._connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        latest = _latest(connection, week.isoformat())
        if not latest or latest["revision"] != item.expected_revision:
            raise JournalConflict("记录已变更或已删除，请重新读取。")
        connection.execute("DELETE FROM market_week_revisions WHERE week_end=?", (week.isoformat(),))


def history(database: Database, query: str, offset: int) -> dict:
    # Match literal text in the latest saved revision, not hidden prior revisions.
    with database._connect() as connection:
        rows = connection.execute(
            f"SELECT {FIELDS} FROM market_week_revisions WHERE id IN "
            "(SELECT MAX(id) FROM market_week_revisions GROUP BY week_end) "
            "AND (? = '' OR instr(lower(week_end || ' ' || judgment || ' ' || next_question || "
            "' ' || assessment_note), lower(?)) > 0) ORDER BY week_end DESC LIMIT ? OFFSET ?",
            (query, query, PAGE_SIZE + 1, offset),
        ).fetchall()
    return {"items": [dict(row) for row in rows[:PAGE_SIZE]], "more": len(rows) > PAGE_SIZE}


def revisions(database: Database, week: date, offset: int) -> dict:
    valid_week(week)
    with database._connect() as connection:
        rows = connection.execute(
            f"SELECT {FIELDS} FROM market_week_revisions WHERE week_end=? ORDER BY id DESC LIMIT ? OFFSET ?",
            (week.isoformat(), PAGE_SIZE + 1, offset),
        ).fetchall()
    return {"items": [dict(row) for row in rows[:PAGE_SIZE]], "more": len(rows) > PAGE_SIZE}
