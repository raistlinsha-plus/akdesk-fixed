from __future__ import annotations

import importlib
import json
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.diagnostics import build_diagnostics, error_category, storage_summary
from app.models import HealthItem
from app.settings import SecretStatus
from scripts import preflight


@pytest.mark.parametrize(
    "message,expected",
    [
        ("CERTIFICATE_VERIFY_FAILED", "certificate"),
        ("HTTP 429 Too Many Requests", "rate_limit"),
        ("HTTP 401 API Key invalid", "credentials"),
        ("SourceTimeoutError: 请求超时", "timeout"),
        ("ConnectionError: network failure", "network"),
        ("KeyError: 缺少字段", "source_format"),
        ("源进程异常退出", "source_process"),
        ("unexpected upstream body", "upstream_unavailable"),
    ],
)
def test_error_classification_never_returns_raw_message(message, expected):
    assert error_category(message) == expected
    assert error_category(None, "healthy") == "none"


def test_diagnostics_only_exports_allowlisted_metadata(tmp_path, monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path / "private-user"))
    secret = "sk-" + "test-only-placeholder" * 3
    private = str(tmp_path / "private-user" / "research.db")
    item = HealthItem(
        adapter="money_rates",
        label=secret,
        state="degraded",
        message=f"ConnectionError: {secret} {private} 私有研究正文",
        quality_issues=[private, secret],
        cache_age_seconds=120,
        cache_persisted=True,
        consecutive_failures=2,
    )
    report = build_diagnostics(
        [item],
        data_dir=tmp_path / "private-user",
        project_root=tmp_path,
        demo_only=False,
    )
    text = json.dumps(report, ensure_ascii=False)
    assert secret not in text
    assert str(tmp_path) not in text
    assert "私有研究正文" not in text
    assert "message" not in report["adapters"][0]
    assert report["adapters"][0]["error_category"] == "network"
    assert report["adapters"][0]["cache_age_seconds"] == 120
    assert report["storage"]["type"] == "custom"
    assert report["privacy"]["automatic_upload"] is False
    assert not (tmp_path / "private-user").exists()


def test_diagnostics_rejects_unknown_identifier_and_host_text(tmp_path, monkeypatch):
    monkeypatch.setattr("app.diagnostics.platform.system", lambda: "Darwin")
    monkeypatch.setattr(
        "app.diagnostics.platform.mac_ver", lambda: ("private-hostname", (), "")
    )
    monkeypatch.setattr("app.diagnostics.platform.machine", lambda: "private-machine")
    report = build_diagnostics(
        [HealthItem(adapter="private_secret", label="private", state="not_checked")],
        data_dir=tmp_path,
        project_root=tmp_path,
        demo_only=True,
    )
    assert report["adapters"][0]["adapter"] == "unknown"
    assert report["environment"]["os_version"] == "unknown"
    assert report["environment"]["architecture"] == "unknown"


def test_diagnostics_unchecked_source_is_not_claimed_trusted(tmp_path):
    item = HealthItem(adapter="money_rates", label="资金", state="not_checked")
    assert item.trust_level == "trusted"
    report = build_diagnostics(
        [item], data_dir=tmp_path, project_root=tmp_path, demo_only=False
    )
    adapter = report["adapters"][0]
    assert adapter["state"] == "not_checked"
    assert adapter["research_status"] == "unchecked"
    assert adapter["trust_level"] == "unavailable"
    assert adapter["error_category"] == "none"
    assert item.trust_level == "trusted"  # No global model/service mutation.


def test_diagnostics_only_classifies_explicit_demo_mode_as_intentional(tmp_path):
    for demo_only, execution_mode, message, expected in (
        (True, "local_demo", "演示模式", "demo_mode"),
        (False, "local_demo", "演示模式", "unknown"),
        (True, "isolated_process", "演示模式", "unknown"),
        (True, "local_demo", "ConnectionError: network failure", "network"),
        (False, "local_demo", "ConnectionError: network failure", "network"),
    ):
        item = HealthItem(
            adapter="money_rates",
            label="资金",
            state="degraded",
            execution_mode=execution_mode,
            trust_level="unavailable",
            message=message,
        )
        report = build_diagnostics(
            [item], data_dir=tmp_path, project_root=tmp_path, demo_only=demo_only
        )
        assert report["adapters"][0]["error_category"] == expected


