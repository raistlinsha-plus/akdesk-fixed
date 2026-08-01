#!/usr/bin/env python3
"""Validate real historical database migrations and backup recovery on copies."""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import Database  # noqa: E402

TARGET_SCHEMA = 1600
REQUIRED_SOURCE_SCHEMAS = (701, 800, 900, 1100, 1201, 1301)
REQUIRED_MIGRATIONS = (700, 701, 800, 900, 1100, 1201, 1301, 1410, 1600)
PRESERVED_TABLES = (
    "watchlist_items",
    "alert_rules",
    "research_projects",
    "research_evidence",
    "credit_observations",
)


def sqlite_summary(path: Path) -> dict[str, Any]:
    connection = sqlite3.connect(path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        counts = {
            table: int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            for table in PRESERVED_TABLES
            if table in tables
        }
        return {
            "schema": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
            "foreign_key_errors": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "counts": counts,
            "migrations": (
                [
                    int(row[0])
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                ]
                if "schema_migrations" in tables
                else []
            ),
        }
    finally:
        connection.close()


def find_sources(backups_dir: Path) -> dict[int, Path]:
    found: dict[int, Path] = {}
    for path in sorted(backups_dir.glob("*.db")):
        try:
            schema = sqlite_summary(path)["schema"]
        except sqlite3.DatabaseError:
            continue
        if schema in REQUIRED_SOURCE_SCHEMAS and schema not in found:
            found[schema] = path
    missing = set(REQUIRED_SOURCE_SCHEMAS) - set(found)
    if missing:
        raise RuntimeError(
            "缺少历史迁移样本：" + ", ".join(str(item) for item in sorted(missing))
        )
    return found


def validate_one(source: Path, workspace: Path) -> dict[str, Any]:
    before = sqlite_summary(source)
    copied = workspace / f"schema-{before['schema']}.db"
    shutil.copy2(source, copied)
    database = Database(copied)
    after = sqlite_summary(copied)
    if after["schema"] != TARGET_SCHEMA:
        raise RuntimeError(f"{source.name} 未迁移到 schema {TARGET_SCHEMA}")
    if after["quick_check"] != "ok" or after["foreign_key_errors"]:
        raise RuntimeError(f"{source.name} 迁移后完整性或外键检查失败")
    if not set(REQUIRED_MIGRATIONS).issubset(after["migrations"]):
        raise RuntimeError(f"{source.name} 缺少预期 schema_migrations 记录")
    for table, count in before["counts"].items():
        if after["counts"].get(table, -1) < count:
            raise RuntimeError(f"{source.name} 迁移后 {table} 记录数量减少")

    snapshot = workspace / f"schema-{before['schema']}-backup.db"
    database.backup_to(snapshot)
    Database.validate_backup(snapshot)
    restored_path = workspace / f"schema-{before['schema']}-restored.db"
    restored = Database(restored_path)
    restored.restore_from(snapshot)
    restored_summary = sqlite_summary(restored_path)
    if restored_summary["counts"] != after["counts"]:
        raise RuntimeError(f"{source.name} 备份恢复后核心表计数不一致")

    return {
        "source": source.name,
        "source_schema": before["schema"],
        "target_schema": after["schema"],
        "quick_check": after["quick_check"],
        "foreign_key_errors": after["foreign_key_errors"],
        "preserved_counts": after["counts"],
        "backup_restore": "ok",
    }


def corruption_rejection_gate(workspace: Path) -> None:
    corrupt = workspace / "corrupt.db"
    corrupt.write_bytes(b"not a sqlite database")
    try:
        Database.validate_backup(corrupt)
    except (ValueError, sqlite3.DatabaseError):
        return
    raise RuntimeError("损坏备份没有被拒绝")


def run(backups_dir: Path) -> dict[str, Any]:
    sources = find_sources(backups_dir)
    with tempfile.TemporaryDirectory(prefix="akdesk-migration-gate-") as directory:
        workspace = Path(directory)
        results = [
            validate_one(sources[schema], workspace)
            for schema in REQUIRED_SOURCE_SCHEMAS
        ]
        corruption_rejection_gate(workspace)
    return {
        "status": "ok",
        "target_schema": TARGET_SCHEMA,
        "source_schemas": list(REQUIRED_SOURCE_SCHEMAS),
        "results": results,
        "corrupt_backup_rejected": True,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--backups-dir", type=Path, default=ROOT / "data" / "backups"
    )
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run(args.backups_dir.resolve())
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
