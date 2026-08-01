from __future__ import annotations

import os
import time

from app.backup import ResearchBackupScheduler
from app.database import Database
from app.models import ResearchProjectCreate


def test_auto_backup_is_valid_bounded_and_skips_recent_snapshot(tmp_path) -> None:
    database = Database(tmp_path / "research.db")
    database.add_research_project(
        ResearchProjectCreate(title="利率方向", question="长端如何变化？")
    )
    scheduler = ResearchBackupScheduler(
        database,
        tmp_path / "backups",
        interval_seconds=3600,
        retention=2,
    )

    first = scheduler.run_once()
    assert first["created"] is True
    backup_path = tmp_path / "backups" / first["backup"]
    Database.validate_backup(backup_path)

    skipped = scheduler.run_once()
    assert skipped == {"created": False, "backup": first["backup"]}

    second = scheduler.run_once(force=True)
    third = scheduler.run_once(force=True)
    assert second["created"] is True and third["created"] is True
    assert len(scheduler.list_backups()) == 2
    assert scheduler.status()["latest"]["name"] == third["backup"]


def test_auto_backup_replaces_invalid_temporary_file_atomically(tmp_path) -> None:
    database = Database(tmp_path / "research.db")
    scheduler = ResearchBackupScheduler(database, tmp_path / "backups")
    result = scheduler.run_once(force=True)
    assert result["created"] is True
    assert not list((tmp_path / "backups").glob("*.tmp"))
    assert os.path.getsize(tmp_path / "backups" / result["backup"]) > 0

    latest = tmp_path / "backups" / result["backup"]
    old = time.time() - scheduler.interval_seconds - 5
    os.utime(latest, (old, old))
    assert scheduler.run_once()["created"] is True
