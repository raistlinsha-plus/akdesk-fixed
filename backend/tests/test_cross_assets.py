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

from app.cross_assets import CrossAssetService, CrossRateLimit, SHANGHAI, asset_spec, normalize_history, normalize_quote, number, observation, reference_payload
from app.database import Database
from app.models import ResearchProjectCreate, WorkflowCaptureCreate, ResearchEvidenceCreate
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
    data = normalize_history([{"date":"2026-11-05","close":100}, {"date":"2026-11-05","close":101},
        {"date":"2026-11-04","close":90}, {"date":"2026-11-07","close":99}, {"date":"2026-11-06","close":"NaN"}], NOW)
    assert data == [{"date":"2026-11-04","close":90.0}]


def test_quote_does_not_trust_provider_change_or_imply_real_time():
    result = normalize_quote(asset_spec("SSE:000001"), {"最新价":110,"昨收":100,"涨跌幅":99}, NOW)
    assert result["change_pct"] == 10
    assert result["observation_time"] is None and result["delay_seconds"] is None
    assert result["quality"] == "limited"


def test_memory_cache_singleflight_cooldown_and_no_force_bypass():
    clock=[0.0]
    calls=[]
    def run(mode,key):
        calls.append((mode,key))
        if len(calls)>1:
            raise CrossRateLimit("private upstream details must not escape")
        return [{"symbol":"sh000001","price":3100,"previous_close":3000}]
    service=CrossAssetService(run,demo=False,clock=lambda:clock[0])
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:service.quotes("index"),range(4)))
    assert len(calls)==1 and results[0]["data"][0]["price"]==3100
    results[0]["data"][0]["price"]=999
    assert service.peek("SSE:000001")["price"]==3100
    clock[0]=301
    result=service.quotes("index")
    assert result["state"]=="stale" and len(calls)==2
    assert "private upstream" not in json.dumps(result)
    clock[0]=302
    assert service.quotes("index")["state"]=="stale" and len(calls)==2
    assert service.peek("SSE:000001")["state"]=="stale"


def test_catalog_and_peek_do_not_fetch_and_invalid_ids_do_not_spawn():
    service=CrossAssetService(lambda *_:pytest.fail("unexpected IO"),demo=False)
    assert len(service.catalog()["assets"])==5
    assert service.peek("SGE:Au99.99") is None
    with pytest.raises(ValueError):
        service.history("https://untrusted.example/key")
    with pytest.raises(ValueError):
        service.quotes("stock")


def test_demo_never_uses_real_runner_and_is_explicit():
    service=CrossAssetService(lambda *_:pytest.fail("unexpected IO"),demo=True)
    quote=service.quotes("gold")["data"][0]
    assert quote["demo"] and quote["observation_time"]=="2026-08-03"
    history=service.history("SGE:Au99.99")
    assert history["demo"] and history["data"][-1]["date"]=="2026-08-03"


def test_reference_is_whitelisted_and_capture_atomic_idempotent(tmp_path):
    database=Database(tmp_path/"test.db")
    project=database.add_research_project(ResearchProjectCreate(title="合成项目"))
    body={"kind":"asset_reference","asset_id":"SGE:Au99.99","request_id":str(uuid4()),"confirmed":True,"note":"自己的文字"}
    request=WorkflowCaptureCreate.model_validate(body)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:workflow_capture(database,None,project.id,request),range(4)))
    assert len({item["entry_id"] for item in results})==1
    assert sum(not item["deduplicated"] for item in results)==1
    saved=database.get_research_project(project.id)
    assert len(saved.evidence)==1 and len(saved.entries)==1
    assert saved.evidence[0].payload==reference_payload("SGE:Au99.99")
    assert saved.evidence[0].observation_end is None
    assert database.project_summary(project.id)["supporting_evidence"][0]["ai_processing_allowed"] is False
    with pytest.raises(WorkflowConflict):
        workflow_capture(database,None,project.id,WorkflowCaptureCreate.model_validate({**body,"note":"changed"}))
    for bad in ({"price":700},{"report_date":"2026-11-06"},{"expected_fetched_at":"2026-11-06"},{"asset_id":"UNKNOWN"}):
        with pytest.raises(ValidationError):
            WorkflowCaptureCreate.model_validate({**body,**bad})


def test_reference_import_boundary_and_ai_filter():
    from app.ai_assistant import ai_record_allowed
    item=ResearchEvidenceCreate(evidence_type="snapshot",title="自己的标题",payload={**reference_payload("SGE:Au99.99"),"price":999,"date":"2026-11-06","nested":{"close":888}},observation_end="2026-11-06")
    assert "price" not in item.payload and "nested" not in item.payload
    assert item.observation_end is None
    assert not ai_record_allowed(item)
    assert not ai_record_allowed(item.model_dump())


def test_api_no_store_unsupported_inputs_watchlist_and_no_numeric_disk(tmp_path,monkeypatch):
    monkeypatch.setenv("AKDESK_DATA_DIR",str(tmp_path))
    monkeypatch.setenv("AKDESK_DEMO","1")
    sys.modules.pop("app.main",None)
    main=importlib.import_module("app.main")
    with TestClient(main.app) as client:
        for path in ("catalog","quotes?kind=index","quotes?kind=gold","history?asset_id=SGE%3AAu99.99"):
            response=client.get("/api/v1/cross-assets/"+path)
            assert response.status_code==200 and response.headers["cache-control"]=="no-store"
        assert client.get("/api/v1/cross-assets/history?asset_id=unknown").status_code==422
        assert client.get("/api/v1/cross-assets/quotes?kind=stock").status_code==422
        assert client.post("/api/v1/watchlists",json={"object_type":"gold","object_id":"SGE:Au99.99","name":"untrusted name"}).json()["name"]=="黄金 Au99.99"
        assert client.post("/api/v1/watchlists",json={"object_type":"index","object_id":"SGE:Au99.99","name":"bad"}).status_code==422
        enriched=client.get("/api/v1/watchlists/enriched").json()[0]
        assert enriched["page"]=="cross-assets" and enriched["source_meta"]["demo"] is True
        with main.database._connect() as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0]==1600
            assert not connection.execute("SELECT 1 FROM research_evidence").fetchall()
