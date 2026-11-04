import io
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import redirect_stdout
from datetime import date, datetime
from types import SimpleNamespace

import pandas as pd
import pytest

from app import aux_worker, source_worker
from app.provider import (
    AUX_RESULT_MARKER,
    DataService,
    PUSH2_COOLDOWN_ENV,
    PUSH2_COOLDOWN_SECONDS,
    PUSH2_SOURCE,
    SOURCE_RESULT_MARKER,
    SourceRateLimitError,
    is_rate_limit_error,
)


RateLimitError = type(
    "RateLimitError", (Exception,), {"__module__": "akshare.exceptions"}
)
Push2RateLimitError = type(
    "Push2RateLimitError", (RateLimitError,), {"__module__": "akshare.utils.http"}
)


@pytest.fixture
def worker_protocol(monkeypatch, request):
    """Run both worker entry points in memory; no child, network, key or DB."""
    monkeypatch.setenv("AKDESK_DEMO", "0")
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_ATTEMPTS", "3")
    # Source observation dates are independent of the cooldown's artificial
    # clock. Advancing time.time() can otherwise make date.today() cross
    # midnight while provider datetime.now() remains on the preceding day.
    observation_date = date.today()
    started = time.time()
    if getattr(request, "param", None) == "near_midnight":
        started = datetime.now().replace(hour=23, minute=58, second=0, microsecond=0).timestamp()
    clock = [started]
    monkeypatch.setattr("app.provider.time.time", lambda: clock[0])
    state = {
        "primary": 0,
        "fallback": 0,
        "lpr": 0,
        "source_processes": 0,
        "fail_fallback": False,
        "limit_lpr": False,
        "payloads": [],
    }

    def primary():
        state["primary"] += 1
        if state["primary"] == 1:
            raise Push2RateLimitError("raw upstream response must not be forwarded")
        return pd.DataFrame(
            [{"转债代码": "113002", "转债名称": "测试转债", "转债最新价": 112.5}]
        )

    def fallback():
        state["fallback"] += 1
        if state["fail_fallback"]:
            raise RuntimeError("fallback unavailable")
        return pd.DataFrame([{"code": "113002", "name": "测试转债", "trade": 112.5}])

    def lpr():
        state["lpr"] += 1
        if state["limit_lpr"]:
            raise RateLimitError("another upstream is limited")
        return pd.DataFrame([{"TRADE_DATE": observation_date, "LPR1Y": 3.0, "LPR5Y": 3.5}])

    monkeypatch.setitem(
        sys.modules,
        "akshare",
        SimpleNamespace(
            bond_cov_comparison=primary,
            bond_zh_hs_cov_spot=fallback,
            macro_china_lpr=lpr,
        ),
    )

    def fake_run(args, **kwargs):
        assert args[1] == "-m"
        module = args[2]
        assert module in {"app.source_worker", "app.aux_worker"}
        if module == "app.source_worker":
            state["source_processes"] += 1
        output = io.StringIO()
        with monkeypatch.context() as child:
            child.setattr(sys, "argv", args[2:])
            # Reproduce only the worker-specific environment. No application
            # entry point, persistent cache or security configuration is loaded.
            for name in (
                "AKDESK_DEMO",
                "AKDESK_NOTIFICATIONS",
                "AKDESK_SOURCE_WORKER",
                "AKDESK_SOURCE_ATTEMPTS",
                PUSH2_COOLDOWN_ENV,
            ):
                if name in kwargs["env"]:
                    child.setenv(name, kwargs["env"][name])
                else:
                    child.delenv(name, raising=False)
            with redirect_stdout(output):
                if module == "app.source_worker":
                    source_worker.main()
                else:
                    aux_worker.main()
        stdout = output.getvalue()
        marker = (
            SOURCE_RESULT_MARKER if module == "app.source_worker" else AUX_RESULT_MARKER
        )
        payload = json.loads(stdout.strip().removeprefix(marker))
        state["payloads"].append((module, payload))
        return subprocess.CompletedProcess(
            args=args, returncode=0, stdout=stdout, stderr=""
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    return DataService(), state, clock


def test_limit_detection_uses_exception_identity_not_error_text() -> None:
    assert is_rate_limit_error(RateLimitError("anything"))
    assert is_rate_limit_error(Push2RateLimitError("anything"))
    assert not is_rate_limit_error(RuntimeError("RateLimitError: 429 限流"))
    unrelated = type("RateLimitError", (Exception,), {"__module__": "other.service"})
    assert not is_rate_limit_error(unrelated("429"))


@pytest.mark.parametrize("worker_protocol", ["default", "near_midnight"], indirect=True)
def test_push2_cooldown_survives_successful_fallback_and_force(worker_protocol) -> None:
    service, state, clock = worker_protocol
    started = clock[0]

    first = service.convertibles(force=True)

    assert not first.meta.demo
    assert first.meta.source == "AKShare / Sina (备用行情)"
    assert first.data[0]["data_tier"] == "price_only"
    assert first.data[0]["research_eligible"] is False
    assert "限流冷却" in first.meta.warnings[0]
    assert state["primary"] == 1
    assert state["fallback"] == 1
    until = service.upstream_cooldowns()[PUSH2_SOURCE]
    assert until >= started + PUSH2_COOLDOWN_SECONDS
    assert service.source_activity()["circuits"] == {}

    clock[0] = started + 299
    forced = service.convertibles(force=True)
    assert forced.meta.source == "AKShare / Sina (备用行情)"
    assert state["primary"] == 1
    assert state["fallback"] == 2
    assert service.upstream_cooldowns()[PUSH2_SOURCE] == until

    # Eastmoney datacenter-web LPR is not the restricted push2 source.
    lpr = service.money_lpr(force=True)
    assert not lpr.meta.demo
    assert state["lpr"] == 1
    assert service.upstream_cooldowns()[PUSH2_SOURCE] == until
    assert "upstream_cooldowns" not in state["payloads"][-1][1]

    clock[0] = until + 0.01
    recovered = service.convertibles(force=True)
    assert not recovered.meta.demo
    assert recovered.meta.source == "AKShare / Eastmoney"
    assert state["primary"] == 2
    assert state["fallback"] == 2
    assert service.upstream_cooldowns() == {}


def test_worker_limit_failure_is_structured_and_not_retried(worker_protocol) -> None:
    service, state, _clock = worker_protocol
    state["fail_fallback"] = True

    unavailable = service.convertibles(force=True)

    assert unavailable.meta.demo
    assert state["primary"] == 1
    assert state["fallback"] == 1
    assert state["source_processes"] == 1
    assert PUSH2_SOURCE in service.upstream_cooldowns()
    primary_payload = next(
        payload
        for module, payload in state["payloads"]
        if module == "app.aux_worker" and payload.get("rate_limited")
    )
    assert primary_payload["error_type"] == "rate_limit"
    assert primary_payload["upstream_source"] == PUSH2_SOURCE
    assert "raw upstream" not in primary_payload["error"]
    source_payload = state["payloads"][-1][1]
    assert source_payload["rate_limited"] is True
    assert source_payload["error_type"] == "rate_limit"
    assert source_payload["upstream_cooldowns"] == service.upstream_cooldowns()


def test_non_push2_worker_limit_keeps_type_without_push2_cooldown(
    worker_protocol,
) -> None:
    service, state, _clock = worker_protocol
    state["limit_lpr"] = True

    unavailable = service.money_lpr(force=True)

    assert unavailable.meta.demo
    assert state["lpr"] == 1
    assert state["source_processes"] == 1
    assert service.upstream_cooldowns() == {}
    payload = state["payloads"][-1][1]
    assert payload["rate_limited"] is True
    assert payload["error_type"] == "rate_limit"
    assert "upstream_source" not in payload


def test_fallback_failure_keeps_previous_real_cache_and_source(worker_protocol) -> None:
    service, state, clock = worker_protocol
    first = service.convertibles(force=True)
    until = service.upstream_cooldowns()[PUSH2_SOURCE]
    state["fail_fallback"] = True
    clock[0] += 1

    cached = service.convertibles(force=True)

    assert not cached.meta.demo
    assert cached.meta.stale
    assert cached.meta.source == first.meta.source == "AKShare / Sina (备用行情)"
    assert cached.data == first.data
    assert state["primary"] == 1
    assert state["fallback"] == 2
    assert service.upstream_cooldowns()[PUSH2_SOURCE] == until


def test_first_short_worker_deadline_gets_full_window_without_sliding(
    monkeypatch,
) -> None:
    monkeypatch.setenv("AKDESK_DEMO", "0")
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    clock = [time.time()]
    monkeypatch.setattr("app.provider.time.time", lambda: clock[0])
    service = DataService()
    short = {PUSH2_SOURCE: clock[0] + 1}
    # A known source in structured cooldown metadata is sufficient even when
    # an older worker did not also send upstream_source.
    service._remember_rate_limit(SourceRateLimitError(cooldowns=short))
    until = service.upstream_cooldowns()[PUSH2_SOURCE]
    assert until == clock[0] + PUSH2_COOLDOWN_SECONDS

    clock[0] += 250
    service._remember_rate_limit(
        SourceRateLimitError(upstream_source=PUSH2_SOURCE, cooldowns=short)
    )
    assert service.upstream_cooldowns()[PUSH2_SOURCE] == until


def test_parallel_forced_refreshes_share_one_push2_cooldown(monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_DEMO", "0")
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    service = DataService()
    calls = {"primary": 0, "fallback": 0}

    def fake_aux(task, **_kwargs):
        if task == "convertibles_comparison":
            calls["primary"] += 1
            time.sleep(0.01)
            raise SourceRateLimitError(upstream_source=PUSH2_SOURCE)
        calls["fallback"] += 1
        return {"rows": [{"code": "113002", "name": "测试转债", "price": 112.5}]}

    monkeypatch.setattr(service, "_call_aux_worker", fake_aux)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _i: service.convertibles(force=True), range(8)))

    assert calls == {"primary": 1, "fallback": 8}
    assert all(item.meta.source == "AKShare / Sina (备用行情)" for item in results)
    assert all(not item.meta.demo for item in results)


