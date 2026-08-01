from __future__ import annotations

import os
import json
import sqlite3
import re
import tempfile
import threading
import webbrowser
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .alerts import AlertEngine
from .ai_assistant import (
    AiAssistantService,
    AiBusyError,
    AiNotConfiguredError,
    AiProviderError,
    help_context,
    market_context,
    research_context,
)
from .ai_runtime import AiRuntimeManager, AiUsageLimitError
from .ai_insights import (
    AiInsightDisabledError,
    AiInsightQueueFullError,
    AiInsightService,
    context_fingerprint,
    credit_context,
    topic_context,
)
from .backup import ResearchBackupScheduler
from .calculator import calculate_bond
from .connectors import connector_catalog
from .credit import credit_candidates, credit_coverage, credit_workspace
from .credit_import import (
    credit_import_template,
    credit_history_csv,
    credit_observations_csv,
    parse_credit_file,
)
from .database import Database
from .gdelt import GdeltProviderError, GdeltRateLimitError, GdeltService
from .macro import FredNotConfiguredError, MacroProviderError, MacroService
from .models import (
    AlertCreate,
    AlertUpdate,
    AiAssistantRequest,
    AiHubMixSettingsUpdate,
    AiInsightGenerateRequest,
    AiRuntimeSettingsUpdate,
    BondCalculatorRequest,
    Dataset,
    CreditObservationCreate,
    CreditObservationUpdate,
    CreditPortfolioCreate,
    CreditPortfolioUpdate,
    CreditSignalConfirmationCreate,
    EvidenceBasketCommit,
    EvidenceBasketCreate,
    EvidenceBasketDelete,
    FredSettingsUpdate,
    IssuerEventTopicCreate,
    MarketSnapshotCreate,
    ReleaseReviewCreate,
    ReleaseReviewUpdate,
    ResearchEntryCreate,
    ResearchEntryUpdate,
    ResearchActionAcceptRequest,
    ResearchEvidenceCreate,
    ResearchProjectCreate,
    ResearchProjectTemplateCreate,
    ResearchProjectUpdate,
    ResearchSignalSettings,
    SovereignSnapshotCreate,
    ResearchTopicCreate,
    ResearchTopicStatus,
    ResearchTopicTemplateCreate,
    ResearchTopicUpdate,
    WatchlistCreate,
    WatchlistUpdate,
)
from .paths import default_data_dir
from .provider import DataService
from .release_review import evaluate_release_review
from .research import build_daily_report, build_market_brief
from .research_actions import action_draft_summary, build_research_action_drafts
from .research_workspace import (
    RESEARCH_TEMPLATES,
    create_project_from_template,
    project_markdown,
    weekly_report,
    weekly_report_markdown,
)
from .runtime import runtime_diagnostics
from .settings import AiHubMixSecretStore, FredSecretStore
from .topics import (
    RESEARCH_TOPIC_TEMPLATES,
    create_or_get_issuer_event_topic,
    create_topic_from_template,
    topic_markdown,
)
from .watchlist import enrich_watchlist
from .world_bank import WorldBankProviderError, WorldBankService

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = default_data_dir(PROJECT_ROOT)
FRONTEND_DIST = PROJECT_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_app: FastAPI):
    service.prewarm()
    service.start_scheduler()
    macro_service.start_scheduler()
    backup_scheduler.start()
    await ai_insight_service.start()
    try:
        yield
    finally:
        await ai_insight_service.stop()
        backup_scheduler.stop()
        macro_service.stop_scheduler()
        service.stop_scheduler()

app = FastAPI(
    title="AKDesk Fixed",
    version=__version__,
    description="个人本地固收研究终端 API",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:8765",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

database = Database(DATA_DIR / "akdesk-fixed.db")
backup_scheduler = ResearchBackupScheduler.from_environment(
    database, DATA_DIR / "backups"
)
market_history_calibration = database.calibrate_market_history()
alert_engine = AlertEngine(database)
fred_secret_store = FredSecretStore()
macro_service = MacroService(database, fred_secret_store)
aihubmix_secret_store = AiHubMixSecretStore()
ai_runtime = AiRuntimeManager(database)
ai_assistant_service = AiAssistantService(
    aihubmix_secret_store,
    budget_check=ai_runtime.ensure_available,
    usage_recorder=ai_runtime.record_usage,
)
ai_insight_service = AiInsightService(database, ai_assistant_service, ai_runtime)
world_bank_service = WorldBankService(database)
gdelt_service = GdeltService(database)


def consume_dataset(adapter: str, dataset: Dataset) -> None:
    database.upsert_instruments(adapter, dataset.data, demo=dataset.meta.demo)
    database.record_market_history(adapter, dataset)
    alert_engine.evaluate(adapter, dataset)


service = DataService(
    cache_path=DATA_DIR / "market-cache.db",
    on_dataset=consume_dataset,
)


def research_signal_settings() -> ResearchSignalSettings:
    payload = database.get_setting(
        "research_signal_settings", ResearchSignalSettings().model_dump()
    )
    try:
        return ResearchSignalSettings.model_validate(payload)
    except ValueError:
        return ResearchSignalSettings()


def market_dataset(adapter: str, loader, refresh: bool):
    """Return cached data immediately while a user refresh runs in the queue."""
    if refresh and service.cache.get(adapter, allow_stale=True) is not None:
        service.request_refresh(adapter, priority=0)
        return loader(False)
    return loader(refresh)


@app.get("/api/v1/info")
def info() -> dict:
    return {
        "name": "AKDesk Fixed",
        "version": __version__,
        "demo_only": service.demo_only,
        "data_dir": str(DATA_DIR),
        "market_history_calibration": market_history_calibration,
        "runtime": runtime_diagnostics(),
    }


@app.get("/api/v1/health")
def basic_health() -> dict:
    return {"status": "ok", "version": __version__}


@app.get("/api/v1/rates")
async def money_rates(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "money_rates", service.money_rates, refresh
    )


@app.get("/api/v1/curves")
async def yield_curves(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "yield_curves", service.yield_curves, refresh
    )


@app.get("/api/v1/bonds/spot")
async def spot_bonds(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "spot_bonds", service.spot_bonds, refresh
    )


@app.get("/api/v1/futures")
async def treasury_futures(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "treasury_futures", service.treasury_futures, refresh
    )


@app.get("/api/v1/fx/pairs")
async def fx_pairs(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "fx_pairs", service.fx_pairs, refresh
    )


@app.get("/api/v1/fx/rmb-reference")
async def fx_rmb_reference(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset,
        "fx_rmb_reference",
        service.fx_rmb_reference,
        refresh,
    )


@app.get("/api/v1/convertibles")
async def convertibles(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "convertibles", service.convertibles, refresh
    )


@app.get("/api/v1/events")
async def events(refresh: bool = Query(default=False)):
    return await run_in_threadpool(
        market_dataset, "issuance_events", service.issuance_events, refresh
    )


@app.get("/api/v1/sources/health")
def sources_health():
    return [
        *service.health_items(),
        macro_service.health_item(),
        world_bank_service.health_item(),
        gdelt_service.health_item(),
    ]


@app.get("/api/v1/connectors")
def external_connectors():
    return connector_catalog(
        market_health=service.health_items(),
        fred_health=macro_service.health_item(),
        fred_status=macro_service.integration_status(),
        world_bank_health=world_bank_service.health_item(),
        world_bank_stats=database.world_bank_stats(),
        gdelt_health=gdelt_service.health_item(),
        gdelt_stats=database.gdelt_stats(),
    )


@app.get("/api/v1/sources/activity")
def sources_activity() -> dict:
    return service.source_activity()


@app.post("/api/v1/sources/{adapter}/retry")
async def retry_source(adapter: str):
    if adapter == "fred_macro":
        try:
            return await run_in_threadpool(macro_service.test_connection)
        except FredNotConfiguredError as exc:
            raise HTTPException(status_code=424, detail=str(exc)) from exc
        except MacroProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if adapter == "world_bank":
        try:
            return await run_in_threadpool(world_bank_service.test_connection)
        except WorldBankProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    if adapter == "gdelt_events":
        try:
            return await run_in_threadpool(gdelt_service.test_connection)
        except GdeltRateLimitError as exc:
            raise HTTPException(status_code=429, detail=str(exc)) from exc
        except GdeltProviderError as exc:
            raise HTTPException(status_code=502, detail=str(exc)) from exc
    try:
        return await run_in_threadpool(service.refresh_adapter, adapter)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="未知数据适配器") from exc


