from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .database import Database


AI_TIMEZONE = ZoneInfo("Asia/Shanghai")
AI_RUNTIME_SETTING_KEY = "ai_runtime_settings"
AI_INSIGHT_CONTEXTS = ("market", "project", "credit", "topic")
AI_INSIGHT_TRIGGERS = ("manual", "data_change", "daily")
AI_RUNTIME_DEFAULTS: dict[str, Any] = {
    "daily_call_limit": 20,
    "daily_token_limit": 100_000,
    "page_insights": {
        context: {"enabled": False, "trigger": "manual"}
        for context in AI_INSIGHT_CONTEXTS
    },
}


class AiUsageLimitError(RuntimeError):
    pass


def normalize_runtime_settings(payload: object) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    calls = source.get("daily_call_limit", AI_RUNTIME_DEFAULTS["daily_call_limit"])
    tokens = source.get("daily_token_limit", AI_RUNTIME_DEFAULTS["daily_token_limit"])
    try:
        daily_call_limit = min(200, max(1, int(calls)))
    except (TypeError, ValueError):
        daily_call_limit = int(AI_RUNTIME_DEFAULTS["daily_call_limit"])
    try:
        daily_token_limit = min(2_000_000, max(1_000, int(tokens)))
    except (TypeError, ValueError):
        daily_token_limit = int(AI_RUNTIME_DEFAULTS["daily_token_limit"])

    policies = source.get("page_insights")
    policies = policies if isinstance(policies, dict) else {}
    page_insights: dict[str, dict[str, Any]] = {}
    for context in AI_INSIGHT_CONTEXTS:
        raw = policies.get(context)
        raw = raw if isinstance(raw, dict) else {}
        trigger = str(raw.get("trigger") or "manual")
        page_insights[context] = {
            "enabled": bool(raw.get("enabled", False)),
            "trigger": trigger if trigger in AI_INSIGHT_TRIGGERS else "manual",
        }
    return {
        "daily_call_limit": daily_call_limit,
        "daily_token_limit": daily_token_limit,
        "page_insights": page_insights,
    }


class AiRuntimeManager:
    """Persistent AI budget and page-insight policy for a personal local install."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _today() -> str:
        return datetime.now(AI_TIMEZONE).date().isoformat()

    def settings(self) -> dict[str, Any]:
        return normalize_runtime_settings(
            self.database.get_setting(AI_RUNTIME_SETTING_KEY, AI_RUNTIME_DEFAULTS)
        )

    def update_settings(self, payload: dict[str, Any]) -> dict[str, Any]:
        settings = normalize_runtime_settings(payload)
        self.database.set_setting(AI_RUNTIME_SETTING_KEY, settings)
        return settings

    def usage(self) -> dict[str, Any]:
        usage = self.database.get_ai_usage(self._today())
        settings = self.settings()
        calls_remaining = max(0, settings["daily_call_limit"] - usage["calls"])
        tokens_remaining = max(
            0, settings["daily_token_limit"] - usage["total_tokens"]
        )
        return {
            **usage,
            "by_context": self.database.get_ai_usage_by_context(self._today()),
            "calls_remaining": calls_remaining,
            "tokens_remaining": tokens_remaining,
            "limit_reached": calls_remaining == 0 or tokens_remaining == 0,
        }

    def ensure_available(self) -> None:
        usage = self.usage()
        if usage["calls_remaining"] <= 0:
            raise AiUsageLimitError(
                "已达到今日 AI 调用上限；可在 AI 助手的“预算与页面洞察”中调整"
            )
        if usage["tokens_remaining"] <= 0:
            raise AiUsageLimitError(
                "已达到今日 AI token 预算；可在 AI 助手的“预算与页面洞察”中调整"
            )

    def record_usage(self, usage: dict[str, Any]) -> None:
        self.database.record_ai_usage(
            usage_date=self._today(),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
            context_type=str(usage.get("context_type") or "assistant"),
            context_key=str(usage.get("context_key") or ""),
        )

    def status(self, *, busy: bool = False, queue_depth: int = 0) -> dict[str, Any]:
        return {
            "settings": self.settings(),
            "usage": self.usage(),
            "task_state": "running" if busy else "queued" if queue_depth else "idle",
            "active_requests": 1 if busy else 0,
            "queue_depth": max(0, queue_depth),
            "concurrency_limit": 1,
            "persistence": {
                "usage": "SQLite 仅保存每日次数与 token 汇总",
                "insights": "页面洞察只保存最终摘要、上下文指纹和生成元数据",
                "excluded": "API Key、完整提示词、思维过程、附件正文和新闻正文不落库",
            },
        }
