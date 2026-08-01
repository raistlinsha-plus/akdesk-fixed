from __future__ import annotations

import asyncio

from app.ai_insights import (
    AiInsightService,
    context_fingerprint,
    credit_context,
    topic_context,
)
from app.ai_runtime import AiRuntimeManager
from app.database import Database


class FakeAssistant:
    def status(self):
        return {"configured": True}

    async def ask(self, **kwargs):
        assert kwargs["scenario"] == "market_insight"
        assert "full_table" not in str(kwargs["context"])
        return {
            "answer": "变化线索：曲线变化有限。\n\n可信边界：数据来自本地缓存。",
            "provider": "AIHubMix",
            "model": "deepseek-v4-flash-think",
            "generated_at": "2026-07-27T12:00:00+08:00",
        }


class FakeRetryAssistant(FakeAssistant):
    def __init__(self) -> None:
        self.calls = 0

    async def ask(self, **kwargs):
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("模型未返回可展示的最终回答，请重试")
        return await super().ask(**kwargs)


def enabled_settings(trigger: str = "manual") -> dict:
    return {
        "daily_call_limit": 20,
        "daily_token_limit": 100_000,
        "page_insights": {
            "market": {"enabled": True, "trigger": trigger},
            "project": {"enabled": False, "trigger": "manual"},
            "credit": {"enabled": False, "trigger": "manual"},
            "topic": {"enabled": False, "trigger": "manual"},
        },
    }


def test_context_fingerprint_is_stable_and_detects_changes() -> None:
    first = context_fingerprint({"b": [2, 3], "a": 1})
    same = context_fingerprint({"a": 1, "b": [2, 3]})
    changed = context_fingerprint({"a": 2, "b": [2, 3]})

    assert first == same
    assert first != changed
    assert first.startswith("sha256:")
    assert context_fingerprint({"value": 1, "generated_at": "10:00"}) == (
        context_fingerprint({"value": 1, "generated_at": "10:01"})
    )


def test_credit_context_excludes_source_notes_and_history_rows() -> None:
    context = credit_context(
        {
            "as_of": "2026-07-27",
            "total": 1,
            "eligible": 1,
            "blocked": 0,
            "eligible_ratio": 1,
            "field_coverage": {
                "rating": {"covered": 1, "total": 1, "ratio": 1}
            },
            "summary": {"issuers": 1},
            "signals": [
                {
                    "title": "待复核",
                    "source_note": "不应发送的用户来源备注正文",
                    "history": [{"spread_bp": 10}],
                }
            ],
            "calendar": [],
            "r2_policy": "人工核验",
        }
    )

    assert "不应发送" not in str(context)
    assert "spread_bp" not in str(context)
    assert context["signals"][0]["title"] == "待复核"


def test_topic_context_excludes_note_bodies_news_and_component_values() -> None:
    context = topic_context(
        {
            "topic": {
                "title": "中美利率",
                "question": "利差如何变化？",
                "description": "跨源跟踪",
                "status": "active",
                "tags": ["利率"],
                "research_object": {
                    "object_type": "rates_theme",
                    "object_key": "rates",
                    "name": "中美利率",
                    "description": "不外发的对象长描述",
                },
                "components": [
                    {
                        "component_type": "event_radar",
                        "title": "事件",
                        "config": {"query": "不外发的查询内容"},
                    }
                ],
            },
            "project_summaries": [
                {
                    "title": "项目",
                    "status": "tracking",
                    "confidence": 60,
                    "question": "问题",
                    "conclusion": "不外发的完整结论",
                    "gaps": [],
                    "supporting_evidence": [],
                    "counter_evidence": [
                        {"title": "反证", "status": "open", "content": "不外发正文"}
                    ],
                    "open_tasks": [
                        {"title": "任务", "due_date": None, "content": "不外发任务正文"}
                    ],
                }
            ],
            "timeline": [
                {
                    "event_type": "entry",
                    "title": "记录标题",
                    "summary": "不外发的笔记或新闻正文",
                    "project_title": "项目",
                    "event_time": "2026-07-28T10:00:00",
                    "metadata": {"source": "GDELT", "raw_news": "不外发新闻"},
                }
            ],
            "timeline_total": 1,
        }
    )

    encoded = str(context)
    assert "不外发" not in encoded
    assert context["topic"]["components"][0]["config_keys"] == ["query"]
    assert context["timeline"][0]["source"] == "GDELT"


def test_insight_queue_persists_only_final_summary_and_metadata(tmp_path) -> None:
    async def run() -> None:
        database = Database(tmp_path / "insights.db")
        runtime = AiRuntimeManager(database)
        runtime.update_settings(enabled_settings())
        service = AiInsightService(database, FakeAssistant(), runtime)  # type: ignore[arg-type]
        await service.start()
        try:
            context = {"headline": "测试", "signals": []}
            queued = service.enqueue(
                context_type="market",
                context_key="today",
                context=context,
                context_summary=["最多 8 条线索"],
            )
            assert queued["status"] == "generating"
            assert service._queue is not None
            await service._queue.join()

            ready = service.status(
                context_type="market",
                context_key="today",
                fingerprint=context_fingerprint(context),
                context_summary=["最多 8 条线索"],
            )
            assert ready["status"] == "ready"
            assert ready["summary"].startswith("变化线索")
            assert ready["job_state"] == "idle"
            with database._connect() as connection:
                columns = {
                    str(row["name"])
                    for row in connection.execute("PRAGMA table_info(ai_insights)")
                }
            assert "prompt" not in columns
            assert "context" not in columns
        finally:
            await service.stop()

    asyncio.run(run())


def test_changed_context_marks_cached_insight_stale_and_auto_due(tmp_path) -> None:
    database = Database(tmp_path / "insights.db")
    runtime = AiRuntimeManager(database)
    runtime.update_settings(enabled_settings("data_change"))
    service = AiInsightService(database, FakeAssistant(), runtime)  # type: ignore[arg-type]
    database.save_ai_insight(
        context_type="market",
        context_key="today",
        context_fingerprint=context_fingerprint({"value": 1}),
        status="ready",
        summary="旧摘要",
        context_summary=["旧上下文"],
        provider="AIHubMix",
        model="deepseek-v4-flash-think",
        generated_at="2026-07-27T10:00:00+08:00",
    )

    status = service.status(
        context_type="market",
        context_key="today",
        fingerprint=context_fingerprint({"value": 2}),
        context_summary=["新上下文"],
    )

    assert status["status"] == "stale"
    assert status["summary"] == "旧摘要"
    assert status["auto_due"] is True


def test_insight_worker_retries_one_empty_final_answer(tmp_path) -> None:
    async def run() -> None:
        database = Database(tmp_path / "retry.db")
        runtime = AiRuntimeManager(database)
        runtime.update_settings(enabled_settings())
        assistant = FakeRetryAssistant()
        service = AiInsightService(database, assistant, runtime)  # type: ignore[arg-type]
        await service.start()
        try:
            context = {"headline": "测试"}
            service.enqueue(
                context_type="market",
                context_key="today",
                context=context,
                context_summary=["市场摘要"],
            )
            assert service._queue is not None
            await service._queue.join()
            ready = service.status(
                context_type="market",
                context_key="today",
                fingerprint=context_fingerprint(context),
                context_summary=["市场摘要"],
            )
            assert assistant.calls == 2
            assert ready["status"] == "ready"
        finally:
            await service.stop()

    asyncio.run(run())
