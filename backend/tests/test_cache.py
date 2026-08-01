from datetime import datetime
import sqlite3

from app.cache import PersistentCache
from app.models import Dataset, SourceMeta


def _dataset() -> Dataset:
    return Dataset(
        data=[{"code": "240011", "price": 101.25}],
        meta=SourceMeta(
            source="test",
            observation_time="2026-07-13T15:00:00",
            fetched_at=datetime.now(),
        ),
    )


def test_persistent_cache_survives_process_restart(tmp_path) -> None:
    path = tmp_path / "market-cache.db"
    first = PersistentCache(path)
    first.set("spot_bonds", _dataset(), ttl_seconds=60)

    restarted = PersistentCache(path)
    restored = restarted.get("spot_bonds")

    assert restored is not None
    assert restored.data[0]["code"] == "240011"
    assert restarted.is_persisted("spot_bonds") is True
    assert restarted.stats()["entries"] == 1


def test_expired_cache_is_only_returned_when_stale_is_allowed(tmp_path) -> None:
    cache = PersistentCache(tmp_path / "market-cache.db")
    cache.set("spot_bonds", _dataset(), ttl_seconds=0)

    assert cache.get("spot_bonds") is None
    assert cache.get("spot_bonds", allow_stale=True) is not None


def test_non_persistent_dataset_stays_in_memory(tmp_path) -> None:
    path = tmp_path / "market-cache.db"
    cache = PersistentCache(path)
    cache.set("spot_bonds", _dataset(), ttl_seconds=60, persist=False)

    assert cache.get("spot_bonds") is not None
    assert PersistentCache(path).get("spot_bonds") is None


def test_compatible_old_cache_schema_is_migrated_in_place(tmp_path) -> None:
    path = tmp_path / "market-cache.db"
    old = PersistentCache(path, schema_version="1")
    old.set("spot_bonds", _dataset(), ttl_seconds=60)

    migrated = PersistentCache(path)
    restored = migrated.get("spot_bonds")
    with sqlite3.connect(path) as connection:
        version = connection.execute(
            "SELECT schema_version FROM market_cache WHERE cache_key = ?",
            ("spot_bonds",),
        ).fetchone()[0]

    assert restored is not None
    assert restored.data[0]["code"] == "240011"
    assert version == migrated.schema_version
