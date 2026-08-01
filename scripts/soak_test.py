#!/usr/bin/env python3
"""Run a bounded demo-mode service soak and record resource behavior."""

from __future__ import annotations

import argparse
import json
import os
import signal
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENDPOINTS = (
    "/api/v1/health",
    "/api/v1/info",
    "/api/v1/rates",
    "/api/v1/curves",
    "/api/v1/bonds/spot",
    "/api/v1/futures",
    "/api/v1/fx/pairs",
    "/api/v1/fx/rmb-reference",
    "/api/v1/research/overview",
    "/api/v1/sources/health",
    "/api/v1/connectors",
)


def get_json(
    base_url: str, path: str, timeout: float = 10.0, method: str = "GET"
) -> Any:
    request = urllib.request.Request(
        base_url + path,
        headers={"User-Agent": "AKDesk-Soak-Gate/1.0"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"{path} returned HTTP {response.status}")
        return json.loads(response.read().decode("utf-8"))


def rss_kib(pid: int) -> int | None:
    result = subprocess.run(
        ["ps", "-o", "rss=", "-p", str(pid)],
        check=False,
        capture_output=True,
        text=True,
    )
    try:
        return int(result.stdout.strip())
    except ValueError:
        return None


def wait_ready(process: subprocess.Popen[str], base_url: str) -> None:
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("服务在就绪前退出")
        try:
            get_json(base_url, "/api/v1/health", timeout=1)
            return
        except (OSError, RuntimeError, json.JSONDecodeError):
            time.sleep(0.2)
    raise RuntimeError("服务未在 30 秒内就绪")


def verify_database(data_dir: Path) -> dict[str, Any]:
    path = data_dir / "akdesk-fixed.db"
    connection = sqlite3.connect(path)
    try:
        return {
            "path": path.name,
            "schema": int(connection.execute("PRAGMA user_version").fetchone()[0]),
            "quick_check": str(connection.execute("PRAGMA quick_check").fetchone()[0]),
            "foreign_key_errors": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
        }
    finally:
        connection.close()


def run_soak(
    *,
    duration_seconds: int,
    interval_seconds: float,
    port: int,
) -> dict[str, Any]:
    started_wall = datetime.now(timezone.utc)
    started = time.monotonic()
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    with tempfile.TemporaryDirectory(prefix="akdesk-soak-") as directory:
        data_dir = Path(directory) / "data"
        data_dir.mkdir()
        log_path = Path(directory) / "service.log"
        environment = os.environ.copy()
        environment.update(
            {
                "PYTHONPATH": str(ROOT / "backend"),
                "PYTHONUTF8": "1",
                "AKDESK_DEMO": "1",
                "AKDESK_NO_BROWSER": "1",
                "AKDESK_PORT": str(port),
                "AKDESK_DATA_DIR": str(data_dir),
                "AKDESK_AUTO_BACKUP_INTERVAL_SECONDS": "60",
            }
        )
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(
                [sys.executable, "-m", "app.main"],
                cwd=ROOT,
                env=environment,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
            base_url = f"http://127.0.0.1:{port}"
            try:
                wait_ready(process, base_url)
                deadline = started + duration_seconds
                cycle = 0
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        failures.append(f"service exited with {process.returncode}")
                        break
                    cycle += 1
                    for endpoint in DEFAULT_ENDPOINTS:
                        try:
                            get_json(base_url, endpoint)
                        except (
                            OSError,
                            RuntimeError,
                            json.JSONDecodeError,
                        ) as error:
                            failures.append(
                                f"cycle {cycle} {endpoint}: "
                                f"{type(error).__name__}: {error}"
                            )
                    info = get_json(base_url, "/api/v1/info")
                    runtime = info["runtime"]
                    samples.append(
                        {
                            "elapsed_seconds": round(time.monotonic() - started, 2),
                            "rss_kib": rss_kib(process.pid),
                            "threads": runtime["threads"],
                            "file_descriptors": runtime["file_descriptors"]["open"],
                        }
                    )
                    time.sleep(
                        min(interval_seconds, max(0.0, deadline - time.monotonic()))
                    )
                get_json(
                    base_url, "/api/v1/research/backup/auto", method="POST"
                )
            finally:
                if process.poll() is None:
                    process.send_signal(signal.SIGTERM)
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
            log.flush()
        service_log = log_path.read_text(encoding="utf-8", errors="replace")
        unexpected_log = [
            line
            for line in service_log.splitlines()
            if "Traceback (most recent call last)" in line
            or "ERROR:" in line
            or "CRITICAL:" in line
        ]
        failures.extend(unexpected_log)
        database = verify_database(data_dir)
        backups = sorted((data_dir / "backups").glob("*.db"))
        for backup in backups:
            connection = sqlite3.connect(backup)
            try:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    failures.append(f"{backup.name}: quick_check failed")
            finally:
                connection.close()

    rss_values = [item["rss_kib"] for item in samples if item["rss_kib"] is not None]
    thread_values = [item["threads"] for item in samples]
    fd_values = [
        item["file_descriptors"]
        for item in samples
        if item["file_descriptors"] is not None
    ]
    if len(fd_values) >= 2 and fd_values[-1] > fd_values[0] + 12:
        failures.append("file descriptor count grew beyond tolerance")
    if len(thread_values) >= 2 and thread_values[-1] > thread_values[0] + 5:
        failures.append("thread count grew beyond tolerance")
    if len(rss_values) >= 2 and rss_values[-1] > rss_values[0] * 1.5 + 50 * 1024:
        failures.append("RSS grew beyond tolerance")
    if database["quick_check"] != "ok" or database["foreign_key_errors"]:
        failures.append("database integrity gate failed")

    report = {
        "status": "ok" if not failures else "failed",
        "started_at": started_wall.isoformat().replace("+00:00", "Z"),
        "duration_seconds": round(time.monotonic() - started, 2),
        "requested_duration_seconds": duration_seconds,
        "cycles": len(samples),
        "failures": failures,
        "resources": {
            "rss_kib": {
                "start": rss_values[0] if rss_values else None,
                "end": rss_values[-1] if rss_values else None,
                "max": max(rss_values) if rss_values else None,
            },
            "threads": {
                "start": thread_values[0] if thread_values else None,
                "end": thread_values[-1] if thread_values else None,
                "max": max(thread_values) if thread_values else None,
            },
            "file_descriptors": {
                "start": fd_values[0] if fd_values else None,
                "end": fd_values[-1] if fd_values else None,
                "max": max(fd_values) if fd_values else None,
            },
        },
        "database": database,
        "backup_count": len(backups),
    }
    if failures:
        raise RuntimeError(json.dumps(report, ensure_ascii=False, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=float, default=5)
    parser.add_argument("--port", type=int, default=18765)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = run_soak(
        duration_seconds=max(10, args.duration_seconds),
        interval_seconds=max(0.2, args.interval_seconds),
        port=args.port,
    )
    text = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
