from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.ai_runtime import AiRuntimeManager, AiUsageLimitError
from app.database import Database


def test_ai_runtime_defaults_are_private_and_opt_in(tmp_path) -> None:
    database = Database(tmp_path / "runtime.db")
    runtime = AiRuntimeManager(database)

    status = runtime.status()

    assert status["settings"]["daily_call_limit"] == 20
    assert status["settings"]["daily_token_limit"] == 100_000
    assert all(
        not policy["enabled"]
        for policy in status["settings"]["page_insights"].values()
    )
    assert status["task_state"] == "idle"
    assert status["concurrency_limit"] == 1
    assert "完整提示词" in status["persistence"]["excluded"]


def test_ai_runtime_records_daily_usage_and_enforces_both_limits(tmp_path) -> None:
    database = Database(tmp_path / "runtime.db")
    runtime = AiRuntimeManager(database)
    runtime.update_settings(
        {
            "daily_call_limit": 2,
            "daily_token_limit": 1_000,
            "page_insights": {
                "market": {"enabled": True, "trigger": "manual"},
                "project": {"enabled": False, "trigger": "manual"},
                "credit": {"enabled": False, "trigger": "manual"},
                "topic": {"enabled": False, "trigger": "manual"},
            },
        }
    )

    runtime.record_usage(
        {
            "prompt_tokens": 300,
            "completion_tokens": 100,
            "total_tokens": 400,
            "context_type": "market_insight",
        }
    )
    runtime.ensure_available()
    runtime.record_usage(
        {"prompt_tokens": 400, "completion_tokens": 200, "total_tokens": 600}
    )

    usage = runtime.usage()
    assert usage["calls"] == 2
    assert usage["total_tokens"] == 1_000
    assert usage["by_context"]["market_insight"]["calls"] == 1
    assert usage["by_context"]["assistant"]["calls"] == 1
    assert usage["limit_reached"] is True
    with pytest.raises(AiUsageLimitError, match="调用上限"):
        runtime.ensure_available()


def test_ai_insight_cache_only_keeps_final_summary_and_metadata(tmp_path) -> None:
    database = Database(tmp_path / "runtime.db")
    generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()

    saved = database.save_ai_insight(
        context_type="market",
        context_key="today",
        context_fingerprint="sha256:abc",
        status="ready",
        summary="最终摘要",
        context_summary=["8 条线索", "3 个来源"],
        provider="AIHubMix",
        model="deepseek-v4-flash-think",
        generated_at=generated_at,
    )

    assert saved["summary"] == "最终摘要"
    assert saved["context_summary"] == ["8 条线索", "3 个来源"]
    assert set(saved) == {
        "id",
        "context_type",
        "context_key",
        "context_fingerprint",
        "status",
        "summary",
        "context_summary",
        "provider",
        "model",
        "generated_at",
        "last_error",
        "created_at",
        "updated_at",
    }
    assert database.delete_ai_insight("market", "today") is True
    assert database.get_ai_insight("market", "today") is None
