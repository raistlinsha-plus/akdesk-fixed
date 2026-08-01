from __future__ import annotations

from types import SimpleNamespace

from app.settings import AiHubMixSecretStore, FredSecretStore


def test_keychain_write_keeps_secret_out_of_process_arguments(monkeypatch) -> None:
    key = "a" * 32
    captured: dict = {}

    def run(args, **kwargs):
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        captured["start_new_session"] = kwargs.get("start_new_session")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.settings.sys.platform", "darwin")
    monkeypatch.setattr("app.settings.shutil.which", lambda _name: "/usr/bin/security")
    monkeypatch.setattr("app.settings.subprocess.run", run)
    monkeypatch.setattr("app.settings.getpass.getuser", lambda: "tester")

    store = FredSecretStore()
    store.set(key)

    assert key not in captured["args"]
    assert captured["args"][-1] == "-w"
    assert captured["input"] == f"{key}\n{key}\n"
    # Detaching the child session prevents macOS security from bypassing the
    # stdin pipe and prompting on the parent launcher's terminal.
    assert captured["start_new_session"] is True
    assert store.get() == key


def test_aihubmix_keychain_write_keeps_secret_out_of_process_arguments(
    monkeypatch,
) -> None:
    key = "sk-" + "A1" * 20
    captured: dict = {}

    def run(args, **kwargs):
        captured["args"] = args
        captured["input"] = kwargs.get("input")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr("app.settings.sys.platform", "darwin")
    monkeypatch.setattr("app.settings.shutil.which", lambda _name: "/usr/bin/security")
    monkeypatch.setattr("app.settings.subprocess.run", run)
    monkeypatch.setattr("app.settings.getpass.getuser", lambda: "tester")

    store = AiHubMixSecretStore()
    store.set(key)

    assert key not in captured["args"]
    assert captured["args"][-1] == "-w"
    assert captured["input"] == f"{key}\n{key}\n"
    assert store.status().source == "keychain"
