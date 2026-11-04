from __future__ import annotations

import importlib.metadata
import re
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("installed", ["9.9.9", "9.9.8"])
def test_launcher_reads_the_expected_akshare_version_from_the_lock(
    tmp_path, monkeypatch, installed
) -> None:
    source = (Path(__file__).resolve().parents[2] / "start-macos.command").read_text(
        encoding="utf-8"
    )
    match = re.search(
        r'! "\$VENV/bin/python" -c \'([^\']+)\' "\$REQUIREMENTS_LOCK"', source
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
