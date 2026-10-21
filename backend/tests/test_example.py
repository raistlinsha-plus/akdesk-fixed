from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from examples import fixed_income_brief
from examples.fixed_income_brief import live_brief, render_markdown, synthetic_brief


def test_synthetic_cli_is_reproducible_without_site_packages(tmp_path):
    script = Path(__file__).resolve().parents[2] / "examples/fixed_income_brief.py"
    command = [sys.executable, "-I", "-S", str(script)]
    first = subprocess.run(command, capture_output=True, text=True, check=True)
    second = subprocess.run(command, capture_output=True, text=True, check=True)
    assert first.stdout == second.stdout
    assert "固定合成示例 · 非真实市场" in first.stdout
    assert "—（缺失）" in first.stdout
    assert "+0.00" in first.stdout
    output = tmp_path / "brief.md"
    subprocess.run(command + ["--output", str(output)], check=True, capture_output=True)
    assert output.read_text(encoding="utf-8") == first.stdout


def test_live_example_continues_after_failure_and_discards_demo_fallback():
    calls = []
    private_error = "ConnectionError: private-local-path confidential-token"

    class FakeService:
        health = {"treasury_futures": SimpleNamespace(message="SourceTimeoutError")}

        def money_rates(self, force=False):
            calls.append("money_rates")
            assert force and not self.demo_only and not self.is_source_worker
            assert self.retry_attempts == 1 and self.timeout_seconds == 2
            raise RuntimeError(private_error)

        def yield_curves(self, force=False):
            calls.append("yield_curves")
            fixture = synthetic_brief()["sources"][1]["data"]
            return SimpleNamespace(
                data=fixture,
                meta=SimpleNamespace(
                    demo=False,
                    stale=False,
                    trust_level="trusted",
                    observation_time="2026-07-27",
                    fetched_at=datetime(2026, 7, 27, 16),
                ),
            )

        def treasury_futures(self, force=False):
            calls.append("treasury_futures")
            return SimpleNamespace(
                data=[{"product": "FAKE", "price": 999}],
                meta=SimpleNamespace(
                    demo=True,
                    stale=True,
                    trust_level="unavailable",
                    observation_time=None,
                    fetched_at=datetime(2026, 7, 27, 16),
                ),
            )

    result = live_brief(2, service_factory=FakeService)
    assert calls == ["money_rates", "yield_curves", "treasury_futures"]
    assert [item["status"] for item in result["sources"]] == [
        "unavailable",
        "available",
        "unavailable",
    ]
    assert result["sources"][2]["data"] is None
    text = render_markdown(result)
    assert private_error not in text
    assert "FAKE" not in text
    assert "network" in text and "timeout" in text
    assert "2026-07-27T00:00:00" not in text
    assert result["sources"][1]["observation_time"] == "2026-07-27"
    assert result["sources"][2]["fetched_at"] is None


def test_synthetic_fixture_is_not_mutated_by_consumers():
    first = synthetic_brief()
    first["sources"][0]["data"][0]["value"] = 999
    assert synthetic_brief()["sources"][0]["data"][0]["value"] == 1.41


def test_cli_keeps_failure_brief_and_returns_explicit_status(monkeypatch, tmp_path):
    brief = synthetic_brief()
    brief["mode"] = "live"
    for item in brief["sources"]:
        item.update(status="unavailable", data=None, error_category="timeout")
    monkeypatch.setattr(fixed_income_brief, "live_brief", lambda _timeout: brief)
    output = tmp_path / "failed-brief.md"
    assert fixed_income_brief.main(["--live", "--output", str(output)]) == 2
    assert "不可用（timeout）" in output.read_text(encoding="utf-8")