def test_storage_summary_preserves_legacy_classification(tmp_path, monkeypatch):
    monkeypatch.delenv("AKDESK_DATA_DIR", raising=False)
    assert storage_summary(tmp_path / "data", tmp_path)["type"] == "legacy_project"


def test_diagnostics_endpoint_does_not_read_credentials_or_fetch(tmp_path, monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AKDESK_DEMO", "1")
    monkeypatch.setenv("AKDESK_NO_BROWSER", "1")
    # Main's existing service constructors inspect status at startup. Stub that
    # before import, then reject even status reads during diagnostics itself.
    monkeypatch.setattr(
        "app.settings.FredSecretStore.status", lambda self: SecretStatus(False, "none")
    )
    monkeypatch.setattr(
        "app.settings.AiHubMixSecretStore.status",
        lambda self: SecretStatus(False, "none"),
    )
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("diagnostics must not inspect keys or fetch data")

    monkeypatch.setattr(main.fred_secret_store, "get", forbidden)
    monkeypatch.setattr(main.fred_secret_store, "status", forbidden)
    monkeypatch.setattr(main.aihubmix_secret_store, "get", forbidden)
    monkeypatch.setattr(main.aihubmix_secret_store, "status", forbidden)
    monkeypatch.setattr(main.macro_service, "health_item", forbidden)
    monkeypatch.setattr(main.world_bank_service, "health_item", forbidden)
    monkeypatch.setattr(main.gdelt_service, "health_item", forbidden)
    monkeypatch.setattr(main.service, "_load", forbidden)
    # No lifespan: testing this route must not prewarm a source.
    client = TestClient(main.app)
    response = client.get("/api/v1/diagnostics")
    assert response.status_code == 200
    report = response.json()
    assert report["schema_version"] == 1
    assert len(report["adapters"]) == 15
    assert report["app"]["mode"] == "demo"
    assert str(tmp_path) not in response.text


def test_preflight_reports_missing_release_without_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path / "personal-data"))
    report = preflight.inspect_environment(tmp_path)
    assert report["ok"] is False
    check = next(item for item in report["checks"] if item["code"] == "release_files")
    assert check["status"] == "error"
    assert "GitHub Releases" in check["recovery"]
    assert str(tmp_path) not in json.dumps(report)
    assert not (tmp_path / "personal-data").exists()


def test_preflight_classifies_permissions_and_certificate_recovery(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(preflight.os, "access", lambda *_args: False)
    monkeypatch.setattr(
        preflight.ssl,
        "get_default_verify_paths",
        lambda: SimpleNamespace(cafile=None, capath=None),
    )
    report = preflight.inspect_environment(tmp_path)
    by_code = {item["code"]: item for item in report["checks"]}
    assert by_code["project_writable"]["status"] == "error"
    assert by_code["certificates"]["status"] == "warning"
    assert "不要关闭" in by_code["certificates"]["recovery"]


def test_preflight_clean_install_with_available_release(tmp_path, monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setattr(preflight.sys, "version_info", (3, 13, 0))
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/requirements.lock").touch()
    (tmp_path / "frontend/dist").mkdir(parents=True)
    (tmp_path / "frontend/dist/index.html").touch()
    assert preflight.inspect_environment(tmp_path)["ok"] is True
    assert not (tmp_path / "data").exists()


def test_preflight_relative_data_directory_matches_launcher_root(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    (root / "runtime").mkdir()
    other = tmp_path / "other-working-directory"
    other.mkdir()
    (other / "runtime").mkdir()
    monkeypatch.chdir(other)
    monkeypatch.setenv("AKDESK_DATA_DIR", "runtime")
    monkeypatch.setattr(
        preflight.os, "access", lambda path, _mode: path != root / "runtime"
    )
    report = preflight.inspect_environment(root)
    by_code = {item["code"]: item for item in report["checks"]}
    assert by_code["data_writable"]["status"] == "error"
    assert str(tmp_path) not in json.dumps(report)