@pytest.mark.parametrize("ok", [True, False])
def test_worker_short_deadline_is_clamped_on_success_and_failure(
    monkeypatch, ok
) -> None:
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    clock = [time.time()]
    monkeypatch.setattr("app.provider.time.time", lambda: clock[0])
    service = DataService()
    payload = {
        "ok": ok,
        "data": [{"price": 112.5}],
        "error_type": "rate_limit" if not ok else None,
        "upstream_cooldowns": {PUSH2_SOURCE: clock[0] + 1},
    }

    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=SOURCE_RESULT_MARKER + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    if ok:
        service._call_with_timeout("convertibles", lambda: ([], None))
    else:
        with pytest.raises(SourceRateLimitError):
            service._call_with_timeout("convertibles", lambda: ([], None))
    assert service.upstream_cooldowns()[PUSH2_SOURCE] == clock[0] + 300


def test_new_service_does_not_persist_process_local_cooldown(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    original = DataService()
    original._remember_rate_limit(SourceRateLimitError(upstream_source=PUSH2_SOURCE))

    assert PUSH2_SOURCE in original.upstream_cooldowns()
    assert DataService().upstream_cooldowns() == {}


def test_legacy_worker_success_payload_remains_compatible(monkeypatch) -> None:
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    service = DataService()
    payload = {"ok": True, "data": [{"value": 1}], "observation_time": None}

    def fake_run(args, **_kwargs):
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=SOURCE_RESULT_MARKER + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    assert service._call_with_timeout("money_lpr", lambda: ([], None)) == (
        [{"value": 1}],
        None,
    )
    assert service.upstream_cooldowns() == {}


def test_generic_akshare_limit_skips_retry_without_blocking_push2(monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_DEMO", "0")
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_ATTEMPTS", "3")
    service = DataService()
    calls = 0

    def limited():
        nonlocal calls
        calls += 1
        raise RateLimitError("not a push2 endpoint")

    with pytest.raises(RateLimitError):
        service._load_live("money_lpr", limited)
    assert calls == 1
    assert service.upstream_cooldowns() == {}


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "not-a-time"])
def test_invalid_worker_cooldown_is_not_restored(monkeypatch, value) -> None:
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.setenv(PUSH2_COOLDOWN_ENV, value)
    assert DataService().upstream_cooldowns() == {}


