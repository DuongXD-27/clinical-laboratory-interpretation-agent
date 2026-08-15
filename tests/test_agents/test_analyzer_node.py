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

    assert "nằm trong khoảng tham chiếu được hệ thống sử dụng" in result["indicators"][0]["explanation"]
    assert result["indicators"][0]["explanation"].endswith(indicator()["explanation"])
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
    assert "nằm trong khoảng tham chiếu được hệ thống sử dụng" in result["indicators"][0]["explanation"]
    assert result["indicators"][0]["explanation"].endswith(indicator()["explanation"])
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

    assert "nằm trong khoảng tham chiếu được hệ thống sử dụng" in result["indicators"][0]["explanation"]
    assert result["indicators"][0]["explanation"].endswith(indicator()["explanation"])


@pytest.mark.asyncio
async def test_analyzer_rag_disabled_produces_curated_explanation(monkeypatch):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: None,
    )

    potassium_indicator = {
        "name": "Potassium",
        "analyte_id": "potassium",
        "value": 4.5,
        "unit": "mmol/L",
        "status": "normal",
        "category": "electrolyte",
        "is_abnormal": False,
        "is_critical": False,
        "explanation": "",
    }

    result = await analyzer_node({"indicators": [potassium_indicator], "patient_gender": "male"})

    explanation = result["indicators"][0]["explanation"]
    assert len(explanation) > 30
    assert "Phát hiện nội dung có thể chứa yếu tố suy đoán" not in explanation
    assert "nằm trong khoảng tham chiếu được hệ thống sử dụng" in explanation
    assert len(result["indicators"][0]["sources"]) > 0


@pytest.mark.asyncio
async def test_analyzer_rag_zero_chunks_degrades_gracefully_to_curated(monkeypatch):
    class EmptyRetriever:
        def retrieve(self, *, query, analyte_id, limit):
            return []

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: EmptyRetriever(),
    )

    wbc_high = {
        "name": "WBC",
        "analyte_id": "wbc",
        "value": 15.0,
        "unit": "10^9/L",
        "status": "high",
        "category": "hematology",
        "is_abnormal": True,
        "is_critical": False,
        "explanation": "",
    }

    result = await analyzer_node({"indicators": [wbc_high], "patient_gender": "male"})

    explanation = result["indicators"][0]["explanation"]
    assert len(explanation) > 30
    assert "Phát hiện nội dung có thể chứa yếu tố suy đoán" not in explanation
    assert "cao so với khoảng tham chiếu được hệ thống sử dụng" in explanation
    assert result["retrieved_contexts"] == []


@pytest.mark.asyncio
async def test_analyzer_status_aware_note_selection_high_vs_low_vs_normal(monkeypatch):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: None)

    for status_val, expected_qualifier in [
        ("normal", "nằm trong khoảng tham chiếu"),
        ("high", "cao so với khoảng tham chiếu"),
        ("low", "thấp so với khoảng tham chiếu"),
    ]:
        ind = {
            "name": "WBC",
            "analyte_id": "wbc",
            "value": 7.0,
            "unit": "10^9/L",
            "status": status_val,
            "category": "hematology",
            "is_abnormal": status_val != "normal",
            "is_critical": False,
            "explanation": "",
        }
        result = await analyzer_node({"indicators": [ind], "patient_gender": "male"})
        exp = result["indicators"][0]["explanation"]
        assert expected_qualifier in exp
        assert "Phát hiện nội dung có thể chứa yếu tố suy đoán" not in exp


@pytest.mark.asyncio
async def test_analyzer_unsupported_generic_glucose_fails_closed(monkeypatch):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: None)

    unsupported_ind = {
        "name": "Glucose",
        "analyte_id": "unknown",
        "value": 5.2,
        "unit": "mmol/L",
        "status": "unknown",
        "category": "unknown",
        "is_abnormal": False,
        "is_critical": False,
        "explanation": "",
    }

    result = await analyzer_node({"indicators": [unsupported_ind], "patient_gender": "male"})
    # Must NOT map to FPG or have FPG sources
    assert result["indicators"][0]["status"] == "unknown"
    assert "Fasting plasma glucose" not in result["indicators"][0]["name"]


@pytest.mark.asyncio
async def test_analyzer_critical_status_qualification_with_separated_status(monkeypatch):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: None)

    critical_ind = {
        "name": "Potassium",
        "analyte_id": "potassium",
        "value": 6.5,
        "unit": "mmol/L",
        "status": "high",
        "critical_status": "critical_high",
        "category": "electrolytes",
        "is_abnormal": True,
        "is_critical": True,
        "explanation": "",
    }

    result = await analyzer_node({"indicators": [critical_ind], "patient_gender": "male"})
    ind = result["indicators"][0]
    assert ind["status"] == "high"
    assert ind["critical_status"] == "critical_high"
    assert "vượt ngưỡng cảnh báo nguy kịch" in ind["explanation"]
    assert "Phát hiện nội dung có thể chứa yếu tố suy đoán" not in ind["explanation"]