@app.get("/api/v1/cache/stats")
def cache_stats() -> dict:
    return {
        **service.cache_stats(),
        "history": database.history_stats(),
        "macro": database.macro_stats(),
        "world_bank": database.world_bank_stats(),
        "gdelt": database.gdelt_stats(),
    }


@app.get("/api/v1/history")
def market_history(
    adapter: str = Query(min_length=1, max_length=40),
    metric: str = Query(min_length=1, max_length=40),
    series: str = Query(default="", max_length=500),
    days: int = Query(default=90, ge=1, le=400),
):
    allowed_adapters = {
        "money_rates",
        "money_fr",
        "money_fdr",
        "money_lpr",
        "yield_curves",
        "spot_bonds",
        "treasury_futures",
        "fx_rmb_reference",
        "convertibles",
    }
    allowed_metrics = {
        "value",
        "yield",
        "spread_bp",
        "change_bp",
        "price",
        "change_pct",
        "volume",
        "open_interest",
        "premium_pct",
        "double_low",
        "ytm_pct",
        "mid",
    }
    if adapter not in allowed_adapters or metric not in allowed_metrics:
        raise HTTPException(status_code=422, detail="不支持的历史序列")
    series_keys = [item for item in series.split(",") if item.strip()]
    return database.market_history(
        adapter,
        metric,
        series_keys=series_keys,
        days=days,
    )


@app.get("/api/v1/research/daily-report")
def daily_report(
    report_date: str | None = Query(default=None, alias="date", max_length=10),
):
    if report_date:
        try:
            date.fromisoformat(report_date)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD") from exc
        if report_date != date.today().isoformat():
            archived = database.get_daily_report(report_date)
            if archived is None:
                raise HTTPException(status_code=404, detail="该日期尚无复盘归档")
            return archived
    if service.demo_only:
        for adapter, loader in (
            ("money_rates", service.money_rates),
            ("yield_curves", service.yield_curves),
            ("spot_bonds", service.spot_bonds),
            ("treasury_futures", service.treasury_futures),
            ("issuance_events", service.issuance_events),
        ):
            if service.cache.get(adapter, allow_stale=True) is None:
                loader()
    report = build_daily_report(service, database)
    database.save_daily_report(report)
    return report


@app.get("/api/v1/research/daily-reports")
def daily_report_archive(limit: int = Query(default=120, ge=1, le=400)):
    return database.list_daily_reports(limit)


@app.get("/api/v1/research/market-brief")
def market_research_brief():
    if service.demo_only:
        for adapter, loader in (
            ("money_rates", service.money_rates),
            ("yield_curves", service.yield_curves),
            ("spot_bonds", service.spot_bonds),
            ("treasury_futures", service.treasury_futures),
        ):
            if service.cache.get(adapter, allow_stale=True) is None:
                loader()
    return build_market_brief(service, research_signal_settings())


@app.post("/api/v1/cache/clear")
def clear_cache() -> dict:
    service.clear_cache()
    macro_service.clear_cache()
    world_bank_service.clear_cache()
    gdelt_service.clear_cache()
    return {"ok": True}


@app.get("/api/v1/search")
def search(
    q: str = Query(min_length=1, max_length=80),
    limit: int = Query(default=20, ge=1, le=50),
):
    market_results = database.search_instruments(q, limit)
    topic_results = database.search_research_topics(q, limit)
    macro_results = [
        {
            "object_type": "macro",
            "object_id": item["series_id"],
            "name": item["title_zh"],
            "subtitle": f"FRED · {item['topic']}",
            "page": "macro",
            "updated_at": datetime.now(),
        }
        for item in macro_service.catalog(q)
    ]
    term = q.strip().lower()
    sovereign_catalog = world_bank_service.catalog()
    sovereign_results = [
        {
            "object_type": "macro",
            "object_id": item["indicator_id"],
            "name": item["title_zh"],
            "subtitle": f"World Bank · {item['topic']}",
            "page": "sovereign",
            "updated_at": datetime.now(),
        }
        for item in sovereign_catalog["indicators"]
        if term
        in " ".join(
            [
                str(item.get("indicator_id") or ""),
                str(item.get("title_zh") or ""),
                str(item.get("name") or ""),
                str(item.get("topic") or ""),
            ]
        ).lower()
    ]
    return [
        *market_results,
        *topic_results,
        *macro_results,
        *sovereign_results,
    ][:limit]


@app.get("/api/v1/watchlists")
def list_watchlist():
    return database.list_watchlist()


@app.get("/api/v1/watchlists/enriched")
def list_enriched_watchlist():
    return enrich_watchlist(service, database.list_watchlist())


@app.post("/api/v1/watchlists")
def add_watchlist(item: WatchlistCreate):
    return database.add_watchlist(item)


@app.patch("/api/v1/watchlists/{item_id}")
def update_watchlist(item_id: int, update: WatchlistUpdate):
    item = database.update_watchlist(item_id, update)
    if item is None:
        raise HTTPException(status_code=404, detail="自选项目不存在")
    return item


