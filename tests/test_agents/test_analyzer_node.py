from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.agents.nodes import analyzer_node as analyzer_module
from src.agents.nodes.analyzer_node import ExplanationOutput, analyzer_node


def indicator():
    return {
        "name": "WBC",
        "analyte_id": "wbc",
        "value": 7.0,
        "unit": "10^9/L",
        "status": "normal",
        "category": "normal",
        "is_abnormal": False,
        "is_critical": False,
        "explanation": "Bạch cầu giúp cơ thể chống lại nhiễm trùng và viêm.",
        "sources": ["https://trusted.test/wbc"],
    }


@pytest.mark.asyncio
async def test_analyzer_uses_curated_fallback_when_llm_and_rag_are_unavailable(monkeypatch):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: (_ for _ in ()).throw(RuntimeError("no rag")),
    )

    result = await analyzer_node({"indicators": [indicator()], "patient_gender": "male"})

    assert result["indicators"][0]["explanation"].startswith("Bạch cầu")
    assert result["retrieved_contexts"] == []


@pytest.mark.asyncio
async def test_retrieval_failure_does_not_fail_analysis(monkeypatch):
    class FailingRetriever:
        def retrieve(self, *, query, analyte_id, limit):
            raise TimeoutError("external embedding timeout")

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: FailingRetriever(),
    )

    result = await analyzer_node({"indicators": [indicator()], "patient_age": 0})

    assert result["indicators"][0]["status"] == "normal"
    assert result["indicators"][0]["explanation"].startswith("Bạch cầu")
    assert result["retrieved_contexts"] == []


@pytest.mark.asyncio
async def test_rag_is_optional_and_only_metadata_sources_are_returned(monkeypatch):
    class FakeStructuredLLM:
        async def ainvoke(self, messages):
            return ExplanationOutput(
                explanation="Lời giải thích được làm giàu nhưng không đổi phân loại.",
                sources=["https://hallucinated.test/source"],
            )

    class FakeLLM:
        def with_structured_output(self, schema):
            return FakeStructuredLLM()

    class FakeRetriever:
        def retrieve(self, *, query, analyte_id, limit):
            return [
                {
                    "indicator_name": "WBC",
                    "text": "Ngữ cảnh y khoa phi cấu trúc.",
                    "source": "https://trusted.test/rag",
                    "sources": ["https://trusted.test/rag"],
                    "score": 0.9,
                }
            ]

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: FakeRetriever())

    result = await analyzer_node({"indicators": [indicator()], "patient_gender": "male"})

    assert result["retrieved_contexts"][0]["score"] == 0.9
    assert result["indicators"][0]["status"] == "normal"
    assert result["indicators"][0]["is_critical"] is False
    assert result["indicators"][0]["sources"] == [
        "https://trusted.test/wbc",
        "https://trusted.test/rag",
    ]
    assert "hallucinated" not in " ".join(result["indicators"][0]["sources"])


@pytest.mark.asyncio
async def test_slow_llm_times_out_and_uses_curated_fallback(monkeypatch):
    class HangingStructuredLLM:
        async def ainvoke(self, messages):
            await asyncio.sleep(10)

    class HangingLLM:
        def with_structured_output(self, schema):
            return HangingStructuredLLM()

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: HangingLLM())
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: (_ for _ in ()).throw(RuntimeError("no rag")),
    )
    monkeypatch.setattr(
        analyzer_module,
        "get_settings",
        lambda: SimpleNamespace(llm_timeout_seconds=0.01),
    )

    result = await asyncio.wait_for(
        analyzer_node({"indicators": [indicator()], "patient_gender": "male"}),
        timeout=0.5,
    )

    assert result["indicators"][0]["explanation"] == indicator()["explanation"]
