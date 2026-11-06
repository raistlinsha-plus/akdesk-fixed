from __future__ import annotations

import importlib
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.cross_assets import (
    CrossAssetService,
    CrossRateLimit,
    SHANGHAI,
    asset_spec,
    normalize_history,
    normalize_quote,
    number,
    observation,
    reference_payload,
)
from app.database import Database
from app.models import (
    ResearchProjectCreate,
    WorkflowCaptureCreate,
    ResearchEvidenceCreate,
)
from app.workflow import WorkflowConflict, workflow_capture

NOW = datetime(2026, 11, 6, 10, tzinfo=SHANGHAI)


@pytest.mark.parametrize("value", [None, "—", "NaN", "inf", float("nan"), True, "oops"])
def test_bad_numbers_are_missing_not_zero(value):
    assert number(value) is None


def test_observation_never_infers_date_from_fetch_time():
    assert observation("10:00:00", NOW) is None
    assert observation("2026-11-07", NOW) is None
    assert observation("2026年11月06日 09:59:00", NOW) == "2026-11-06T09:59:00+08:00"
    assert observation(None, NOW) is None


def test_history_filters_future_nonfinite_and_conflicting_duplicates():
    data = normalize_history(
        [
            {"date": "2026-11-05", "close": 100},
            {"date": "2026-11-05", "close": 101},
            {"date": "2026-11-04", "close": 90},
            {"date": "2026-11-07", "close": 99},
            {"date": "2026-11-06", "close": "NaN"},
        ],
        NOW,
    )
    assert data == [{"date": "2026-11-04", "close": 90.0}]


def test_quote_does_not_trust_provider_change_or_imply_real_time():
    result = normalize_quote(
        asset_spec("SSE:000001"), {"最新价": 110, "昨收": 100, "涨跌幅": 99}, NOW
    )
    assert result["change_pct"] == 10
    assert result["observation_time"] is None and result["delay_seconds"] is None
    assert result["quality"] == "limited"
    extreme = normalize_quote(asset_spec("SSE:000001"), {"price":1e300,"previous_close":1e-300},NOW)
    assert extreme["change_pct"] is None


def test_memory_cache_singleflight_cooldown_and_no_force_bypass():
    clock = [0.0]
    calls = []

    def run(mode, key):
        calls.append((mode, key))
        if len(calls) > 1:
            raise CrossRateLimit("private upstream details must not escape")
        return [{"symbol": "sh000001", "price": 3100, "previous_close": 3000}]

    service = CrossAssetService(run, demo=False, clock=lambda: clock[0])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: service.quotes("index"), range(4)))
    assert len(calls) == 1 and results[0]["data"][0]["price"] == 3100
    results[0]["data"][0]["price"] = 999
    assert service.peek("SSE:000001")["price"] == 3100
    clock[0] = 301
    result = service.quotes("index")
    assert result["state"] == "stale" and len(calls) == 2
    assert "private upstream" not in json.dumps(result)
    clock[0] = 302
    assert service.quotes("index")["state"] == "stale" and len(calls) == 2
    assert service.peek("SSE:000001")["state"] == "stale"


def test_catalog_and_peek_do_not_fetch_and_invalid_ids_do_not_spawn():
    service = CrossAssetService(lambda *_: pytest.fail("unexpected IO"), demo=False)
    assert len(service.catalog()["assets"]) == 9
    assert service.peek("SGE:Au99.99") is None
    with pytest.raises(ValueError):
        service.history("https://untrusted.example/key")
    with pytest.raises(ValueError):
        service.quotes("stock")


def test_demo_never_uses_real_runner_and_is_explicit():
    service = CrossAssetService(lambda *_: pytest.fail("unexpected IO"), demo=True)
    quote = service.quotes("gold")["data"][0]
    assert quote["demo"] and quote["observation_time"] == "2026-08-03"
    history = service.history("SGE:Au99.99")
    assert history["demo"] and history["data"][-1]["date"] == "2026-08-03"


