from __future__ import annotations

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest

from app.ai_assistant import (
    AIHUBMIX_MODEL,
    MAX_RESPONSE_BYTES,
    AI_FRED_BOUNDARY_NOTICE,
    AiAssistantService,
    AiNotConfiguredError,
    AiProviderError,
    help_context,
    market_context,
    research_context,
    isolate_fred_ai_context,
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


def test_research_context_excludes_entire_fred_evidence_without_changing_notes() -> None:
    fred_evidence = SimpleNamespace(
        title="DGS10 987.654（不得外发的标题值）",
        evidence_type="chart",
        source_summary="美国利率 987.654",
        observation_start="2026-07-22",
        observation_end="2026-07-23",
        payload={"provider": "FRED", "series": [{"series_id": "DGS10"}]},
    )
    project = SimpleNamespace(
        id=1, title="混合研究", question="如何核验？", hypothesis="待核验",
        status="tracking", confidence=50, horizon="1M", tags=["rates"],
        next_review_date=None, conclusion="尚未形成",
        evidence=[fred_evidence, SimpleNamespace(
            title="本地曲线证据", evidence_type="snapshot", source_summary="AKShare",
            observation_start=None, observation_end=None, payload={},
        )],
        entries=[SimpleNamespace(
            entry_type="note", title="手工 FRED 记录 987.654", status="open",
            due_date=None, content="原笔记必须保留",
        )],
    )
    before = copy.deepcopy(vars(project))
    context = research_context(project, [project])
    encoded = json.dumps(context, ensure_ascii=False)

    assert "987.654" not in encoded
    assert "DGS10" not in encoded
    assert context["selected_project"]["evidence"][0]["title"] == "本地曲线证据"
    assert context["selected_project"]["research_records"] == []
    assert vars(project) == before


def test_final_ai_boundary_strips_fred_metadata_and_keeps_other_sources() -> None:
    captured: list[dict] = []

    def request(payload, _key):
        captured.append(payload)
        return {"choices": [{"message": {"content": "请核验保留的本地证据。"}}]}

    context = {
        "fred_series": {"series_id": "DGS10", "values": [987.654]},
        "evidence": [
            {"title": "隐藏标题值 987.654", "metadata": {"provider": "FRED"}},
            {"title": "禁止处理 765.432", "ai_processing_allowed": False},
            {"title": "国内曲线", "source": "AKShare", "value": 1.8},
        ],
    }
    before = copy.deepcopy(context)
    safe = isolate_fred_ai_context(context)
    assert safe == isolate_fred_ai_context(safe)
    service = AiAssistantService(FakeSecrets(), request)
    answer = asyncio.run(service.ask(
        scenario="research", question="下一步怎样核验？", context=context,
        context_summary=["FRED · DGS10 · 987.654", "项目证据"],
    ))
    outbound = json.dumps(captured, ensure_ascii=False)
    assert "987.654" not in outbound
    assert "765.432" not in outbound
    assert "DGS10" not in outbound
    assert "国内曲线" in outbound
    assert "DGS10" not in json.dumps(answer["context_summary"])
    assert AI_FRED_BOUNDARY_NOTICE in answer["context_summary"]
    assert context == before


@pytest.mark.parametrize("question", [
    '{"provider":"FRED","series_id":"DGS10","value":987.654}',
    "来源：FRED，DGS10=987.654，请分析",
    "查看 https://fred.stlouisfed.org/series/DGS10",
])
def test_explicit_fred_source_input_is_rejected_before_any_provider_call(question) -> None:
    calls = []
    service = AiAssistantService(FakeSecrets(), lambda *args: calls.append(args))
    with pytest.raises(AiProviderError, match="保守隔离策略"):
        asyncio.run(service.ask(
            scenario="research", question=question, context={}, context_summary=[],
        ))
    assert calls == []


@pytest.mark.parametrize("question", [
    "FRED条款怎样查看？",
    '{"question":"FRED条款怎样查看？"}',
])
def test_ordinary_fred_product_or_terms_question_is_not_blanket_rejected(question) -> None:
    service = AiAssistantService(FakeSecrets(), lambda *_args: {
        "choices": [{"message": {"content": "请阅读数据使用规则和原始条款。"}}],
    })
    result = asyncio.run(service.ask(
        scenario="help", question=question, context=help_context("macro"),
        context_summary=[],
    ))
    assert result["answer"].startswith("请阅读")
    assert any("无法全面识别" in notice for notice in result["context_summary"])


def test_market_context_drops_fred_signals_before_projection() -> None:
    context = market_context({
        "headline": "国内市场核验",
        "signals": [
            {"title": "标题值 987.654", "payload": {"provider": "FRED"}},
            {"title": "国内曲线", "source": "AKShare"},
        ],
        "sources": [{"source": "FRED", "series_id": "DGS10"}],
    })
    assert [item["title"] for item in context["signals"]] == ["国内曲线"]
    assert context["sources"] == []


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