@app.delete("/api/v1/watchlists/{item_id}")
def delete_watchlist(item_id: int) -> dict:
    database.delete_watchlist(item_id)
    return {"ok": True}


@app.get("/api/v1/research/projects")
def list_research_projects():
    return database.list_research_projects()


@app.post("/api/v1/research/projects")
def add_research_project(item: ResearchProjectCreate):
    return database.add_research_project(item)


@app.get("/api/v1/research/templates")
def research_templates():
    return RESEARCH_TEMPLATES


@app.get("/api/v1/research/topic-templates")
def research_topic_templates():
    return RESEARCH_TOPIC_TEMPLATES


@app.get("/api/v1/research/topics")
def list_research_topics(
    q: str = Query(default="", max_length=120),
    status: ResearchTopicStatus | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=500),
):
    return database.list_research_topics(query=q, status=status, limit=limit)


@app.post("/api/v1/research/topics")
def add_research_topic(item: ResearchTopicCreate):
    try:
        return database.add_research_topic(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/research/topics/from-template")
def add_research_topic_from_template(item: ResearchTopicTemplateCreate):
    try:
        return create_topic_from_template(database, item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/research/topics/from-issuer-events")
def add_research_topic_from_issuer_events(item: IssuerEventTopicCreate):
    try:
        return create_or_get_issuer_event_topic(database, item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/research/topics/{topic_id}")
def get_research_topic(topic_id: int):
    topic = database.get_research_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="专题研究不存在")
    return topic


@app.patch("/api/v1/research/topics/{topic_id}")
def update_research_topic(topic_id: int, item: ResearchTopicUpdate):
    try:
        topic = database.update_research_topic(topic_id, item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if topic is None:
        raise HTTPException(status_code=404, detail="专题研究不存在")
    return topic


@app.delete("/api/v1/research/topics/{topic_id}")
def delete_research_topic(topic_id: int) -> dict:
    if not database.delete_research_topic(topic_id):
        raise HTTPException(status_code=404, detail="专题研究不存在")
    return {"ok": True}


@app.get("/api/v1/research/topics/{topic_id}/timeline")
def research_topic_timeline(
    topic_id: int,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    before_time: str | None = Query(default=None, max_length=64),
    before_id: str | None = Query(default=None, max_length=200),
    paged: bool = Query(default=False),
):
    if bool(before_time) != bool(before_id):
        raise HTTPException(status_code=422, detail="时间线游标必须同时包含时间和记录 ID")
    try:
        page = database.topic_timeline_page(
            topic_id, limit, offset, before_time, before_id
        )
        return page if paged else page["items"]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="专题研究不存在") from exc


@app.get("/api/v1/research/topics/{topic_id}/workspace")
def research_topic_workspace(
    topic_id: int, timeline_limit: int = Query(default=100, ge=1, le=200)
):
    workspace = database.topic_workspace(topic_id, timeline_limit)
    if workspace is None:
        raise HTTPException(status_code=404, detail="专题研究不存在")
    return workspace


@app.get("/api/v1/research/topics/{topic_id}/export")
def export_research_topic(topic_id: int):
    topic = database.get_research_topic(topic_id)
    if topic is None:
        raise HTTPException(status_code=404, detail="专题研究不存在")
    return Response(
        topic_markdown(database, topic),
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="akdesk-topic-{topic_id}.md"'
        },
    )


@app.post("/api/v1/research/projects/from-template")
def add_project_from_template(item: ResearchProjectTemplateCreate):
    return create_project_from_template(database, item)


@app.get("/api/v1/research/signal-settings")
def get_research_signal_settings():
    return research_signal_settings()


@app.patch("/api/v1/research/signal-settings")
def update_research_signal_settings(item: ResearchSignalSettings):
    database.set_setting("research_signal_settings", item.model_dump())
    return item


@app.get("/api/v1/research/projects/{project_id}")
def get_research_project(project_id: int):
    project = database.get_research_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return project


@app.get("/api/v1/research/projects/{project_id}/summary")
def get_research_project_summary(project_id: int):
    summary = database.project_summary(project_id)
    if summary is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return summary


@app.patch("/api/v1/research/projects/{project_id}")
def update_research_project(project_id: int, update: ResearchProjectUpdate):
    project = database.update_research_project(project_id, update)
    if project is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return project


@app.delete("/api/v1/research/projects/{project_id}")
def delete_research_project(project_id: int) -> dict:
    if not database.delete_research_project(project_id):
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return {"ok": True}


@app.post("/api/v1/research/projects/{project_id}/entries")
def add_research_entry(project_id: int, item: ResearchEntryCreate):
    saved = database.add_research_entry(project_id, item)
    if saved is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return saved


@app.patch("/api/v1/research/entries/{entry_id}")
def update_research_entry(entry_id: int, item: ResearchEntryUpdate):
    saved = database.update_research_entry(entry_id, item)
    if saved is None:
        raise HTTPException(status_code=404, detail="研究记录不存在")
    return saved


@app.delete("/api/v1/research/entries/{entry_id}")
def delete_research_entry(entry_id: int) -> dict:
    if not database.delete_research_entry(entry_id):
        raise HTTPException(status_code=404, detail="研究记录不存在")
    return {"ok": True}


@app.get("/api/v1/research/projects/{project_id}/action-drafts")
def list_research_action_drafts(project_id: int):
    if database.get_research_project(project_id) is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return action_draft_summary(database.list_research_action_drafts(project_id))


@app.post("/api/v1/research/projects/{project_id}/action-drafts/generate")
def generate_research_action_drafts(project_id: int):
    try:
        proposals = build_research_action_drafts(database, project_id)
        drafts = database.replace_research_action_drafts(project_id, proposals)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="研究项目不存在") from exc
    return action_draft_summary(drafts)


@app.post("/api/v1/research/projects/{project_id}/action-drafts/accept")
def accept_research_action_drafts(
    project_id: int, item: ResearchActionAcceptRequest
):
    try:
        drafts = database.accept_research_action_drafts(project_id, item.draft_ids)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return action_draft_summary(drafts)


@app.post("/api/v1/research/projects/{project_id}/action-drafts/{draft_id}/undo")
def undo_research_action_draft(project_id: int, draft_id: int):
    try:
        saved = database.undo_research_action_draft(project_id, draft_id)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="研究行动草稿不存在")
    return action_draft_summary(database.list_research_action_drafts(project_id))


@app.get("/api/v1/research/projects/{project_id}/export")
def export_research_project(
    project_id: int,
    format: str = Query(default="json", pattern="^(json|markdown)$"),
):
    project = database.get_research_project(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    if format == "markdown":
        return Response(
            project_markdown(project),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="akdesk-project-{project_id}.md"'
            },
        )
    bundle = database.project_bundle(project_id)
    return Response(
        json.dumps(bundle, ensure_ascii=False, indent=2),
        media_type="application/json; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="akdesk-project-{project_id}.json"'
        },
    )