def test_reference_is_whitelisted_and_capture_atomic_idempotent(tmp_path):
    database = Database(tmp_path / "test.db")
    project = database.add_research_project(ResearchProjectCreate(title="合成项目"))
    body = {
        "kind": "asset_reference",
        "asset_id": "SGE:Au99.99",
        "request_id": str(uuid4()),
        "confirmed": True,
        "note": "自己的文字",
    }
    request = WorkflowCaptureCreate.model_validate(body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(
                lambda _: workflow_capture(database, None, project.id, request),
                range(4),
            )
        )
    assert len({item["entry_id"] for item in results}) == 1
    assert sum(not item["deduplicated"] for item in results) == 1
    saved = database.get_research_project(project.id)
    assert len(saved.evidence) == 1 and len(saved.entries) == 1
    assert saved.evidence[0].payload == reference_payload("SGE:Au99.99")
    assert saved.evidence[0].observation_end is None
    assert (
        database.project_summary(project.id)["supporting_evidence"][0][
            "ai_processing_allowed"
        ]
        is False
    )
    with pytest.raises(WorkflowConflict):
        workflow_capture(
            database,
            None,
            project.id,
            WorkflowCaptureCreate.model_validate({**body, "note": "changed"}),
        )
    for bad in (
        {"price": 700},
        {"report_date": "2026-11-06"},
        {"expected_fetched_at": "2026-11-06"},
        {"asset_id": "UNKNOWN"},
    ):
        with pytest.raises(ValidationError):
            WorkflowCaptureCreate.model_validate({**body, **bad})


def test_reference_import_boundary_and_ai_filter():
    from app.ai_assistant import ai_record_allowed

    item = ResearchEvidenceCreate(
        evidence_type="snapshot",
        title="自己的标题",
        payload={
            **reference_payload("SGE:Au99.99"),
            "price": 999,
            "date": "2026-11-06",
            "nested": {"close": 888},
        },
        observation_end="2026-11-06",
    )
    assert "price" not in item.payload and "nested" not in item.payload
    assert item.observation_end is None
    assert not ai_record_allowed(item)
    assert not ai_record_allowed(item.model_dump())


def test_working_restore_calibrates_tagged_references_without_changing_source(tmp_path):
    database=Database(tmp_path/"source.db")
    project=database.add_research_project(ResearchProjectCreate(title="合成项目"))
    request=WorkflowCaptureCreate(kind="asset_reference",asset_id="SSE:510300",request_id=uuid4(),confirmed=True,note="保留自己的文字")
    workflow_capture(database,None,project.id,request)
    with database._connect() as connection:
        connection.execute("UPDATE research_evidence SET payload=?,observation_end=?",(json.dumps({**reference_payload("SSE:510300"),"prices":[12345],"raw":"drop"}),"2026-11-06"))
    source=tmp_path/"backup.db"
    database.backup_to(source)
    before=source.read_bytes()
    target=Database(tmp_path/"target.db")
    target.restore_from(source)
    assert source.read_bytes()==before
    with target._connect() as connection:
        row=connection.execute("SELECT payload,observation_end FROM research_evidence").fetchone()
        assert json.loads(row["payload"])==reference_payload("SSE:510300")
        assert row["observation_end"] is None
    assert target.get_research_project(project.id).entries[0].content=="保留自己的文字"


