from __future__ import annotations

import gc

import pytest

from app.cache import PersistentCache
from app.database import Database
from app.runtime import runtime_diagnostics


def test_repeated_sqlite_reads_release_file_descriptors(tmp_path) -> None:
    database = Database(tmp_path / "research.db")
    cache = PersistentCache(tmp_path / "market-cache.db")
    before = runtime_diagnostics()["file_descriptors"]["open"]
    if before is None:
        pytest.skip("当前平台不提供进程文件描述符计数")

    gc_was_enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(120):
            database.list_watchlist()
            cache.stats()
        after = runtime_diagnostics()["file_descriptors"]["open"]
    finally:
        if gc_was_enabled:
            gc.enable()
        gc.collect()

    assert after is not None
    assert after - before <= 4


def test_runtime_diagnostics_report_fd_limits() -> None:
    runtime = runtime_diagnostics()
    descriptors = runtime["file_descriptors"]

    assert runtime["process_id"] > 0
    assert runtime["uptime_seconds"] >= 0
    assert runtime["threads"] >= 1
    assert descriptors["open"] is None or descriptors["open"] >= 0
    assert descriptors["soft_limit"] is None or descriptors["soft_limit"] > 0
