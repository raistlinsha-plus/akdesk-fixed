#!/usr/bin/env python3
"""Exercise macOS launch/stop scripts without touching real data or market feeds."""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener


def run(root: Path, browser: bool = False) -> None:
    with tempfile.TemporaryDirectory(prefix="akdesk-release-smoke-") as temp:
        workspace = Path(temp)
        bin_dir = workspace / "bin"
        bin_dir.mkdir()
        (bin_dir / "security").symlink_to(shutil.which("false") or "/usr/bin/false")
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        env = {
            "HOME": temp,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "AKDESK_DATA_DIR": str(workspace / "demo-data"),
            "AKDESK_NO_BROWSER": "1",
            "AKDESK_NONINTERACTIVE": "1",
            "AKDESK_PORT": str(port),
            "AKDESK_NOTIFICATIONS": "0",
            "PIP_NO_INDEX": "1",
        }
        # Treat all inherited keys/configuration as private. Use the existing
        # installed Python runtime; the smoke test never installs dependencies.
        assert (root / ".venv/bin/python").is_file(), "prepare dependencies first"
        opener = build_opener(ProxyHandler({}))

        def invoke(name: str, *, directory: Path = root, **overrides):
            return subprocess.run(
                [str(directory / name)], cwd=directory, env=env | overrides,
                capture_output=True, text=True, timeout=20, check=False,
            )

        with tempfile.TemporaryFile(mode="w+b") as log:
            service = subprocess.Popen(
                [str(root / "start-macos-demo.command")],
                cwd=root, env=env, stdout=log, stderr=subprocess.STDOUT,
            )
            try:
                for _ in range(125):
                    if service.poll() is not None:
                        log.seek(0)
                        raise RuntimeError(log.read().decode(errors="replace"))
                    try:
                        with opener.open(f"http://127.0.0.1:{port}/api/v1/local-instance", timeout=1) as response:
                            instance = json.load(response)
                        break
                    except OSError:
                        time.sleep(0.2)
                else:
                    raise RuntimeError("service did not become ready")
                assert instance["pid"] == service.pid and instance["demo"] is True
                assert invoke("start-macos-demo.command").returncode == 0
                for script, settings in [
                    ("start-macos.command", {}),
                    ("start-macos-demo.command", {"AKDESK_DATA_DIR": str(workspace / "other-data")}),
                ]:
                    rejected = invoke(script, **settings)
                    assert rejected.returncode != 0 and "未复用" in rejected.stdout
                assert not (workspace / "other-data").exists()
                other = workspace / "other-install"
                (other / "scripts").mkdir(parents=True)
                (other / "backend/app").mkdir(parents=True)
                for relative in ("scripts/launcher.py", "backend/app/__init__.py",
                                 "backend/app/paths.py", "stop-macos.command"):
                    shutil.copy2(root / relative, other / relative)
                rejected = invoke("stop-macos.command", directory=other, AKDESK_PYTHON=sys.executable)
                assert rejected.returncode != 0 and "未执行终止" in rejected.stderr
                assert service.poll() is None
                if browser:
                    subprocess.run(
                        ["node", str(Path(__file__).with_name("smoke_release_browser.mjs")),
                         f"http://127.0.0.1:{port}", str(workspace)],
                        # Chrome gets an isolated profile. macOS Chrome still
                        # needs the OS user's home for its platform bootstrap.
                        check=True, timeout=90, env=env | {"HOME": str(Path.home())},
                    )
                assert invoke("stop-macos.command").returncode == 0
                service.wait(timeout=12)
                print(f"PASS v{instance['version']}: reuse, mode/data conflict, other install refusal, custom-port stop")
            finally:
                if service.poll() is None:
                    service.terminate()
                    service.wait(timeout=12)


if __name__ == "__main__":
    args = [arg for arg in sys.argv[1:] if arg != "--browser"]
    run(Path(args[0]).resolve() if args else Path(__file__).resolve().parents[1], "--browser" in sys.argv)
