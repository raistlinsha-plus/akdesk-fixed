from __future__ import annotations

from pathlib import Path

from app.paths import default_data_dir


def test_explicit_data_dir_has_priority(tmp_path, monkeypatch) -> None:
    configured = tmp_path / "configured"
    monkeypatch.setenv("AKDESK_DATA_DIR", str(configured))
    assert default_data_dir(tmp_path / "project") == configured.resolve()


def test_legacy_database_is_preserved(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_DATA_DIR", raising=False)
    project = tmp_path / "project"
    legacy = project / "data"
    legacy.mkdir(parents=True)
    (legacy / "akdesk-fixed.db").touch()
    assert default_data_dir(project) == legacy


def test_clean_macos_install_uses_application_support(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.delenv("AKDESK_DATA_DIR", raising=False)
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    monkeypatch.setattr("app.paths.sys.platform", "darwin")
    assert default_data_dir(tmp_path / "project") == (
        tmp_path / "home" / "Library" / "Application Support" / "AKDesk Fixed"
    )
