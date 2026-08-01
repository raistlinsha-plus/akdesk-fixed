from __future__ import annotations

import sqlite3
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .models import Dataset


CACHE_SCHEMA_VERSION = "2"


@dataclass
class CacheEntry:
    value: Any
    created_at: float
    ttl_seconds: int

    @property
    def fresh(self) -> bool:
        return self.age_seconds < self.ttl_seconds

    @property
    def age_seconds(self) -> int:
        return max(0, round(time.time() - self.created_at))


class MemoryCache:
    def __init__(self) -> None:
        self._items: dict[str, CacheEntry] = {}
        self._lock = threading.RLock()

    def _set_entry(self, key: str, entry: CacheEntry) -> None:
        with self._lock:
            self._items[key] = entry

    def entry(self, key: str) -> CacheEntry | None:
        with self._lock:
            return self._items.get(key)

    def get(self, key: str, allow_stale: bool = False) -> Any | None:
        entry = self.entry(key)
        if entry is None:
            return None
        if entry.fresh or allow_stale:
            return entry.value
        return None

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int,
        *,
        persist: bool = True,
    ) -> None:
        del persist
        self._set_entry(
            key,
            CacheEntry(
                value=value,
                created_at=time.time(),
                ttl_seconds=ttl_seconds,
            ),
        )

    def age_seconds(self, key: str) -> int | None:
        entry = self.entry(key)
        return entry.age_seconds if entry else None

    def is_persisted(self, key: str) -> bool:
        del key
        return False

    def clear(self) -> None:
        with self._lock:
            self._items.clear()

    def delete(self, key: str) -> None:
        with self._lock:
            self._items.pop(key, None)

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._items), "bytes": 0}


class PersistentCache(MemoryCache):
    """SQLite-backed last-known-good cache with an in-memory hot layer."""

    def __init__(self, path: Path, schema_version: str = CACHE_SCHEMA_VERSION) -> None:
        super().__init__()
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.schema_version = schema_version
        self._db_lock = threading.RLock()
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._db_lock, self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS market_cache (
                    cache_key TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    ttl_seconds INTEGER NOT NULL,
                    schema_version TEXT NOT NULL
                );
                """
            )

    def _disk_entry(self, key: str) -> CacheEntry | None:
        with self._db_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM market_cache WHERE cache_key = ?",
                (key,),
            ).fetchone()
            if row is None:
                return None
        try:
            dataset = Dataset.model_validate_json(row["payload"])
        except Exception:
            with self._db_lock, self._connect() as connection:
                connection.execute(
                    "DELETE FROM market_cache WHERE cache_key = ?", (key,)
                )
            return None
        if row["schema_version"] != self.schema_version:
            # SourceMeta additions are deliberately backward compatible. Keep a
            # valid last-known-good payload and migrate it in place instead of
            # discarding a user's cache during an application upgrade.
            with self._db_lock, self._connect() as connection:
                connection.execute(
                    """
                    UPDATE market_cache
                    SET payload = ?, schema_version = ?
                    WHERE cache_key = ?
                    """,
                    (dataset.model_dump_json(), self.schema_version, key),
                )
        entry = CacheEntry(
            value=dataset,
            created_at=float(row["created_at"]),
            ttl_seconds=int(row["ttl_seconds"]),
        )
        self._set_entry(key, entry)
        return entry

    def entry(self, key: str) -> CacheEntry | None:
        entry = super().entry(key)
        return entry if entry is not None else self._disk_entry(key)

    def set(
        self,
        key: str,
        value: Any,
        ttl_seconds: int,
        *,
        persist: bool = True,
    ) -> None:
        created_at = time.time()
        self._set_entry(
            key,
            CacheEntry(
                value=value,
                created_at=created_at,
                ttl_seconds=ttl_seconds,
            ),
        )
        if not persist:
            return
        if not isinstance(value, Dataset):
            raise TypeError("持久行情缓存只接受 Dataset")
        with self._db_lock, self._connect() as connection:
            connection.execute(
                """
                INSERT INTO market_cache
                    (cache_key, payload, created_at, ttl_seconds, schema_version)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at,
                    ttl_seconds = excluded.ttl_seconds,
                    schema_version = excluded.schema_version
                """,
                (
                    key,
                    value.model_dump_json(),
                    created_at,
                    ttl_seconds,
                    self.schema_version,
                ),
            )

    def is_persisted(self, key: str) -> bool:
        with self._db_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT 1 FROM market_cache WHERE cache_key = ?", (key,)
            ).fetchone()
        return row is not None

    def clear(self) -> None:
        super().clear()
        with self._db_lock, self._connect() as connection:
            connection.execute("DELETE FROM market_cache")

    def delete(self, key: str) -> None:
        super().delete(key)
        with self._db_lock, self._connect() as connection:
            connection.execute("DELETE FROM market_cache WHERE cache_key = ?", (key,))

    def stats(self) -> dict[str, int]:
        with self._db_lock, self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS entries, COALESCE(SUM(LENGTH(payload)), 0) AS bytes FROM market_cache"
            ).fetchone()
        return {
            "entries": int(row["entries"]) if row else 0,
            "bytes": int(row["bytes"]) if row else 0,
        }