@app.post("/api/v1/research/import")
def import_research_project(bundle: dict[str, object]):
    try:
        return database.import_project_bundle(bundle)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get("/api/v1/research/backup")
def download_research_backup():
    backup_dir = DATA_DIR / "backups"
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"akdesk-research-{stamp}.db"
    database.backup_to(target)
    return FileResponse(
        target,
        media_type="application/vnd.sqlite3",
        filename=target.name,
    )


@app.get("/api/v1/research/backups")
def research_backup_status():
    return backup_scheduler.status()


@app.post("/api/v1/research/backup/auto")
def create_auto_research_backup():
    try:
        result = backup_scheduler.run_once(force=True)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return {**result, "status": backup_scheduler.status()}


@app.post("/api/v1/research/backup/restore")
async def restore_research_backup(request: Request):
    content = await request.body()
    if not content or len(content) > 100 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="备份文件为空或超过 100 MB")
    backup_dir = DATA_DIR / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    current_backup = backup_dir / (
        "before-restore-" + datetime.now().strftime("%Y%m%d-%H%M%S") + ".db"
    )
    database.backup_to(current_backup)
    with tempfile.NamedTemporaryFile(
        suffix=".db", dir=backup_dir, delete=False
    ) as handle:
        handle.write(content)
        candidate = Path(handle.name)
    try:
        database.restore_from(candidate)
    except (ValueError, OSError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        candidate.unlink(missing_ok=True)
    return {"ok": True, "safety_backup": current_backup.name}


@app.get("/api/v1/research/weekly-report")
def get_weekly_report(
    end: str | None = Query(default=None, max_length=10),
    format: str = Query(default="json", pattern="^(json|markdown)$"),
):
    try:
        end_date = date.fromisoformat(end) if end else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式应为 YYYY-MM-DD") from exc
    report = weekly_report(database, end_date)
    if format == "markdown":
        return Response(
            weekly_report_markdown(report),
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="akdesk-weekly.md"'},
        )
    return report


def build_market_snapshot_evidence(item: MarketSnapshotCreate) -> ResearchEvidenceCreate:
    brief = build_market_brief(service, research_signal_settings())
    eligible = {
        signal["id"]: signal
        for signal in brief["signals"]
        if signal.get("actionable")
    }
    requested = list(dict.fromkeys(item.signal_ids)) if item.signal_ids else list(eligible)
    unavailable = [signal_id for signal_id in requested if signal_id not in eligible]
    if unavailable:
        raise HTTPException(
            status_code=422,
            detail="所选信号已过期、来自演示数据或可信度不足，请刷新后重试",
        )
    selected = [eligible[signal_id] for signal_id in requested]
    if not selected:
        raise HTTPException(
            status_code=409,
            detail="当前没有可保存的可信市场信号",
        )
    adapters = {signal["adapter"] for signal in selected}
    sources = [
        source for source in brief["sources"] if source["adapter"] in adapters
    ]
    observation_times = sorted(
        {
            str(source["observation_time"])
            for source in sources
            if source.get("observation_time")
        }
    )
    source_names = list(
        dict.fromkeys(str(source["source"]) for source in sources if source.get("source"))
    )
    generated_at = str(brief["generated_at"])
    return ResearchEvidenceCreate(
        evidence_type="snapshot",
        title=f"市场快照 · {generated_at[0:16].replace('T', ' ')}",
        payload={
            "schema_version": "1.0",
            "snapshot_type": "market_brief",
            "generated_at": generated_at,
            "market_status": brief["market_status"],
            "headline": brief["headline"],
            "signals": selected,
            "sources": sources,
            "note": item.note.strip(),
            "notice": "该证据保存的是当时可用的中国固收市场快照；演示、异常隔离和不可用数据不会写入。",
        },
        source_summary=(
            " / ".join(source_names) + f" · {len(selected)} 项可信市场信号"
        )[:500],
        observation_start=observation_times[0] if observation_times else None,
        observation_end=observation_times[-1] if observation_times else None,
    )


def build_sovereign_snapshot_evidence(
    item: SovereignSnapshotCreate,
) -> ResearchEvidenceCreate:
    try:
        comparison = world_bank_service.compare(
            item.country_codes,
            item.indicator_id,
            start_year=item.start_year,
            end_year=item.end_year,
            view=item.view,
            refresh=False,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WorldBankProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    if comparison.meta.stale or comparison.meta.trust_level not in {
        "trusted",
        "partial",
    }:
        raise HTTPException(
            status_code=409,
            detail="当前 World Bank 数据已过期或不可验证，请刷新后重试",
        )
    data = comparison.data
    indicator = data["indicator"]
    return ResearchEvidenceCreate(
        evidence_type="table",
        title=f"主权比较 · {indicator['title_zh']}",
        payload={
            "schema_version": "1.0",
            "snapshot_type": "world_bank_sovereign_comparison",
            "provider": "World Bank",
            "indicator": indicator,
            "countries": data["countries"],
            "years": data["years"],
            "series": data["series"],
            "view": data["view"],
            "summary_year": data["summary_year"],
            "latest_rows": data["latest_rows"],
            "coverage": data["coverage"],
            "source": data["source"],
            "source_url": data["source_url"],
            "license": data["license"],
            "license_url": data["license_url"],
            "attribution": data["attribution"],
            "captured_at": datetime.now().isoformat(),
            "source_fetched_at": comparison.meta.fetched_at.isoformat(),
            "observation_time": comparison.meta.observation_time,
            "note": item.note.strip(),
            "notice": data["comparison_notice"],
        },
        source_summary=(
            f"World Bank · {indicator['indicator_id']} · "
            + " / ".join(
                str(country.get("name_zh") or country.get("country_code"))
                for country in data["countries"]
            )
        )[:500],
        observation_start=str(item.start_year),
        observation_end=str(item.end_year),
    )


@app.get("/api/v1/research/evidence-basket")
def list_research_evidence_basket(
    topic_id: int | None = Query(default=None, ge=1),
    include_unassigned: bool = Query(default=True),
    source: str | None = Query(default=None, max_length=120),
    origin_page: str | None = Query(default=None, max_length=80),
    date_from: date | None = Query(default=None),
    date_to: date | None = Query(default=None),
):
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="证据篮起始日期不得晚于结束日期")
    return database.list_evidence_basket(
        topic_id=topic_id,
        include_unassigned=include_unassigned,
        source=source,
        origin_page=origin_page,
        date_from=date_from.isoformat() if date_from else None,
        date_to=date_to.isoformat() if date_to else None,
    )


@app.post("/api/v1/research/evidence-basket")
def add_research_evidence_basket(item: EvidenceBasketCreate):
    try:
        return database.add_evidence_basket(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/research/evidence-basket/market-snapshot")
def add_market_snapshot_to_basket(item: MarketSnapshotCreate):
    evidence = build_market_snapshot_evidence(item)
    return database.add_evidence_basket(
        EvidenceBasketCreate(
            **evidence.model_dump(),
            origin_page="research-desk",
        )
    )


@app.post("/api/v1/research/evidence-basket/sovereign-snapshot")
def add_sovereign_snapshot_to_basket(item: SovereignSnapshotCreate):
    evidence = build_sovereign_snapshot_evidence(item)
    return database.add_evidence_basket(
        EvidenceBasketCreate(
            **evidence.model_dump(),
            origin_page="sovereign",
        )
    )


@app.post("/api/v1/research/evidence-basket/commit")
def commit_research_evidence_basket(item: EvidenceBasketCommit):
    try:
        return database.commit_evidence_basket(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/v1/research/evidence-basket/batch-delete")
def delete_research_evidence_basket_batch(item: EvidenceBasketDelete) -> dict:
    deleted = database.delete_evidence_basket_items(item.item_ids)
    if deleted != len(item.item_ids):
        raise HTTPException(
            status_code=409,
            detail=f"仅删除 {deleted}/{len(item.item_ids)} 项，证据篮可能已被其他操作更新",
        )
    return {"ok": True, "deleted": deleted}


@app.delete("/api/v1/research/evidence-basket/{item_id}")
def delete_research_evidence_basket(item_id: int) -> dict:
    if not database.delete_evidence_basket(item_id):
        raise HTTPException(status_code=404, detail="证据篮项目不存在")
    return {"ok": True}


@app.get("/api/v1/gdelt/events")
async def gdelt_events(
    query: str = Query(min_length=2, max_length=200),
    days: int = Query(default=7, ge=1, le=90),
    limit: int = Query(default=20, ge=5, le=50),
    sort: str = Query(default="datedesc", pattern=r"^(datedesc|hybridrel)$"),
    refresh: bool = Query(default=False),
):
    try:
        return await run_in_threadpool(
            gdelt_service.search,
            query,
            days=days,
            limit=limit,
            sort=sort,
            refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except GdeltRateLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except GdeltProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/research/projects/{project_id}/evidence")
def add_research_evidence(project_id: int, item: ResearchEvidenceCreate):
    evidence = database.add_research_evidence(project_id, item)
    if evidence is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return evidence


@app.post("/api/v1/research/projects/{project_id}/market-snapshot")
def add_market_snapshot(project_id: int, item: MarketSnapshotCreate):
    if database.get_research_project(project_id) is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    evidence = build_market_snapshot_evidence(item)
    saved = database.add_research_evidence(project_id, evidence)
    if saved is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return saved


@app.post("/api/v1/research/projects/{project_id}/sovereign-snapshot")
def add_sovereign_snapshot(project_id: int, item: SovereignSnapshotCreate):
    if database.get_research_project(project_id) is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    evidence = build_sovereign_snapshot_evidence(item)
    saved = database.add_research_evidence(project_id, evidence)
    if saved is None:
        raise HTTPException(status_code=404, detail="研究项目不存在")
    return saved


@app.delete("/api/v1/research/evidence/{evidence_id}")
def delete_research_evidence(evidence_id: int) -> dict:
    if not database.delete_research_evidence(evidence_id):
        raise HTTPException(status_code=404, detail="研究证据不存在")
    return {"ok": True}


@app.get("/api/v1/research/overview")
def research_overview() -> dict:
    projects = database.list_research_projects()
    topics = database.list_research_topics()
    basket = database.list_evidence_basket()
    watchlist = database.list_watchlist()
    today = date.today().isoformat()
    return {
        "projects": {
            "total": len(projects),
            "active": sum(item.status not in {"archived"} for item in projects),
            "with_conclusion": sum(bool(item.conclusion.strip()) for item in projects),
            "evidence": sum(len(item.evidence) for item in projects),
            "due": sum(
                bool(item.next_review_date and item.next_review_date <= today)
                and item.status != "archived"
                for item in projects
            ),
            "recent": projects[:5],
        },
        "topics": {
            "total": len(topics),
            "active": sum(item.status != "archived" for item in topics),
            "review": sum(item.status == "review" for item in topics),
            "recent": topics[:5],
        },
        "evidence_basket": {
            "total": len(basket),
            "oldest": basket[-1].created_at.isoformat() if basket else None,
        },
        "watchlist": {
            "total": len(watchlist),
            "macro": sum(item.object_type == "macro" for item in watchlist),
            "securities": sum(item.object_type != "macro" for item in watchlist),
            "pinned": sum(item.pinned for item in watchlist),
        },
        "fred": macro_service.integration_status(),
        "macro_cache": database.macro_stats(),
        "world_bank": database.world_bank_stats(),
    }


@app.get("/api/v1/settings/integrations")
def integration_settings() -> dict:
    return {
        "fred": macro_service.integration_status(),
        "aihubmix": {
            **ai_assistant_service.status(),
            "runtime": ai_runtime.status(
                busy=ai_assistant_service.busy,
                queue_depth=ai_insight_service.queue_depth,
            ),
        },
    }


@app.get("/api/v1/ai/status")
def ai_assistant_status() -> dict:
    return {
        **ai_assistant_service.status(),
        "runtime": ai_runtime.status(
            busy=ai_assistant_service.busy,
            queue_depth=ai_insight_service.queue_depth,
        ),
    }


@app.get("/api/v1/ai/runtime")
def ai_runtime_status() -> dict:
    return ai_runtime.status(
        busy=ai_assistant_service.busy,
        queue_depth=ai_insight_service.queue_depth,
    )


@app.patch("/api/v1/ai/runtime")
def update_ai_runtime(item: AiRuntimeSettingsUpdate) -> dict:
    ai_runtime.update_settings(item.model_dump())
    return ai_runtime_status()


@app.post("/api/v1/settings/integrations/aihubmix")
async def save_aihubmix_settings(item: AiHubMixSettingsUpdate) -> dict:
    current = aihubmix_secret_store.status()
    if current.source == "environment":
        raise HTTPException(
            status_code=409,
            detail=(
                "AIHubMix Key 当前由环境变量提供，"
                "请先移除环境变量后再使用 Keychain"
            ),
        )
    previous_key = (
        aihubmix_secret_store.get() if current.source == "keychain" else None
    )
    try:
        aihubmix_secret_store.set(item.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    ai_assistant_service.credential_changed()
    try:
        await ai_assistant_service.test_connection()
    except (AiNotConfiguredError, AiProviderError, AiBusyError) as exc:
        try:
            if previous_key:
                aihubmix_secret_store.set(previous_key)
            else:
                aihubmix_secret_store.delete()
        finally:
            ai_assistant_service.credential_changed()
        raise HTTPException(
            status_code=502,
            detail=f"AIHubMix 连接验证失败，新 Key 未保存：{exc}",
        ) from exc
    return ai_assistant_status()


@app.delete("/api/v1/settings/integrations/aihubmix")
def delete_aihubmix_settings() -> dict:
    deleted = aihubmix_secret_store.delete()
    ai_assistant_service.credential_changed()
    return {**ai_assistant_status(), "deleted": deleted}


@app.post("/api/v1/settings/integrations/aihubmix/test")
async def test_aihubmix_settings() -> dict:
    try:
        await ai_assistant_service.test_connection()
        return ai_assistant_status()
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except AiBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AiProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/ai/assistant")
async def ask_ai_assistant(item: AiAssistantRequest) -> dict:
    if not item.confirm_external_processing:
        raise HTTPException(
            status_code=428,
            detail="发送前必须确认本次问题与预览上下文将提交给 AIHubMix",
        )
    if item.scenario == "help":
        context = help_context(item.current_page)
        context_summary = ["当前页面", "产品模块导航", "推荐研究闭环与能力边界"]
    elif item.scenario == "market":
        brief = build_market_brief(service, research_signal_settings())
        context = market_context(brief)
        context_summary = [
            "最多 8 条市场线索",
            "来源、观测时间、可信状态与质量分",
            "不发送完整行情表或历史数据库",
        ]
    else:
        projects = database.list_research_projects()
        project = (
            database.get_research_project(item.project_id)
            if item.project_id
            else None
        )
        if item.project_id and project is None:
            raise HTTPException(status_code=404, detail="研究项目不存在")
        context = research_context(project, projects)
        context_summary = (
            [
                "所选项目的问题、假设、当前结论与复盘日期",
                "最多 8 条证据标题与来源摘要",
                "最多 12 条研究记录标题与状态，不发送记录正文",
            ]
            if project
            else ["项目数量与状态", "最多 8 个最近项目标题", "不发送研究正文"]
        )
    try:
        return await ai_assistant_service.ask(
            scenario=item.scenario,
            question=item.question,
            context=context,
            context_summary=context_summary,
        )
    except AiNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except AiBusyError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AiUsageLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AiProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


def ai_insight_context(
    context_type: Literal["market", "project", "credit", "topic"],
    project_id: int | None,
    topic_id: int | None = None,
) -> tuple[str, dict, list[str]]:
    if context_type == "market":
        brief = build_market_brief(service, research_signal_settings())
        return (
            "today",
            market_context(brief),
            [
                "最多 8 条市场线索",
                "最多 12 个来源的时点、可信状态与质量分",
                "不发送完整行情表、历史数据库或新闻正文",
            ],
        )
    if context_type == "project":
        if project_id is None:
            raise HTTPException(status_code=422, detail="研究项目洞察需要 project_id")
        project = database.get_research_project(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="研究项目不存在")
        return (
            str(project_id),
            research_context(project, [project]),
            [
                "项目问题、假设、当前结论与复盘日期",
                "最多 8 条证据标题和来源摘要",
                "最多 12 条研究记录标题与状态，不发送记录正文",
            ],
        )
    if context_type == "topic":
        if topic_id is None:
            raise HTTPException(status_code=422, detail="专题综述需要 topic_id")
        workspace = database.topic_workspace(topic_id, timeline_limit=100)
        if workspace is None:
            raise HTTPException(status_code=404, detail="研究专题不存在")
        return (
            str(topic_id),
            topic_context(workspace),
            [
                "专题问题、研究对象、标签和组件类型",
                "最多 8 个项目的状态、证据标题、反证标题与任务标题",
                "最多 20 条时间线标题、来源与时点，不发送笔记正文或新闻正文",
            ],
        )
    workspace = credit_workspace(database)
    return (
        "workspace",
        credit_context(workspace),
        [
            "信用覆盖率、字段缺口与汇总数量",
            "最多 12 条规则信号和 12 个信用日程",
            "不发送来源备注正文、导入文件、历史明细或研究记录正文",
        ],
    )


@app.get("/api/v1/ai/insights/{context_type}")
def get_ai_insight(
    context_type: Literal["market", "project", "credit", "topic"],
    project_id: int | None = Query(default=None, ge=1),
    topic_id: int | None = Query(default=None, ge=1),
) -> dict:
    context_key, context, context_summary = ai_insight_context(
        context_type, project_id, topic_id
    )
    return ai_insight_service.status(
        context_type=context_type,
        context_key=context_key,
        fingerprint=context_fingerprint(context),
        context_summary=context_summary,
    )


@app.post("/api/v1/ai/insights/{context_type}")
def generate_ai_insight(
    context_type: Literal["market", "project", "credit", "topic"],
    item: AiInsightGenerateRequest,
) -> dict:
    if not item.confirm_external_processing:
        raise HTTPException(
            status_code=428,
            detail="生成页面洞察前必须确认裁剪上下文将提交给 AIHubMix",
        )
    policy = ai_runtime.settings()["page_insights"][context_type]
    if item.trigger_reason != "manual" and policy["trigger"] != item.trigger_reason:
        raise HTTPException(status_code=409, detail="页面洞察触发策略已经变化，请刷新")
    context_key, context, context_summary = ai_insight_context(
        context_type, item.project_id, item.topic_id
    )
    try:
        return ai_insight_service.enqueue(
            context_type=context_type,
            context_key=context_key,
            context=context,
            context_summary=context_summary,
            force=item.force or item.trigger_reason == "daily",
        )
    except AiInsightDisabledError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except AiUsageLimitError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except AiInsightQueueFullError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/api/v1/settings/integrations/fred")
async def save_fred_settings(item: FredSettingsUpdate) -> dict:
    current = fred_secret_store.status()
    if current.source == "environment":
        raise HTTPException(
            status_code=409,
            detail="FRED Key 当前由环境变量提供，请先移除环境变量后再使用 Keychain",
        )
    previous_key = fred_secret_store.get() if current.source == "keychain" else None
    try:
        fred_secret_store.set(item.api_key)
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    macro_service.credential_changed()
    try:
        await run_in_threadpool(macro_service.test_connection)
    except (FredNotConfiguredError, MacroProviderError) as exc:
        try:
            if previous_key:
                fred_secret_store.set(previous_key)
            else:
                fred_secret_store.delete()
        finally:
            macro_service.credential_changed()
        raise HTTPException(
            status_code=502,
            detail=f"FRED 连接验证失败，新 Key 未保存：{exc}",
        ) from exc
    return macro_service.integration_status()


@app.delete("/api/v1/settings/integrations/fred")
def delete_fred_settings() -> dict:
    deleted = fred_secret_store.delete()
    macro_service.credential_changed()
    return {**macro_service.integration_status(), "deleted": deleted}


@app.post("/api/v1/settings/integrations/fred/test")
async def test_fred_settings():
    try:
        return await run_in_threadpool(macro_service.test_connection)
    except FredNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except MacroProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.delete("/api/v1/ai/insights/{context_type}")
def clear_ai_insight(
    context_type: Literal["market", "project", "credit", "topic"],
    project_id: int | None = Query(default=None, ge=1),
    topic_id: int | None = Query(default=None, ge=1),
) -> dict:
    context_key, context, context_summary = ai_insight_context(
        context_type, project_id, topic_id
    )
    if ai_insight_service.is_active(context_type, context_key):
        raise HTTPException(status_code=409, detail="AI 洞察正在生成，完成后才能清除")
    database.delete_ai_insight(context_type, context_key)
    return ai_insight_service.status(
        context_type=context_type,
        context_key=context_key,
        fingerprint=context_fingerprint(context),
        context_summary=context_summary,
    )


@app.get("/api/v1/macro/catalog")
def macro_catalog(
    q: str = Query(default="", max_length=80),
    topic: str = Query(default="", max_length=80),
):
    return macro_service.catalog(q, topic)


@app.get("/api/v1/macro/series/{series_id}")
async def macro_series(
    series_id: str,
    years: int = Query(default=10, ge=1, le=50),
    refresh: bool = Query(default=False),
):
    try:
        return await run_in_threadpool(
            macro_service.series, series_id, years=years, refresh=refresh
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="该宏观序列不在精选目录中") from exc
    except FredNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except MacroProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/macro/chart")
async def macro_chart(
    series: str = Query(min_length=1, max_length=300),
    years: int = Query(default=10, ge=1, le=50),
    transform: str = Query(default="level", max_length=20),
    refresh: bool = Query(default=False),
):
    series_ids = [item.strip().upper() for item in series.split(",") if item.strip()]
    try:
        return await run_in_threadpool(
            macro_service.chart,
            series_ids,
            years=years,
            transform=transform,
            refresh=refresh,
        )
    except (ValueError, KeyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except FredNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except MacroProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/macro/releases")
async def macro_releases(refresh: bool = Query(default=False)):
    try:
        return await run_in_threadpool(macro_service.release_calendar, refresh)
    except FredNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except MacroProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/sovereign/catalog")
def sovereign_catalog():
    return world_bank_service.catalog()


@app.get("/api/v1/sovereign/compare")
async def sovereign_compare(
    countries: str = Query(min_length=1, max_length=80),
    indicator: str = Query(min_length=1, max_length=80),
    start_year: int = Query(ge=1960, le=2100),
    end_year: int = Query(ge=1960, le=2100),
    view: str = Query(default="level", pattern="^(level|change|rank|zscore)$"),
    refresh: bool = Query(default=False),
):
    country_codes = [item for item in countries.split(",") if item.strip()]
    try:
        return await run_in_threadpool(
            world_bank_service.compare,
            country_codes,
            indicator,
            start_year=start_year,
            end_year=end_year,
            view=view,
            refresh=refresh,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except WorldBankProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/v1/release-reviews")
def list_release_reviews():
    return database.list_release_reviews()


@app.post("/api/v1/release-reviews")
def add_release_review(item: ReleaseReviewCreate):
    try:
        return database.add_release_review(item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.patch("/api/v1/release-reviews/{review_id}")
def update_release_review(review_id: int, item: ReleaseReviewUpdate):
    try:
        saved = database.update_release_review(review_id, item)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="发布复盘不存在")
    return saved


@app.delete("/api/v1/release-reviews/{review_id}")
def delete_release_review(review_id: int) -> dict:
    if not database.delete_release_review(review_id):
        raise HTTPException(status_code=404, detail="发布复盘不存在")
    return {"ok": True}


@app.get("/api/v1/release-reviews/{review_id}/evaluate")
async def evaluate_saved_release_review(review_id: int):
    review = database.get_release_review(review_id)
    if review is None:
        raise HTTPException(status_code=404, detail="发布复盘不存在")
    try:
        return await run_in_threadpool(
            evaluate_release_review, database, macro_service, review
        )
    except FredNotConfiguredError as exc:
        raise HTTPException(status_code=424, detail=str(exc)) from exc
    except MacroProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/v1/release-reviews/{review_id}/mark-reviewed")
def mark_release_reviewed(review_id: int, payload: dict[str, str]):
    realtime_start = str(payload.get("realtime_start") or "").strip()
    if not realtime_start:
        raise HTTPException(status_code=422, detail="缺少 FRED vintage 引用")
    saved = database.update_release_review(
        review_id,
        ReleaseReviewUpdate(
            reviewed_realtime_start=realtime_start,
            reviewed_at=datetime.now(),
        ),
    )
    if saved is None:
        raise HTTPException(status_code=404, detail="发布复盘不存在")
    return saved


@app.get("/api/v1/credit/observations")
def list_credit_observations():
    return credit_coverage(database.list_credit_observations())


@app.get("/api/v1/credit/workspace")
def get_credit_workspace():
    return credit_workspace(database)


@app.get("/api/v1/credit/observations/{item_id}/history")
def get_credit_observation_history(item_id: int):
    if not any(item.id == item_id for item in database.list_credit_observations()):
        raise HTTPException(status_code=404, detail="信用观察不存在")
    return database.list_credit_history(item_id)


@app.get("/api/v1/credit/candidates")
def list_credit_candidates():
    return credit_candidates(service)


@app.post("/api/v1/credit/observations")
def add_credit_observation(item: CreditObservationCreate):
    return database.add_credit_observation(item)


@app.patch("/api/v1/credit/observations/{item_id}")
def update_credit_observation(item_id: int, item: CreditObservationUpdate):
    saved = database.update_credit_observation(item_id, item)
    if saved is None:
        raise HTTPException(status_code=404, detail="信用观察不存在")
    return saved


@app.delete("/api/v1/credit/observations/{item_id}")
def delete_credit_observation(item_id: int) -> dict:
    if not database.delete_credit_observation(item_id):
        raise HTTPException(status_code=404, detail="信用观察不存在")
    return {"ok": True}


@app.get("/api/v1/credit/import/template")
def download_credit_import_template():
    return Response(
        credit_import_template(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": 'attachment; filename="akdesk-credit-r2-template.csv"'
        },
    )


@app.get("/api/v1/credit/export")
def export_credit_observations(
    scope: str = Query(default="current", pattern="^(current|history)$"),
):
    observations = database.list_credit_observations()
    content = (
        credit_history_csv(observations, database.list_credit_history())
        if scope == "history"
        else credit_observations_csv(observations)
    )
    filename = (
        "akdesk-credit-history.csv"
        if scope == "history"
        else "akdesk-credit-observations.csv"
    )
    return Response(
        content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        },
    )


@app.post("/api/v1/credit/import")
async def import_credit_file(
    request: Request,
    filename: str = Query(min_length=1, max_length=240),
    commit: bool = Query(default=False),
    mapping: str | None = Query(default=None, max_length=8_000),
):
    content = await request.body()
    if not content or len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="导入文件为空或超过 10 MB")
    mapping_override = None
    if mapping:
        try:
            candidate = json.loads(mapping)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=422, detail="字段映射格式无效") from exc
        if not isinstance(candidate, dict):
            raise HTTPException(status_code=422, detail="字段映射必须是对象")
        mapping_override = {str(key): str(value) for key, value in candidate.items()}
    try:
        result = await run_in_threadpool(
            parse_credit_file, content, filename, mapping_override
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    items = result.pop("items")
    if commit:
        if result["errors"] or not items:
            raise HTTPException(
                status_code=422,
                detail="导入仍有字段映射或行校验错误，请修正后再确认",
            )
        saved = await run_in_threadpool(database.add_credit_observations, items)
        return {**result, **saved, "committed": True}
    return {**result, "committed": False}


@app.post("/api/v1/credit/portfolios")
def add_credit_portfolio(item: CreditPortfolioCreate):
    try:
        return database.add_credit_portfolio(item)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="组合名称重复或包含不存在的债券") from exc


@app.patch("/api/v1/credit/portfolios/{portfolio_id}")
def update_credit_portfolio(portfolio_id: int, item: CreditPortfolioUpdate):
    try:
        saved = database.update_credit_portfolio(portfolio_id, item)
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="组合名称重复或包含不存在的债券") from exc
    if saved is None:
        raise HTTPException(status_code=404, detail="信用组合不存在")
    return saved


@app.delete("/api/v1/credit/portfolios/{portfolio_id}")
def delete_credit_portfolio(portfolio_id: int):
    if not database.delete_credit_portfolio(portfolio_id):
        raise HTTPException(status_code=404, detail="信用组合不存在")
    return {"ok": True}


@app.post("/api/v1/credit/signals/{signal_id}/confirm")
def confirm_credit_signal(signal_id: str, item: CreditSignalConfirmationCreate):
    if not re.fullmatch(r"[0-9a-f]{16}", signal_id):
        raise HTTPException(status_code=422, detail="信号标识无效")
    current = {
        signal["id"]: signal for signal in credit_workspace(database)["signals"]
    }
    signal = current.get(signal_id)
    if signal is None:
        raise HTTPException(status_code=404, detail="信用信号不存在或已失效")
    project = None
    if item.project_id is not None:
        project = database.get_research_project(item.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="关联研究项目不存在")
    existing = database.list_credit_signal_confirmations().get(signal_id)
    confirmation = database.confirm_credit_signal(signal_id, item.note)
    research_entry = None
    if project is not None and existing is None:
        research_entry = database.add_research_entry(
            project.id,
            ResearchEntryCreate(
                entry_type="review",
                title=f"信用信号确认：{signal['title']}",
                content="\n".join(
                    part
                    for part in (
                        signal["detail"],
                        f"主体：{signal['issuer']}",
                        f"债券：{signal['bond_name']}（{signal['bond_code']}）",
                        f"观察日期：{signal.get('observation_date') or '待补'}",
                        f"来源：{signal.get('source_note') or '待补'}",
                        f"人工备注：{item.note.strip() or '已复核，无补充备注'}",
                    )
                    if part
                ),
                status="done",
            ),
        )
    return {
        **confirmation,
        "project_id": project.id if project else None,
        "research_entry_id": research_entry.id if research_entry else None,
    }


@app.get("/api/v1/alerts")
def list_alerts():
    return database.list_alerts()


@app.post("/api/v1/alerts")
def add_alert(item: AlertCreate):
    saved = database.add_alert(item)
    adapter_by_type = {
        "bond": "spot_bonds",
        "future": "treasury_futures",
        "convertible": "convertibles",
    }
    dataset = service.cache.get(adapter_by_type[item.object_type])
    if dataset is not None:
        alert_engine.evaluate(adapter_by_type[item.object_type], dataset)
    return saved


@app.post("/api/v1/alerts/preview")
def preview_alert(item: AlertCreate):
    adapter_by_type = {
        "bond": "spot_bonds",
        "future": "treasury_futures",
        "convertible": "convertibles",
    }
    adapter = adapter_by_type[item.object_type]
    dataset = service.cache.get(adapter)
    return alert_engine.preview(adapter, dataset, item)


@app.patch("/api/v1/alerts/{item_id}")
def update_alert(item_id: int, update: AlertUpdate):
    item = database.set_alert_enabled(item_id, update.enabled)
    if item is None:
        raise HTTPException(status_code=404, detail="提醒规则不存在")
    return item


@app.delete("/api/v1/alerts/{item_id}")
def delete_alert(item_id: int) -> dict:
    database.delete_alert(item_id)
    return {"ok": True}


@app.get("/api/v1/alerts/history")
def alert_history(limit: int = 100, unread_only: bool = False):
    return database.list_alert_triggers(limit=limit, unread_only=unread_only)


@app.get("/api/v1/alerts/unread-count")
def alert_unread_count() -> dict:
    return {"count": database.unread_alert_count()}


@app.post("/api/v1/alerts/history/read")
def mark_alert_history_read() -> dict:
    return {"updated": database.mark_alert_triggers_read()}


@app.post("/api/v1/alerts/evaluate")
def evaluate_alerts() -> dict:
    triggered = 0
    for adapter in ("spot_bonds", "treasury_futures", "convertibles"):
        dataset = service.cache.get(adapter)
        if dataset is not None:
            triggered += len(alert_engine.evaluate(adapter, dataset))
    return {"triggered": triggered}


@app.post("/api/v1/calculators/bond")
def bond_calculator(request: BondCalculatorRequest):
    try:
        return calculate_bond(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


if (FRONTEND_DIST / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=FRONTEND_DIST / "assets"),
        name="frontend-assets",
    )


@app.get("/{path:path}", include_in_schema=False)
def frontend(path: str):
    if path == "api" or path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API 路径不存在")
    dist = FRONTEND_DIST.resolve()
    target = (FRONTEND_DIST / path).resolve()
    if path and target.is_file() and target.is_relative_to(dist):
        return FileResponse(target)
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return {
        "message": "前端尚未构建，请在 frontend 目录运行 npm install && npm run build",
        "api_docs": "/docs",
    }


def run() -> None:
    port = int(os.getenv("AKDESK_PORT", "8765"))
    url = f"http://127.0.0.1:{port}"
    if os.getenv("AKDESK_NO_BROWSER", "0") != "1":
        threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


if __name__ == "__main__":
    run()
