from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from .database import Database


class ResearchBackupScheduler:
    """Create bounded, validated research database snapshots in the background."""

    def __init__(
        self,
        database: Database,
        backup_dir: Path,
        *,
        interval_seconds: int = 24 * 60 * 60,
        retention: int = 14,
    ) -> None:
        self.database = database
        self.backup_dir = backup_dir
        self.interval_seconds = max(60, interval_seconds)
        self.retention = max(2, retention)
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()
        self._last_error: str | None = None

    @classmethod
    def from_environment(
        cls, database: Database, backup_dir: Path
    ) -> ResearchBackupScheduler:
        return cls(
            database,
            backup_dir,
            interval_seconds=int(
                os.getenv("AKDESK_AUTO_BACKUP_INTERVAL_SECONDS", str(24 * 60 * 60))
            ),
            retention=int(os.getenv("AKDESK_AUTO_BACKUP_RETENTION", "14")),
        )

    def _files(self) -> list[Path]:
        if not self.backup_dir.exists():
            return []
        return sorted(
            self.backup_dir.glob("auto-research-*.db"),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )

    def list_backups(self) -> list[dict[str, Any]]:
        return [
            {
                "name": item.name,
                "size_bytes": item.stat().st_size,
                "created_at": datetime.fromtimestamp(
                    item.stat().st_mtime
                ).isoformat(),
            }
            for item in self._files()
        ]

    def cleanup(self) -> int:
        removed = 0
        for item in self._files()[self.retention :]:
            item.unlink(missing_ok=True)
            removed += 1
        return removed

    def run_once(self, *, force: bool = False) -> dict[str, Any]:
        with self._lock:
            self.backup_dir.mkdir(parents=True, exist_ok=True)
            existing = self._files()
            now = time.time()
            if (
                not force
                and existing
                and now - existing[0].stat().st_mtime < self.interval_seconds
            ):
                self.cleanup()
                self._last_error = None
                return {"created": False, "backup": existing[0].name}

            stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
            target = self.backup_dir / f"auto-research-{stamp}.db"
            temporary = target.with_suffix(".tmp")
            try:
                self.database.backup_to(temporary)
                self.database.validate_backup(temporary)
                temporary.replace(target)
                self.cleanup()
                self._last_error = None
                return {"created": True, "backup": target.name}
            except Exception as exc:
                temporary.unlink(missing_ok=True)
                self._last_error = f"{type(exc).__name__}: {exc}"[:300]
                raise

    def status(self) -> dict[str, Any]:
        backups = self.list_backups()
        latest = backups[0] if backups else None
        next_due_at = None
        if latest is not None:
            next_due_at = datetime.fromtimestamp(
                datetime.fromisoformat(latest["created_at"]).timestamp()
                + self.interval_seconds
            ).isoformat()
        return {
            "enabled": True,
            "running": bool(self._thread and self._thread.is_alive()),
            "retention": self.retention,
            "interval_seconds": self.interval_seconds,
            "latest": latest,
            "next_due_at": next_due_at,
            "last_error": self._last_error,
            "backups": backups,
        }

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        try:
            self.run_once()
        except Exception:
            # A backup failure is reported by status, but must not block startup.
            pass

        def loop() -> None:
            check_seconds = min(60 * 60, max(60, self.interval_seconds // 4))
            while not self._stop.wait(check_seconds):
                try:
                    self.run_once()
                except Exception:
                    continue

        self._thread = threading.Thread(
            target=loop,
            daemon=True,
            name="akdesk-research-backup",
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1)

