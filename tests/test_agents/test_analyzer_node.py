from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.agents.nodes import analyzer_node as analyzer_module
from src.agents.nodes.analyzer_node import ExplanationOutput, analyzer_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.services.medical_safety_validator import MedicalSafetyValidator


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
        def retrieve(self, *, query, analyte_id, status, limit, band_id=None, critical_status=None):
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
        lambda: SimpleNamespace(llm_timeout_seconds=0.01, max_analyzer_context_chars=4000),
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
async def test_unknown_status_skips_rag_and_llm_but_keeps_curated_catalog(monkeypatch):
    calls = {"rag": 0, "llm": 0}

    class FakeRetriever:
        def retrieve(self, *, query, analyte_id, status, limit, band_id=None, critical_status=None):
            calls["rag"] += 1
            raise AssertionError("RAG must not run for status='unknown'")

    class FakeLLM:
        def with_structured_output(self, schema):
            return object()

    async def counted_llm_call(structured_llm, prompt):
        calls["llm"] += 1
        raise AssertionError("LLM explanation must not run for status='unknown'")

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: FakeRetriever())
    monkeypatch.setattr(analyzer_module, "call_llm_with_retry", counted_llm_call)

    unknown_with_catalog = {
        "name": "Uric acid",
        "analyte_id": "uric_acid",
        "value": 420.0,
        "unit": "umol/L",
        "status": "unknown",
        "category": "unknown",
        "is_abnormal": False,
        "is_critical": False,
        "explanation": "",
        "sources": [],
    }

    result = await analyzer_node({"indicators": [unknown_with_catalog], "patient_gender": "male"})

    indicator_result = result["indicators"][0]
    assert calls == {"rag": 0, "llm": 0}
    assert result["retrieved_contexts"] == []
    assert indicator_result["status"] == "unknown"
    assert indicator_result["is_critical"] is False
    assert "Acid uric" in indicator_result["explanation"]
    assert indicator_result["sources"] == ["https://ard.bmj.com/content/76/1/29"]


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


@pytest.mark.asyncio
async def test_urea_high_uses_only_safe_grounding_segments(monkeypatch):
    assessment = await reference_range_checker_node(
        {
            "patient_age": 30,
            "patient_gender": "female",
            "raw_indicators": [{"name": "Urea", "value": 7.9, "unit": "mmol/L"}],
        }
    )
    urea = assessment["indicators"][0]
    assert (urea["reference_low"], urea["reference_high"], urea["status"]) == (
        2.5,
        7.8,
        "high",
    )

    class CapturingStructuredLLM:
        prompt = ""

        async def ainvoke(self, messages):
            self.prompt = messages[0].content
            return ExplanationOutput(
                explanation=(
                    "Giá trị Urea là 7.9 mmol/L. "
                    "Ure là sản phẩm chuyển hóa của protein."
                )
            )

    structured_llm = CapturingStructuredLLM()

    class FakeLLM:
        def with_structured_output(self, _schema):
            return structured_llm

    class FakeRetriever:
        def retrieve(self, **_kwargs):
            return [
                {
                    "indicator_name": "Urea",
                    "text": (
                        "Ure máu tăng có thể do suy giảm chức năng bài tiết của thận. "
                        "Ure là sản phẩm chuyển hóa của protein."
                    ),
                    "source": "https://trusted.test/urea",
                    "sources": ["https://trusted.test/urea"],
                    "score": 0.9,
                    "note_type": "high_note",
                }
            ]

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: FakeRetriever(),
    )

    result = await analyzer_node({"indicators": [urea], "patient_gender": "female"})
    explanation = result["indicators"][0]["explanation"]
    retrieved_text = " ".join(chunk["text"] for chunk in result["retrieved_contexts"])

    assert result["indicators"][0]["status"] == "high"
    assert "Giá trị Urea là 7.9 mmol/L" in explanation
    assert "cao so với khoảng tham chiếu được hệ thống sử dụng" in explanation
    assert "có thể do" not in structured_llm.prompt
    assert "có thể do" not in retrieved_text
    assert "Ure là sản phẩm chuyển hóa của protein" in retrieved_text
    assert MedicalSafetyValidator().validate(explanation) == []


@pytest.mark.asyncio
async def test_all_unsafe_retrieval_and_no_llm_use_safe_deterministic_urea_path(monkeypatch):
    class UnsafeOnlyRetriever:
        def retrieve(self, **_kwargs):
            return [
                {
                    "indicator_name": "Urea",
                    "text": "Ure máu tăng có thể do nhiều nguyên nhân.",
                    "source": "https://trusted.test/urea",
                    "sources": ["https://trusted.test/urea"],
                    "score": 0.9,
                    "note_type": "high_note",
                }
            ]

    monkeypatch.setattr(
        analyzer_module,
        "get_llm",
        lambda: (_ for _ in ()).throw(RuntimeError("no llm")),
    )
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: UnsafeOnlyRetriever(),
    )
    urea = {
        "name": "Urea",
        "analyte_id": "urea",
        "value": 7.9,
        "unit": "mmol/L",
        "status": "high",
        "is_abnormal": True,
        "is_critical": False,
        "explanation": "Ure máu tăng có thể do nhiều nguyên nhân.",
        "sources": ["https://trusted.test/urea"],
    }

    result = await analyzer_node({"indicators": [urea], "patient_gender": "female"})
    explanation = result["indicators"][0]["explanation"]

    assert result["retrieved_contexts"] == []
    assert "Giá trị Urea là 7.9 mmol/L" in explanation
    assert "có thể do" not in explanation
    assert MedicalSafetyValidator().validate(explanation) == []


@pytest.mark.asyncio
async def test_plt_risk_oriented_grounding_remains_available(monkeypatch):
    risk_text = "Số lượng tiểu cầu giảm có thể làm tăng nguy cơ xuất huyết."

    class EchoStructuredLLM:
        async def ainvoke(self, _messages):
            return ExplanationOutput(explanation=f"Giá trị PLT là 142 10^9/L. {risk_text}")

    class FakeLLM:
        def with_structured_output(self, _schema):
            return EchoStructuredLLM()

    class FakeRetriever:
        def retrieve(self, **_kwargs):
            return [
                {
                    "indicator_name": "PLT",
                    "text": risk_text,
                    "source": "https://trusted.test/plt",
                    "sources": ["https://trusted.test/plt"],
                    "score": 0.9,
                    "note_type": "low_note",
                }
            ]

    monkeypatch.setattr(analyzer_module, "get_llm", lambda: FakeLLM())
    monkeypatch.setattr(
        analyzer_module,
        "get_medical_knowledge_retriever",
        lambda: FakeRetriever(),
    )
    plt = {
        "name": "PLT",
        "analyte_id": "plt",
        "value": 142,
        "unit": "10^9/L",
        "status": "low",
        "is_abnormal": True,
        "is_critical": False,
        "explanation": "",
        "sources": ["https://trusted.test/plt"],
    }

    result = await analyzer_node({"indicators": [plt], "patient_gender": "female"})
    explanation = result["indicators"][0]["explanation"]

    assert risk_text in result["retrieved_contexts"][0]["text"]
    assert risk_text in explanation
    assert MedicalSafetyValidator().validate(explanation) == []
