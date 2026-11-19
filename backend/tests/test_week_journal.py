from concurrent.futures import ThreadPoolExecutor
from datetime import date
import hashlib
import sqlite3

import pytest
from pydantic import ValidationError

from app.database import Database
from app.week_journal import JournalConflict, WeekDelete, WeekSave, delete_week, history, revisions, save_week, view_week

FIRST = date(2026, 7, 24)
SECOND = date(2026, 7, 31)


def test_journal_keeps_prior_revision_and_plain_text_in_backup(tmp_path):
    db = Database(tmp_path / "original.db")
    first = save_week(db, FIRST, WeekSave(expected_revision=None, judgment="初始判断", next_question="下一周验证"))
    second = save_week(db, SECOND, WeekSave(
        expected_revision=None, judgment="第二周", assessment="partial",
        assessment_note="只支持一个方向", previous_revision=first["revision"],
    ))
    latest = save_week(db, FIRST, WeekSave(expected_revision=first["revision"], judgment="修订后的判断"))
    assert view_week(db, SECOND)["previous"] == latest
    assert view_week(db, SECOND)["assessed"] == first
    assert revisions(db, FIRST, 0)["items"] == [latest, first]
    assert history(db, "修订后", 0)["items"] == [latest]
    assert history(db, "初始", 0)["items"] == []
    backup = tmp_path / "backup.db"
    db.backup_to(backup)
    digest = hashlib.sha256(backup.read_bytes()).digest()
    restored = Database(tmp_path / "restored.db")
    restored.restore_from(backup)
    assert hashlib.sha256(backup.read_bytes()).digest() == digest
    assert view_week(restored, SECOND)["current"] == second
    assert view_week(restored, SECOND)["assessed"] == first


def test_concurrent_stale_edit_and_repeat_does_not_overwrite(tmp_path):
    db = Database(tmp_path / "test.db")
    first = save_week(db, FIRST, WeekSave(expected_revision=None, judgment="初版"))

    def edit(i):
        item = WeekSave(expected_revision=first["revision"], judgment="并发 " + str(i))
        try:
            saved = save_week(db, FIRST, item)
            assert save_week(db, FIRST, item) == saved
            return saved
        except JournalConflict:
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(edit, range(4)))
    winners = [result for result in results if result]
    assert len(winners) == 1
    assert revisions(db, FIRST, 0)["items"] == [winners[0], first]


def test_validation_rejects_market_payload_wrong_period_and_unexplained_assessments(tmp_path):
    db = Database(tmp_path / "test.db")
    first = save_week(db, FIRST, WeekSave(expected_revision=None, next_question="待验证"))
    with pytest.raises(ValidationError):
        WeekSave.model_validate({"expected_revision": None, "judgment": "用户文字", "quotes": [1.5]})
    with pytest.raises(ValidationError):
        WeekSave(expected_revision=None, judgment="过长" * 1001)
    with pytest.raises(ValueError, match="简要说明"):
        save_week(db, SECOND, WeekSave(expected_revision=None, assessment="supported", previous_revision=first["revision"]))
    with pytest.raises(JournalConflict):
        save_week(db, date(2026, 8, 1), WeekSave(expected_revision=None, assessment="pending", previous_revision=first["revision"]))
    assert view_week(db, date(2026, 8, 1))["previous"] is None
    assert set(first) == {
        "revision", "week_end", "judgment", "next_question", "assessment", "assessment_note",
        "previous_revision", "created_at",
    }


def test_delete_all_revisions_requires_current_token_and_does_not_repoint(tmp_path):
    db = Database(tmp_path / "test.db")
    first = save_week(db, FIRST, WeekSave(expected_revision=None, next_question="待验证"))
    second = save_week(db, SECOND, WeekSave(expected_revision=None, assessment="pending", previous_revision=first["revision"]))
    new = save_week(db, FIRST, WeekSave(expected_revision=first["revision"], next_question="更新问题"))
    with pytest.raises(JournalConflict):
        delete_week(db, FIRST, WeekDelete(expected_revision=first["revision"], confirmed=True))
    delete_week(db, FIRST, WeekDelete(expected_revision=new["revision"], confirmed=True))
    assert revisions(db, FIRST, 0)["items"] == []
    replaced = save_week(db, FIRST, WeekSave(expected_revision=None, next_question="新问题"))
    assert replaced["revision"] not in (first["revision"], new["revision"])
    context = view_week(db, SECOND)
    assert context["current"] == second
    assert context["assessed"] is None
    assert context["previous"] == replaced


def test_migrates_schema_1600_and_preserves_existing_records(tmp_path):
    path = tmp_path / "old.db"
    Database(path)
    with sqlite3.connect(path) as connection:
        connection.execute("DROP TABLE market_week_revisions")
        connection.execute("DELETE FROM schema_migrations WHERE version=1700")
        connection.execute("PRAGMA user_version=1600")
        connection.execute("INSERT INTO research_projects(title, created_at, updated_at) VALUES ('原有项目', '2026-07-01', '2026-07-01')")
    db = Database(path)
    assert history(db, "", 0)["items"] == []
    with db._connect() as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 1700
        assert connection.execute("SELECT title FROM research_projects").fetchone()[0] == "原有项目"
