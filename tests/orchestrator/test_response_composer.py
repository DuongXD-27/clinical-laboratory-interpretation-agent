from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataType,
    ExplanationDataPayload,
    HistorySummaryPayload,
    IntentEnum,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
)
from src.models.schemas import IndicatorResultSchema
from src.orchestrator import response_composer
from src.orchestrator.response_composer import build_final_response


class FakeLLM:
    def __init__(self, output):
        self.output = output
        self.prompts: list[str] = []

    def with_structured_output(self, schema):
        self.schema = schema
        return self

    async def ainvoke(self, messages):
        self.prompts.append(messages[0].content)
        return self.output


def _history_payload() -> HistorySummaryPayload:
    return HistorySummaryPayload(
        report_ref="report-1",
        test_date="2026-08-20",
        summary="summary",
        status="NORMAL",
        has_critical_values=False,
        result_count=1,
    )


def _high_analysis_payload() -> AnalysisDataPayload:
    return AnalysisDataPayload(
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=15.0,
                unit="10^9/L",
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation="Giá trị này cao so với khoảng tham chiếu.",
                sources=["https://trusted.test/wbc"],
            )
        ]
    )


@pytest.mark.asyncio
async def test_r1_composer_rejects_extra_model_fields_and_uses_fallback(monkeypatch):
    fake = FakeLLM({"message": "Tin nhắn từ model", "status": "blocked"})
    monkeypatch.setattr(response_composer, "get_llm", lambda: fake)

    response = await build_final_response(
        intent=IntentEnum.VIEW_HISTORY,
        status=ResponseStatus.SUCCESS,
        data=_history_payload(),
    )

    assert response.message == "Đây là phiếu xét nghiệm gần nhất trong lịch sử của bạn."
    assert response.status == ResponseStatus.SUCCESS
    assert fake.prompts


@pytest.mark.asyncio
async def test_r2_llm_message_cannot_mutate_server_fields_sources_or_actions(monkeypatch):
    fake = FakeLLM(
        response_composer.ComposedMessage(
            message="Có thể xem phần giải thích đã duyệt tại https://invented.test",
        )
    )
    monkeypatch.setattr(response_composer, "get_llm", lambda: fake)
    payload = ExplanationDataPayload(
        explanation="Nội dung giải thích đã được hệ thống duyệt.",
        sources=["https://trusted.test/source"],
    )

    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=payload,
    )

    assert response.status == ResponseStatus.SUCCESS
    assert response.reason_code is None
    assert response.data == payload
    assert response.sources == ["https://trusted.test/source"]
    assert "invented.test" not in response.sources
    assert response.suggested_actions == []


@pytest.mark.asyncio
async def test_r3_canonical_status_contradiction_fails_closed():
    response = OrchestratorResponse(
        intent=IntentEnum.ANALYZE_REPORT,
        status=ResponseStatus.SUCCESS,
        message="Kết quả này bình thường.",
        data_type=DataType.ANALYSIS,
        data=_high_analysis_payload(),
    )
    safe = response_composer.enforce_final_response(response)

    assert safe.status == ResponseStatus.BLOCKED
    assert safe.reason_code == ReasonCode.GUARDRAIL_BLOCKED
    assert safe.data_type == DataType.BLOCKED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "unsafe_message",
    [
        "Bạn mắc bệnh gout.",
        "Tình trạng này có thể do bệnh thận.",
        "Bạn nên uống thuốc hạ acid uric.",
    ],
)
async def test_r4_r5_r6_unsafe_medical_message_fails_closed(monkeypatch, unsafe_message):
    fake = FakeLLM(response_composer.ComposedMessage(message=unsafe_message))
    monkeypatch.setattr(response_composer, "get_llm", lambda: fake)

    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=ExplanationDataPayload(explanation="Giải thích đã duyệt."),
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.GUARDRAIL_BLOCKED
    assert unsafe_message not in response.message


