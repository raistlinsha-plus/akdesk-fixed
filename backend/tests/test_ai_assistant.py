from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from app.ai_assistant import (
    AIHUBMIX_MODEL,
    MAX_RESPONSE_BYTES,
    AiAssistantService,
    AiNotConfiguredError,
    AiProviderError,
    help_context,
    market_context,
    research_context,
)
from app.settings import SecretStatus


class FakeSecrets:
    def __init__(self, key: str | None = "sk-" + "A1" * 20) -> None:
        self.key = key

    def get(self) -> str | None:
        return self.key

    def status(self) -> SecretStatus:
        return SecretStatus(bool(self.key), "test" if self.key else "none")


def test_ai_assistant_uses_fixed_model_and_returns_only_final_answer() -> None:
    captured: dict = {}

    def request(payload, key):
        captured["payload"] = payload
        captured["key"] = key
        return {
            "choices": [
                {
                    "message": {
                        "content": "先核对观测时间，再检查反证。",
                        "reasoning_content": "internal reasoning must not be returned",
                    }
                }
            ],
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            },
        }

    service = AiAssistantService(FakeSecrets(), request)
    result = asyncio.run(
        service.ask(
            scenario="research",
            question="下一步该做什么？",
            context={"selected_project": {"title": "利率研究"}},
            context_summary=["项目标题"],
        )
    )

    assert captured["payload"]["model"] == AIHUBMIX_MODEL
    assert "internal reasoning" not in result["answer"]
    assert result["answer"].startswith("先核对")
    assert result["usage"]["total_tokens"] == 150
    assert result["persisted"] is False
    assert service.status()["verified"] is True


def test_ai_assistant_requires_user_owned_key() -> None:
    service = AiAssistantService(FakeSecrets(None), lambda _payload, _key: {})

    with pytest.raises(AiNotConfiguredError, match="配置并验证"):
        asyncio.run(service.test_connection())

    assert service.status()["verification_state"] == "not_configured"


def test_ai_contexts_are_minimized_and_exclude_research_record_content() -> None:
    market = market_context(
        {
            "generated_at": "2026-07-23T10:00:00",
            "market_status": "未开盘",
            "headline": "曲线变化有限",
            "signals": [
                {
                    "title": "10Y",
                    "summary": "1.7%",
                    "payload": {"full_table": [1, 2, 3]},
                }
            ],
            "sources": [{"source": "AKShare", "source_url": "https://example.com"}],
            "settings": {"hidden": True},
        }
    )
    assert "payload" not in market["signals"][0]
    assert "settings" not in market

    project = SimpleNamespace(
        id=1,
        title="测试项目",
        question="曲线会如何变化？",
        hypothesis="可能走陡",
        status="tracking",
        confidence=55,
        horizon="1M",
        tags=["rates"],
        next_review_date="2026-07-30",
        conclusion="尚未形成",
        evidence=[
            SimpleNamespace(
                title="曲线快照",
                evidence_type="chart",
                source_summary="AKShare",
                observation_start="2026-07-22",
                observation_end="2026-07-23",
                payload={"values": [1, 2, 3]},
            )
        ],
        entries=[
            SimpleNamespace(
                entry_type="note",
                title="核对数据",
                status="open",
                due_date=None,
                content="这段正文不应发送",
            )
        ],
    )
    research = research_context(project, [project])
    encoded = str(research)
    assert "这段正文不应发送" not in encoded
    assert "values" not in encoded
    assert research["selected_project"]["research_records"][0]["title"] == "核对数据"

    help_payload = help_context("dashboard")
    assert help_payload["current_page"] == "dashboard"
    assert "health" in help_payload["modules"]


def test_ai_provider_response_limit_stops_stream_before_parsing(
    monkeypatch,
) -> None:
    class FakeResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        @staticmethod
        async def aiter_bytes():
            yield b"x" * MAX_RESPONSE_BYTES
            yield b"x"

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        @staticmethod
        def stream(*_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr("app.ai_assistant.httpx.AsyncClient", FakeClient)
    service = AiAssistantService(FakeSecrets())

    with pytest.raises(AiProviderError, match="响应过大"):
        asyncio.run(service.test_connection())


def test_ai_provider_has_a_hard_total_timeout(monkeypatch) -> None:
    class SlowResponse:
        status_code = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        @staticmethod
        async def aiter_bytes():
            await asyncio.sleep(1)
            yield b"{}"

    class FakeClient:
        def __init__(self, **_kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        @staticmethod
        def stream(*_args, **_kwargs):
            return SlowResponse()

    monkeypatch.setattr("app.ai_assistant.httpx.AsyncClient", FakeClient)
    monkeypatch.setattr("app.ai_assistant.AI_TOTAL_TIMEOUT_SECONDS", 0.01)
    service = AiAssistantService(FakeSecrets())

    with pytest.raises(AiProviderError, match="响应超时"):
        asyncio.run(service.test_connection())