def test_api_no_store_unsupported_inputs_watchlist_and_no_numeric_disk(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("AKDESK_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("AKDESK_DEMO", "1")
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    with TestClient(main.app) as client:
        for path in (
            "catalog",
            "quotes?kind=index",
            "quotes?kind=gold",
            "history?asset_id=SGE%3AAu99.99",
        ):
            response = client.get("/api/v1/cross-assets/" + path)
            assert (
                response.status_code == 200
                and response.headers["cache-control"] == "no-store"
            )
        assert (
            client.get("/api/v1/cross-assets/history?asset_id=unknown").status_code
            == 422
        )
        assert client.get("/api/v1/cross-assets/quotes?kind=stock").status_code == 422
        assert (
            client.post(
                "/api/v1/watchlists",
                json={
                    "object_type": "gold",
                    "object_id": "SGE:Au99.99",
                    "name": "untrusted name",
                },
            ).json()["name"]
            == "黄金 Au99.99"
        )
        assert (
            client.post(
                "/api/v1/watchlists",
                json={
                    "object_type": "index",
                    "object_id": "SGE:Au99.99",
                    "name": "bad",
                },
            ).status_code
            == 422
        )
        enriched = client.get("/api/v1/watchlists/enriched").json()[0]
        assert (
            enriched["page"] == "cross-assets"
            and enriched["source_meta"]["demo"] is True
        )
        with main.database._connect() as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 1600
            assert not connection.execute("SELECT 1 FROM research_evidence").fetchall()


def test_etf_uses_selected_history_only_and_peek_never_refreshes():
    clock = [0.0]
    calls = []

    def run(mode, key):
        calls.append((mode, key))
        return [
            {"date": "2026-08-03", "close": 4.01},
            {"date": "2026-08-04", "close": 4.02},
        ]

    service = CrossAssetService(run, demo=False, clock=lambda: clock[0])
    assert service.peek("SSE:510300") is None and not calls
    first = service.etf("SSE:510300")
    assert calls == [("history", "SSE:510300")]
    assert first["data"][0]["quote_kind"] == "last_daily"
    assert first["data"][0]["adjust"] == "none"
    assert first["data"][0]["price"] == 4.02
    assert "premium" not in json.dumps(first)
    clock[0] = 22000
    assert service.peek("SSE:510300")["state"] == "stale" and len(calls) == 1
    assert service.peek("SSE:510300")["fetched_at"] == first["data"][0]["fetched_at"]
    with pytest.raises(ValueError):
        service.etf("SSE:000001")


def test_etf_blocks_current_day_before_1630():
    from app.cross_assets import completed_etf_rows

    rows = [{"date": "2026-11-05", "close": 4}, {"date": "2026-11-06", "close": 5}]
    assert completed_etf_rows(rows, NOW) == rows[:1]
    assert completed_etf_rows(rows, NOW.replace(hour=16, minute=30)) == rows


def test_etf_shared_eastmoney_cooldown_prevents_io_and_receives_limits():
    from app.provider import PUSH2_SOURCE

    class Market:
        cooling = {}

        def upstream_cooldowns(self):
            return self.cooling

        def _merge_upstream_cooldowns(self, value):
            self.cooling.update(value)

    market = Market()
    market.cooling = {PUSH2_SOURCE: 9999999999}
    calls = []

    def run(*args):
        calls.append(args)
        raise CrossRateLimit("limit")

    service = CrossAssetService(run, demo=False, market_service=market)
    assert service.etf("SSE:518880")["state"] == "unavailable" and not calls
    market.cooling = {}
    assert service.etf("SSE:518880")["state"] == "unavailable" and len(calls) == 1
    assert PUSH2_SOURCE in market.cooling
    service.etf("SSE:511010")
    assert len(calls) == 1


def test_etf_worker_calls_single_history_not_full_market(monkeypatch, capsys):
    from types import SimpleNamespace
    import pandas as pd
    from app.cross_assets_worker import main

    calls = []

    def history(**kwargs):
        calls.append(kwargs)
        return pd.DataFrame([{"日期": "2026-08-03", "收盘": 4}])

    monkeypatch.setitem(
        sys.modules, "akshare", SimpleNamespace(fund_etf_hist_em=history)
    )
    monkeypatch.setattr(sys, "argv", ["worker", "history", "SSE:510300"])
    main()
    assert (
        len(calls) == 1 and calls[0]["symbol"] == "510300" and calls[0]["adjust"] == ""
    )
    assert '"ok": true' in capsys.readouterr().out


def test_worker_recognizes_structured_http_429_without_exposing_errors(monkeypatch,capsys):
    from types import SimpleNamespace
    from app.cross_assets_worker import main
    class Limited(Exception):
        response=SimpleNamespace(status_code=429)
    def fail(**_): raise Limited("private request credentials must not escape")
    monkeypatch.setitem(sys.modules,"akshare",SimpleNamespace(fund_etf_hist_em=fail))
    monkeypatch.setattr(sys,"argv",["worker","history","SSE:510300"])
    main()
    output=capsys.readouterr().out
    assert '"rate_limited": true' in output and "private request" not in output
