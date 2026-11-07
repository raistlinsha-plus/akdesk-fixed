import hashlib
import importlib.metadata
import json
import re
import sys
from pathlib import Path
from unittest.mock import Mock

import pytest

from app.paths import default_data_dir, launch_port, path_id
from scripts import launcher, preflight


@pytest.mark.parametrize("installed", ["9.9.9", "9.9.8"])
def test_launcher_reads_the_expected_akshare_version_from_the_lock(
    tmp_path, monkeypatch, installed
) -> None:
    source = (Path(__file__).resolve().parents[2] / "start-macos.command").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r"""! "\$VENV/bin/python" -c '([^']+)' "\$REQUIREMENTS_LOCK" """.rstrip(), source
    )
    assert match, "启动探测须读取实际锁文件，不能写死历史 SDK 版本"
    lock = tmp_path / "requirements.lock"
    lock.write_text("# isolated test\nakshare==9.9.9\n", encoding="utf-8")
    original = importlib.metadata.version
    monkeypatch.setattr(
        importlib.metadata, "version",
        lambda name: installed if name == "akshare" else original(name),
    )
    monkeypatch.setattr(sys, "argv", ["-c", str(lock)])
    if installed == "9.9.9":
        exec(compile(match.group(1), "launcher-probe", "exec"), {})
    else:
        with pytest.raises(AssertionError):
            exec(compile(match.group(1), "launcher-probe", "exec"), {})


def test_probe_distinguishes_install_mode_and_data(tmp_path, monkeypatch):
    root = tmp_path / "project"
    monkeypatch.setenv("AKDESK_DATA_DIR", "research")
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    payload = {
        "name": "AKDesk Fixed",
        "version": "1.3.2",
        "pid": 42,
        "root_id": path_id(root),
        "data_id": path_id(root / "research"),
        "demo": False,
    }
    assert launcher.matches(payload, root, "1.3.2", for_start=True)
    assert not launcher.matches(payload, tmp_path, "1.3.2", for_start=False)
    assert not launcher.matches({**payload, "demo": True}, root, "1.3.2", for_start=True)
    monkeypatch.setenv("AKDESK_DATA_DIR", "another")
    assert not launcher.matches(payload, root, "1.3.2", for_start=True)
    # Stop is scoped to this installation and port, regardless of demo mode.
    assert launcher.matches(payload, root, "1.3.2", for_start=False)


def test_stop_refuses_unrelated_or_changed_listener(tmp_path, monkeypatch):
    monkeypatch.setattr(launcher, "ROOT", tmp_path)
    monkeypatch.setattr(launcher, "identity", lambda _port: {
        "name": "AKDesk Fixed", "version": "1.3.2",
        "root_id": path_id(tmp_path), "pid": 42,
    })
    kill = Mock()
    monkeypatch.setattr(launcher.os, "kill", kill)
    monkeypatch.setattr(launcher, "listeners", Mock(side_effect=[{42}, {43}]))
    with pytest.raises(RuntimeError, match="已变化"):
        launcher.stop(9876, "1.3.2")
    monkeypatch.setattr(launcher, "listeners", Mock(return_value={42}))
    with pytest.raises(RuntimeError, match="不属于"):
        launcher.stop(9876, "1.3.1")
    kill.assert_not_called()


@pytest.mark.parametrize("value", ["0", "-1", "65536", "９９", "a", ""])
def test_invalid_port(monkeypatch, value):
    monkeypatch.setenv("AKDESK_PORT", value)
    with pytest.raises(ValueError):
        launch_port()


def test_demo_has_separate_default_data_directory(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("AKDESK_DATA_DIR", raising=False)
    root = tmp_path / "project"
    (root / "data/backups").mkdir(parents=True)
    monkeypatch.delenv("AKDESK_DEMO", raising=False)
    assert default_data_dir(root) == root / "data"
    monkeypatch.setenv("AKDESK_DEMO", "1")
    assert default_data_dir(root) != root / "data"


def test_release_preflight_checks_lazy_assets_and_digest(tmp_path):
    dist = tmp_path / "frontend/dist"
    (dist / "assets").mkdir(parents=True)
    (dist / ".vite").mkdir()
    (dist / "index.html").write_text('<script type="module" src="/assets/main.js"></script>')
    (dist / "assets/main.js").write_text("import('./help.js')")
    (dist / ".vite/manifest.json").write_text(json.dumps({
        "index.html": {"isEntry": True, "file": "assets/main.js", "dynamicImports": ["help"]},
        "help": {"file": "assets/help.js"},
    }))
    assert not preflight.frontend_bundle_ready(tmp_path)
    chunk = dist / "assets/help.js"
    chunk.write_text("healthy")
    assert preflight.frontend_bundle_ready(tmp_path)
    files = [{
        "path": p.relative_to(tmp_path).as_posix(),
        "sha256": hashlib.sha256(p.read_bytes()).hexdigest(),
        "size": p.stat().st_size,
    } for p in dist.rglob("*") if p.is_file()]
    (tmp_path / "RELEASE_MANIFEST.json").write_text(json.dumps({"files": files}))
    assert preflight.frontend_bundle_ready(tmp_path)
    chunk.write_text("changed")
    assert not preflight.frontend_bundle_ready(tmp_path)
    chunk.unlink()
    assert not preflight.frontend_bundle_ready(tmp_path)
    chunk.write_text("healthy")
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts/launcher.py").touch()
    (tmp_path / "RELEASE_MANIFEST.json").unlink()
    assert not preflight.frontend_bundle_ready(tmp_path)
