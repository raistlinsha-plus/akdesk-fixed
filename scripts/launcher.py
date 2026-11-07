#!/usr/bin/env python3
"""Local launcher identity and safe, scoped stop. No third-party imports."""

from __future__ import annotations

import http.client
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.paths import default_data_dir, launch_port, path_id  # noqa: E402

NOT_RUNNING = 3
CONFLICT = 4


def identity(port: int) -> dict | None:
    connection = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
    try:
        connection.connect()
    except ConnectionRefusedError:
        return None
    try:
        connection.request("GET", "/api/v1/local-instance", headers={"Connection": "close"})
        with connection.getresponse() as response:
            if response.status != 200:
                return {}
            payload = json.loads(response.read(4097))
            return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, http.client.HTTPException):
        return {}
    finally:
        connection.close()


def matches(payload: dict, root: Path, version: str, *, for_start: bool) -> bool:
    same_install = (
        payload.get("name") == "AKDesk Fixed"
        and payload.get("version") == version
        and payload.get("root_id") == path_id(root)
        and type(payload.get("pid")) is int
        and payload["pid"] > 1
    )
    if not same_install or not for_start:
        return same_install
    return (
        payload.get("data_id") == path_id(default_data_dir(root))
        and payload.get("demo") is (os.getenv("AKDESK_DEMO") == "1")
    )


def listeners(port: int) -> set[int]:
    result = subprocess.run(
        ["lsof", "-nP", f"-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True, text=True, timeout=3, check=False,
    )
    if result.returncode not in (0, 1) or result.stderr:
        raise RuntimeError("无法核对端口监听进程")
    return {int(pid) for pid in result.stdout.split()}


def stop(port: int, version: str) -> int:
    before = listeners(port)
    if not before:
        print("AKDesk 服务当前没有运行。")
        return 0
    payload = identity(port)
    if not payload or not matches(payload, ROOT, version, for_start=False):
        raise RuntimeError("端口上的进程不属于此安装目录与版本，未执行终止")
    pid = payload["pid"]
    if before != {pid} or listeners(port) != before:
        raise RuntimeError("端口监听进程不唯一或已变化，未执行终止")
    print(f"正在正常停止 AKDesk（PID {pid}）……", flush=True)
    os.kill(pid, signal.SIGTERM)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if pid not in listeners(port):
            print("AKDesk 已释放服务端口。")
            return 0
        time.sleep(0.25)
    raise RuntimeError("服务未在 10 秒内释放端口，请检查原启动窗口")


def main() -> int:
    operation = sys.argv[1]
    try:
        port = launch_port()
        if operation == "port":
            print(port)
            return 0
        version = sys.argv[2]
        if operation == "stop":
            return stop(port, version)
        if operation != "probe":
            raise ValueError("未知启动器操作")
        payload = identity(port)
        if payload is None:
            # An IPv6-only listener may not respond at 127.0.0.1.
            if listeners(port):
                raise RuntimeError("端口已被其他进程占用")
            return NOT_RUNNING
        if matches(payload, ROOT, version, for_start=True):
            return 0
        raise RuntimeError("端口上运行着不同安装、版本、模式或数据目录的实例。请在原启动窗口停止它，或选择其他 AKDESK_PORT")
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"无法{ '停止' if operation == 'stop' else '启动' }：{exc}", file=sys.stderr)
        return CONFLICT


if __name__ == "__main__":
    raise SystemExit(main())
