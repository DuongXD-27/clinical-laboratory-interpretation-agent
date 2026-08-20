from __future__ import annotations

import logging
import re
import textwrap
import unicodedata
from collections.abc import Sequence

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataPayload,
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    NeedsInputPayload,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
    SuggestedAction,
)
from src.services.llm import get_llm
from src.services.medical_safety_validator import MedicalSafetyValidator

logger = logging.getLogger(__name__)


class ComposedMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=600)


_ACTION_ADAPTER = TypeAdapter(SuggestedAction)


def deterministic_message_for(status: ResponseStatus, reason_code: ReasonCode | None, intent: IntentEnum) -> str:
    if reason_code == ReasonCode.UNSUPPORTED_ANALYTE:
        return "Chỉ số này chưa nằm trong phạm vi hỗ trợ an toàn của hệ thống."
    if reason_code == ReasonCode.UNSUPPORTED_CAPABILITY:
        return "Chức năng này chưa được hỗ trợ cho phiên hiện tại."
    if reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED:
        return "Không tìm thấy phiếu phù hợp trong phạm vi được phép."
    if reason_code == ReasonCode.TREND_INSUFFICIENT_POINTS:
        return "Chưa đủ dữ liệu để tạo xu hướng cho chỉ số này."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.VIEW_HISTORY:
        return "Đây là phiếu xét nghiệm gần nhất trong lịch sử của bạn."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.ANALYZE_TREND:
        return "Đây là xu hướng của chỉ số đã chọn."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.GET_DOCTOR_QUESTIONS:
        return "Đây là các câu hỏi gợi ý để trao đổi với bác sĩ."
    if status == ResponseStatus.SUCCESS and intent == IntentEnum.EXPLAIN_CURRENT_RESULT:
        return "Đây là phần giải thích đã được tạo cho chỉ số hiện tại."
    if status == ResponseStatus.SUCCESS:
        return "Đây là kết quả phân tích hiện có."
    return "Tôi cần thêm thông tin để tiếp tục an toàn."


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _deduplicate(values: Sequence[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _sources_from_data(data: DataPayload) -> list[str]:
    if isinstance(data, ExplanationDataPayload):
        return _deduplicate(data.sources)
    if isinstance(data, AnalysisDataPayload):
        sources: list[str] = []
        for indicator in data.indicators:
            sources.extend(indicator.sources)
        return _deduplicate(sources)
    return []


def _payload_summary(data: DataPayload) -> str:
    if isinstance(data, AnalysisDataPayload):
        statuses = [str(indicator.status) for indicator in data.indicators[:5]]
        return (
            f"Payload: analysis. Indicator count: {len(data.indicators)}. "
            f"Statuses: {', '.join(statuses)}. Has critical values: {data.has_critical_values}."
        )
    if isinstance(data, ExplanationDataPayload):
        return f"Payload: explanation. Approved explanation: {data.explanation[:800]}"
    if data.data_type == DataType.HISTORY_SUMMARY:
        return "Payload: history summary. Report summary is available to the user."
    if data.data_type == DataType.TREND:
        return "Payload: trend. Deterministic trend data is available to the user."
    if data.data_type == DataType.DOCTOR_QUESTIONS:
        return "Payload: doctor questions. Server-generated questions are available."
    if isinstance(data, NeedsInputPayload):
        return f"Payload: needs input. Missing fields: {', '.join(data.missing_fields)}."
    if isinstance(data, BlockedPayload):
        return f"Payload: blocked. Reason: {data.reason_code}."
    return f"Payload: {data.data_type}."


def _composer_prompt(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    reason_code: ReasonCode | None,
    data: DataPayload,
    fallback_message: str,
) -> str:
    return textwrap.dedent(
        f"""\
        You write one short patient-facing message in Vietnamese.

        You may rewrite or summarize approved canonical information only.
        You may not recalculate medical status, reinterpret reference ranges,
        create diagnoses, infer causes, recommend treatment, invent facts,
        invent sources, invent actions, or change server fields.

        Server-controlled fields:
        intent={intent.value}
        status={status.value}
        reason_code={reason_code.value if reason_code else "none"}

        Canonical bounded context:
        {_payload_summary(data)}

        Deterministic fallback message:
        {fallback_message}

        Return only the message field.
        """
    )


async def compose_message(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    reason_code: ReasonCode | None,
    data: DataPayload,
    fallback_message: str,
) -> str:
    if status != ResponseStatus.SUCCESS:
        return fallback_message
    prompt = _composer_prompt(
        intent=intent,
        status=status,
        reason_code=reason_code,
        data=data,
        fallback_message=fallback_message,
    )
    try:
        structured_llm = get_llm().with_structured_output(ComposedMessage)
        raw = await structured_llm.ainvoke([HumanMessage(content=prompt)])
        composed = raw if isinstance(raw, ComposedMessage) else ComposedMessage.model_validate(raw)
    except Exception as exc:
        logger.info("Response composer unavailable; using deterministic fallback: %s", exc)
        return fallback_message
    return composed.message.strip() or fallback_message


def _canonical_statuses(data: DataPayload) -> list[str]:
    if not isinstance(data, AnalysisDataPayload):
        return []
    return [str(indicator.status).casefold() for indicator in data.indicators]


def _message_contradicts_canonical_data(message: str, data: DataPayload) -> bool:
    normalized = _normalize(message)
    if not normalized:
        return False
    for status in _canonical_statuses(data):
        if status in {"high", "low", "critical_high", "critical_low", "unknown"} and (
            "binh thuong" in normalized or "normal" in normalized
        ):
            return True
        if status == "normal" and any(term in normalized for term in ("nguy kich", "critical", "cao", "thap")):
            return True
    return False


def _guardrail_blocked_response(intent: IntentEnum, message: str = "Nội dung phản hồi không vượt qua kiểm duyệt an toàn.") -> OrchestratorResponse:
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.BLOCKED,
        message=message,
        data_type=DataType.BLOCKED,
        data=BlockedPayload(
            safety_notice=message,
            disclaimer="Thông tin này chỉ mang tính giáo dục và không thay thế tư vấn y khoa.",
            reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        ),
        reason_code=ReasonCode.GUARDRAIL_BLOCKED,
        suggested_actions=[],
        sources=[],
        safety_notice=message,
    )


def _validate_actions(actions: Sequence[object]) -> list[SuggestedAction]:
    return [_ACTION_ADAPTER.validate_python(action) for action in actions]


def enforce_final_response(response: OrchestratorResponse) -> OrchestratorResponse:
    try:
        validated = OrchestratorResponse.model_validate(response.model_dump())
    except Exception:
        return _guardrail_blocked_response(response.intent)

    validator = MedicalSafetyValidator()
    if validator.validate(validated.message):
        return _guardrail_blocked_response(validated.intent)
    if _message_contradicts_canonical_data(validated.message, validated.data):
        return _guardrail_blocked_response(validated.intent)
    return validated


async def build_final_response(
    *,
    intent: IntentEnum,
    status: ResponseStatus,
    data: DataPayload,
    reason_code: ReasonCode | None = None,
    suggested_actions: Sequence[object] = (),
) -> OrchestratorResponse:
    fallback_message = deterministic_message_for(status, reason_code, intent)
    message = await compose_message(
        intent=intent,
        status=status,
        reason_code=reason_code,
        data=data,
        fallback_message=fallback_message,
    )
    try:
        actions = _validate_actions(suggested_actions)
    except Exception:
        return _guardrail_blocked_response(intent)
    response = OrchestratorResponse(
        intent=intent,
        status=status,
        message=message,
        data_type=data.data_type,
        data=data,
        reason_code=reason_code,
        suggested_actions=actions,
        sources=_sources_from_data(data),
        safety_notice=data.safety_notice if isinstance(data, BlockedPayload) else None,
    )
    return enforce_final_response(response)


__all__ = [
    "ComposedMessage",
    "build_final_response",
    "compose_message",
    "deterministic_message_for",
    "enforce_final_response",
]