@pytest.mark.asyncio
async def test_invalid_suggested_action_fails_closed_before_final_response():
    response = await build_final_response(
        intent=IntentEnum.VIEW_HISTORY,
        status=ResponseStatus.SUCCESS,
        data=_history_payload(),
        suggested_actions=[{"action": "OPEN_URL", "url": "javascript:alert(1)"}],
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.GUARDRAIL_BLOCKED


@pytest.mark.asyncio
async def test_composer_llm_unavailable_uses_deterministic_typed_fallback(monkeypatch):
    monkeypatch.setattr(response_composer, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))

    response = await build_final_response(
        intent=IntentEnum.VIEW_HISTORY,
        status=ResponseStatus.SUCCESS,
        data=_history_payload(),
    )

    assert response.message == "Đây là phiếu xét nghiệm gần nhất trong lịch sử của bạn."
    assert OrchestratorResponse.model_validate(response.model_dump()) == response


@pytest.mark.asyncio
async def test_explanation_fallback_preserves_approved_explanation(monkeypatch):
    monkeypatch.setattr(response_composer, "get_llm", lambda: (_ for _ in ()).throw(RuntimeError("no llm")))
    payload = ExplanationDataPayload(
        explanation="Bạch cầu tăng nhẹ so với khoảng tham chiếu.",
        sources=["HD-BYT"],
    )

    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        data=payload,
    )

    assert response.message == payload.explanation
    assert response.sources == ["HD-BYT"]


@pytest.mark.asyncio
async def test_guardrail_blocked_result_does_not_call_response_composer(monkeypatch):
    calls = 0

    def counted_llm():
        nonlocal calls
        calls += 1
        return SimpleNamespace()

    monkeypatch.setattr(response_composer, "get_llm", counted_llm)

    response = await build_final_response(
        intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
        status=ResponseStatus.BLOCKED,
        reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        data=BlockedPayload(
            safety_notice="Nội dung đã bị chặn.",
            reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        ),
    )

    assert calls == 0
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.GUARDRAIL_BLOCKED


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reason_code",
    [ReasonCode.UNSUPPORTED_ANALYTE, ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED],
)
async def test_fail_closed_blocked_results_do_not_enter_composer(monkeypatch, reason_code):
    calls = 0

    def counted_llm():
        nonlocal calls
        calls += 1
        return SimpleNamespace()

    monkeypatch.setattr(response_composer, "get_llm", counted_llm)

    response = await build_final_response(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.BLOCKED,
        reason_code=reason_code,
        data=BlockedPayload(
            safety_notice="Yêu cầu bị chặn trước khi tạo phản hồi.",
            reason_code=reason_code,
        ),
    )

    assert calls == 0
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == reason_code


def test_needs_input_human_friendly_mapping():
    from src.orchestrator.response_composer import map_needs_input_prompt

    missing_fields = ["current_report_ref", "current_analyte"]
    fallback = "Tôi cần thêm thông tin để tiếp tục an toàn."

    mapped = map_needs_input_prompt(missing_fields, fallback)

    assert "current_report_ref" not in mapped
    assert "current_analyte" not in mapped
    assert "Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn" in mapped
    assert "Bạn có thể gửi ảnh phiếu xét nghiệm" in mapped


def test_safety_refusal_wording():
    from src.orchestrator.response_composer import _safety_refusal_message

    msg_diag = _safety_refusal_message(ReasonCode.MEDICAL_DIAGNOSIS_REQUEST)
    assert "không thể đưa ra chẩn đoán bệnh" in msg_diag
    assert "bác sĩ" in msg_diag
    assert "MEDICAL_DIAGNOSIS_REQUEST" not in msg_diag
    assert "UNSUPPORTED_OR_UNSAFE" not in msg_diag

    msg_cause = _safety_refusal_message(ReasonCode.MEDICAL_CAUSE_REQUEST)
    assert "không thể xác định nguyên nhân cá nhân" in msg_cause
    assert "MEDICAL_CAUSE_REQUEST" not in msg_cause

    msg_treat = _safety_refusal_message(ReasonCode.TREATMENT_REQUEST)
    assert "không thể hướng dẫn phương pháp điều trị" in msg_treat
    assert "TREATMENT_REQUEST" not in msg_treat