def test_unstructured_error_does_not_create_a_limit(monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_SOURCE_WORKER", "1")
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    monkeypatch.setenv("AKDESK_SOURCE_ATTEMPTS", "2")
    monkeypatch.setattr("app.provider.time.sleep", lambda _seconds: None)
    service = DataService()
    calls = 0

    def ordinary_failure():
        nonlocal calls
        calls += 1
        raise RuntimeError("429 限流 RateLimitError but no typed exception")

    with pytest.raises(RuntimeError):
        service._load_live("money_lpr", ordinary_failure)
    assert calls == 2
    assert service.upstream_cooldowns() == {}


def test_source_runner_preserves_generic_rate_limit_metadata(monkeypatch) -> None:
    monkeypatch.setenv("AKDESK_DEMO", "0")
    monkeypatch.delenv("AKDESK_SOURCE_WORKER", raising=False)
    monkeypatch.delenv(PUSH2_COOLDOWN_ENV, raising=False)
    service = DataService()
    calls = []

    def fake_run(args, **kwargs):
        calls.append(kwargs["env"])
        payload = {"ok": False, "error_type": "rate_limit", "rate_limited": True}
        return subprocess.CompletedProcess(
            args=args,
            returncode=0,
            stdout=SOURCE_RESULT_MARKER + json.dumps(payload),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(SourceRateLimitError):
        service._load_live("money_lpr", lambda: ([], None))
    assert len(calls) == 1
    assert PUSH2_COOLDOWN_ENV not in calls[0]
    assert service.upstream_cooldowns() == {}
