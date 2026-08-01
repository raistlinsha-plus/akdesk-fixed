from __future__ import annotations

import asyncio
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .ai_assistant import (
    AIHUBMIX_MODEL,
    AIHUBMIX_MODEL_LABEL,
    AiAssistantService,
    AiBusyError,
    AiNotConfiguredError,
    AiProviderError,
)
from .ai_runtime import AI_TIMEZONE, AiRuntimeManager, AiUsageLimitError
from .database import Database


class AiInsightDisabledError(RuntimeError):
    pass


class AiInsightQueueFullError(RuntimeError):
    pass


def context_fingerprint(context: dict[str, Any]) -> str:
    stable_context = dict(context)
    # Request construction time is useful to the model but must not make an
    # otherwise unchanged page look stale on every status poll.
    stable_context.pop("generated_at", None)
    encoded = json.dumps(
        stable_context,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def credit_context(workspace: dict[str, Any]) -> dict[str, Any]:
    coverage = workspace.get("field_coverage")
    coverage = coverage if isinstance(coverage, dict) else {}
    return {
        "as_of": workspace.get("as_of"),
        "coverage": {
            "total": workspace.get("total"),
            "eligible": workspace.get("eligible"),
            "blocked": workspace.get("blocked"),
            "eligible_ratio": workspace.get("eligible_ratio"),
            "field_coverage": {
                field: {
                    "covered": item.get("covered"),
                    "total": item.get("total"),
                    "ratio": item.get("ratio"),
                }
                for field, item in coverage.items()
                if isinstance(item, dict)
            },
        },
        "summary": workspace.get("summary"),
        "signals": [
            {
                key: signal.get(key)
                for key in (
                    "kind",
                    "level",
                    "title",
                    "detail",
                    "bond_code",
                    "issuer",
                    "observation_date",
                    "quality_state",
                    "requires_manual_confirmation",
                )
            }
            for signal in workspace.get("signals", [])[:12]
            if isinstance(signal, dict)
        ],
        "calendar": [
            {
                key: event.get(key)
                for key in ("date", "kind", "title", "bond_code", "issuer", "overdue")
            }
            for event in workspace.get("calendar", [])[:12]
            if isinstance(event, dict)
        ],
        "policy": workspace.get("r2_policy"),
    }


def topic_context(workspace: dict[str, Any]) -> dict[str, Any]:
    """Minimize a topic workspace before external processing."""
    topic = workspace.get("topic")
    if hasattr(topic, "model_dump"):
        topic = topic.model_dump(mode="json")
    topic = topic if isinstance(topic, dict) else {}
    components = topic.get("components")
    components = components if isinstance(components, list) else []
    project_summaries = workspace.get("project_summaries")
    project_summaries = (
        project_summaries if isinstance(project_summaries, list) else []
    )
    timeline = workspace.get("timeline")
    timeline = timeline if isinstance(timeline, list) else []
    return {
        "topic": {
            "title": topic.get("title"),
            "question": topic.get("question"),
            "description": topic.get("description"),
            "status": topic.get("status"),
            "tags": topic.get("tags"),
            "research_object": {
                key: (
                    topic.get("research_object", {}).get(key)
                    if isinstance(topic.get("research_object"), dict)
                    else None
                )
                for key in ("object_type", "object_key", "name")
            },
            "components": [
                {
                    "component_type": item.get("component_type"),
                    "title": item.get("title"),
                    "config_keys": sorted(
                        item.get("config", {}).keys()
                        if isinstance(item.get("config"), dict)
                        else []
                    ),
                }
                for item in components[:12]
                if isinstance(item, dict)
            ],
        },
        "project_summaries": [
            {
                "title": item.get("title"),
                "status": item.get("status"),
                "confidence": item.get("confidence"),
                "question": item.get("question"),
                "gaps": item.get("gaps"),
                "next_review_date": item.get("next_review_date"),
                "supporting_evidence": [
                    {
                        "title": evidence.get("title"),
                        "source": evidence.get("source"),
                        "observation_end": evidence.get("observation_end"),
                    }
                    for evidence in item.get("supporting_evidence", [])[:5]
                    if isinstance(evidence, dict)
                ],
                "counter_evidence": [
                    {
                        "title": evidence.get("title"),
                        "status": evidence.get("status"),
                    }
                    for evidence in item.get("counter_evidence", [])[:5]
                    if isinstance(evidence, dict)
                ],
                "open_tasks": [
                    {
                        "title": task.get("title"),
                        "due_date": task.get("due_date"),
                    }
                    for task in item.get("open_tasks", [])[:8]
                    if isinstance(task, dict)
                ],
            }
            for item in project_summaries[:8]
            if isinstance(item, dict)
        ],
        "timeline": [
            {
                "event_type": item.get("event_type"),
                "title": item.get("title"),
                "project_title": item.get("project_title"),
                "event_time": item.get("event_time"),
                "observation_time": item.get("observation_time"),
                "source": (
                    item.get("metadata", {}).get("source")
                    if isinstance(item.get("metadata"), dict)
                    else None
                ),
            }
            for item in timeline[:20]
            if isinstance(item, dict)
        ],
        "timeline_total": workspace.get("timeline_total"),
    }


INSIGHT_QUESTIONS = {
    "market": (
        "请生成本页市场洞察。用“变化线索 / 可信边界 / 下一步核验”三个短段，"
        "只写上下文可支持的内容，总长不超过 450 个汉字。"
    ),
    "project": (
        "请生成本项目研究洞察。用“当前证据 / 关键缺口 / 下一步验证”三个短段，"
        "不要替用户改写结论，总长不超过 450 个汉字。"
    ),
    "credit": (
        "请生成本页信用观察洞察。用“新增信号 / 数据缺口 / 人工复核任务”三个短段，"
        "不得生成评级、违约概率或投资结论，总长不超过 450 个汉字。"
    ),
    "topic": (
        "请生成本专题跨源综述。用“共同变化 / 来源分歧 / 证据缺口 / 下一步核验”四个短段，"
        "不得把共现写成因果，不替用户形成投资结论，总长不超过 550 个汉字。"
    ),
}


@dataclass(slots=True)
class AiInsightJob:
    context_type: str
    context_key: str
    fingerprint: str
    context: dict[str, Any]
    context_summary: list[str]


class AiInsightService:
    """Single-worker page insight queue with metadata-only local persistence."""

    def __init__(
        self,
        database: Database,
        assistant: AiAssistantService,
        runtime: AiRuntimeManager,
    ) -> None:
        self.database = database
        self.assistant = assistant
        self.runtime = runtime
        self._queue: asyncio.Queue[AiInsightJob | None] | None = None
        self._worker_task: asyncio.Task[None] | None = None
        self._pending_keys: set[tuple[str, str]] = set()
        self._active_key: tuple[str, str] | None = None

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    def is_active(self, context_type: str, context_key: str) -> bool:
        return self._active_key == (context_type, context_key)

    async def start(self) -> None:
        if self._worker_task and not self._worker_task.done():
            return
        self.database.fail_interrupted_ai_insights()
        self._queue = asyncio.Queue(maxsize=10)
        self._worker_task = asyncio.create_task(
            self._worker(), name="akdesk-ai-insight-worker"
        )

    async def stop(self) -> None:
        if self._worker_task is None:
            return
        queue = self._queue
        if queue is not None:
            await queue.put(None)
        try:
            await asyncio.wait_for(self._worker_task, timeout=5)
        except TimeoutError:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        finally:
            self._worker_task = None
            self._queue = None
            self._pending_keys.clear()
            self._active_key = None

    def status(
        self,
        *,
        context_type: str,
        context_key: str,
        fingerprint: str,
        context_summary: list[str],
    ) -> dict[str, Any]:
        settings = self.runtime.settings()
        policy = settings["page_insights"][context_type]
        usage = self.runtime.usage()
        record = self.database.get_ai_insight(context_type, context_key)
        job_key = (context_type, context_key)
        job_state = (
            "running"
            if self._active_key == job_key
            else "queued"
            if job_key in self._pending_keys
            else "idle"
        )
        status = "never_generated"
        if record is not None:
            status = record["status"]
            if status == "ready" and record["context_fingerprint"] != fingerprint:
                status = "stale"
        generated_at = record["generated_at"] if record else None
        generated_date = None
        if generated_at:
            try:
                parsed_generated_at = datetime.fromisoformat(str(generated_at))
                if parsed_generated_at.tzinfo is None:
                    parsed_generated_at = parsed_generated_at.replace(
                        tzinfo=AI_TIMEZONE
                    )
                generated_date = parsed_generated_at.astimezone(AI_TIMEZONE).date()
            except ValueError:
                generated_date = None
        today = datetime.now(AI_TIMEZONE).date()
        auto_due = bool(
            policy["enabled"]
            and job_state == "idle"
            and (
                policy["trigger"] == "data_change"
                and status in {"never_generated", "stale"}
                or policy["trigger"] == "daily"
                and generated_date != today
            )
        )
        configured = bool(self.assistant.status()["configured"])
        return {
            "context_type": context_type,
            "context_key": context_key,
            "context_fingerprint": fingerprint,
            "status": status,
            "job_state": job_state,
            "summary": record["summary"] if record else "",
            "context_summary": context_summary,
            "cached_context_summary": record["context_summary"] if record else [],
            "provider": record["provider"] if record else "AIHubMix",
            "model": record["model"] if record else AIHUBMIX_MODEL,
            "model_label": AIHUBMIX_MODEL_LABEL,
            "generated_at": generated_at,
            "updated_at": record["updated_at"] if record else None,
            "last_error": record["last_error"] if record else None,
            "policy": policy,
            "configured": configured,
            "auto_due": auto_due,
            "can_generate": bool(
                configured
                and policy["enabled"]
                and job_state == "idle"
                and not usage["limit_reached"]
            ),
            "usage": usage,
            "persistence_notice": (
                "本机只缓存最终摘要、上下文指纹、模型与生成时间；"
                "不保存完整提示词、思维过程或上下文副本。"
            ),
        }

    def enqueue(
        self,
        *,
        context_type: str,
        context_key: str,
        context: dict[str, Any],
        context_summary: list[str],
        force: bool = False,
    ) -> dict[str, Any]:
        policy = self.runtime.settings()["page_insights"][context_type]
        if not policy["enabled"]:
            raise AiInsightDisabledError(
                "本页面的 AI 洞察尚未授权；请先在 AI 助手中开启"
            )
        if not self.assistant.status()["configured"]:
            raise AiInsightDisabledError("请先配置 AIHubMix API Key")
        self.runtime.ensure_available()
        if self._queue is None or self._worker_task is None:
            raise RuntimeError("AI 洞察任务服务尚未启动")

        fingerprint = context_fingerprint(context)
        current = self.database.get_ai_insight(context_type, context_key)
        job_key = (context_type, context_key)
        if job_key in self._pending_keys:
            return self.status(
                context_type=context_type,
                context_key=context_key,
                fingerprint=fingerprint,
                context_summary=context_summary,
            )
        if (
            not force
            and current
            and current["status"] == "ready"
            and current["context_fingerprint"] == fingerprint
        ):
            return self.status(
                context_type=context_type,
                context_key=context_key,
                fingerprint=fingerprint,
                context_summary=context_summary,
            )

        self.database.save_ai_insight(
            context_type=context_type,
            context_key=context_key,
            context_fingerprint=fingerprint,
            status="generating",
            summary=current["summary"] if current else "",
            context_summary=context_summary,
            provider=current["provider"] if current else "AIHubMix",
            model=current["model"] if current else AIHUBMIX_MODEL,
            generated_at=current["generated_at"] if current else None,
        )
        job = AiInsightJob(
            context_type=context_type,
            context_key=context_key,
            fingerprint=fingerprint,
            context=context,
            context_summary=context_summary,
        )
        try:
            self._queue.put_nowait(job)
        except asyncio.QueueFull as exc:
            self.database.save_ai_insight(
                context_type=context_type,
                context_key=context_key,
                context_fingerprint=fingerprint,
                status="failed",
                summary=current["summary"] if current else "",
                context_summary=context_summary,
                provider=current["provider"] if current else "AIHubMix",
                model=current["model"] if current else AIHUBMIX_MODEL,
                generated_at=current["generated_at"] if current else None,
                last_error="AI 洞察任务队列已满，请稍后重试",
            )
            raise AiInsightQueueFullError(
                "AI 洞察任务队列已满，请稍后重试"
            ) from exc
        self._pending_keys.add(job_key)
        return self.status(
            context_type=context_type,
            context_key=context_key,
            fingerprint=fingerprint,
            context_summary=context_summary,
        )

    async def _worker(self) -> None:
        assert self._queue is not None
        while True:
            job = await self._queue.get()
            if job is None:
                self._queue.task_done()
                return
            job_key = (job.context_type, job.context_key)
            self._active_key = job_key
            try:
                result = None
                for attempt in range(2):
                    try:
                        result = await self.assistant.ask(
                            scenario=f"{job.context_type}_insight",
                            question=INSIGHT_QUESTIONS[job.context_type],
                            context=job.context,
                            context_summary=job.context_summary,
                        )
                        break
                    except RuntimeError as exc:
                        if attempt == 0 and "最终回答" in str(exc):
                            continue
                        raise
                assert result is not None
                self.database.save_ai_insight(
                    context_type=job.context_type,
                    context_key=job.context_key,
                    context_fingerprint=job.fingerprint,
                    status="ready",
                    summary=result["answer"],
                    context_summary=job.context_summary,
                    provider=result["provider"],
                    model=result["model"],
                    generated_at=result["generated_at"],
                )
            except Exception as exc:
                current = self.database.get_ai_insight(
                    job.context_type, job.context_key
                )
                safe_error = (
                    str(exc)
                    if isinstance(
                        exc,
                        (
                            AiBusyError,
                            AiNotConfiguredError,
                            AiProviderError,
                            AiUsageLimitError,
                        ),
                    )
                    else "本地 AI 洞察任务失败，请重试"
                )
                self.database.save_ai_insight(
                    context_type=job.context_type,
                    context_key=job.context_key,
                    context_fingerprint=job.fingerprint,
                    status="failed",
                    summary=current["summary"] if current else "",
                    context_summary=job.context_summary,
                    provider=current["provider"] if current else "AIHubMix",
                    model=current["model"] if current else AIHUBMIX_MODEL,
                    generated_at=current["generated_at"] if current else None,
                    last_error=safe_error,
                )
            finally:
                self._active_key = None
                self._pending_keys.discard(job_key)
                self._queue.task_done()
