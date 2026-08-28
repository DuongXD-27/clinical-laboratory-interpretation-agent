from __future__ import annotations

import hashlib
import logging
import re
import time
import uuid
from dataclasses import dataclass, field

from src.models.orchestrator_schemas import (
    BlockedPayload,
    ConfirmOcrAction,
    ConversationState,
    DataType,
    IntentEnum,
    NeedsInputPayload,
    OpenReportAction,
    OrchestratorRequest,
    OrchestratorResponse,
    ProgressStage,
    ReasonCode,
    ResponseStatus,
    RetryAction,
)
from src.orchestrator.gates import (
    contains_lab_value,
    emergency_safety_gate,
    medical_safety_gate,
    onboarding_gate,
    role_admission_gate,
    treatment_followup_gate,
)
from src.orchestrator.progress import ProgressCallback, emit_progress
from src.orchestrator.session_store import (
    SessionStore,
    bind_conversation,
    current_binding,
    default_session_store,
)
from src.services import conversation_repository
from src.services.request_timing import get_current_timing

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorRuntime:
    session_store: SessionStore = field(default_factory=lambda: default_session_store)


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]


def _blocked_response(intent: IntentEnum, reason_code: ReasonCode, message: str) -> OrchestratorResponse:
    action = [ConfirmOcrAction(review_ref="ocr-review")] if reason_code == ReasonCode.OCR_REVIEW_REQUIRED else []
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.BLOCKED,
        message=message,
        data_type=DataType.BLOCKED,
        data=BlockedPayload(
            safety_notice=message,
            disclaimer="Thông tin này chỉ mang tính giáo dục và không thay thế tư vấn y khoa.",
            reason_code=reason_code,
        ),
        reason_code=reason_code,
        suggested_actions=action,
        safety_notice=message,
    )


def _is_ocr_bypass_request(message: str) -> bool:
    lowered = message.casefold()
    patterns = (
        "skip confirm",
        "skip confirmation",
        "continue without review",
        "analyze now",
        "bỏ qua confirm",
        "bo qua confirm",
        "bỏ qua xác nhận",
        "bo qua xac nhan",
        "không cần xác nhận",
        "khong can xac nhan",
        "cứ phân tích",
        "cu phan tich",
    )
    return any(pattern in lowered for pattern in patterns)


UNCLEAR_INPUT_MESSAGE = "Tôi chưa hiểu yêu cầu của bạn. Bạn vui lòng nhập lại hoặc mô tả rõ hơn điều bạn muốn hỏi."

OUT_OF_SCOPE_MESSAGE = (
    "Tôi được thiết kế để hỗ trợ bạn về kết quả xét nghiệm và các chức năng liên quan trong VMEC. "
    "Tôi chưa thể hỗ trợ yêu cầu này. "
    "Bạn có thể hỏi tôi về phiếu xét nghiệm, một chỉ số cụ thể, lịch sử hoặc xu hướng xét nghiệm."
)

SENSITIVE_SYSTEM_MESSAGE = (
    "Tôi không thể cung cấp khóa API, thông tin đăng nhập, prompt hệ thống hoặc thông tin nội bộ của VMEC. "
    "Tôi có thể hỗ trợ bạn về kết quả xét nghiệm và các chức năng được phép trong ứng dụng."
)

_DEGRADED_MESSAGE = (
    "Trợ lý đang tạm thời không thể xử lý câu hỏi này. "
    "Bạn có thể thử lại sau ít phút hoặc quay lại phiếu xét nghiệm hiện tại."
)


def _safety_refusal_message(reason_code: ReasonCode | None) -> str:
    if reason_code == ReasonCode.EMERGENCY_INPUT_SAFETY:
        return (
            "Nếu bạn đang gặp các triệu chứng cấp cứu hoặc khó chịu nghiêm trọng (như khó thở, đau tức ngực dữ dội), "
            "bạn không nên chờ đợi phản hồi từ trợ lý ảo. "
            "Vui lòng liên hệ ngay cơ sở y tế gần nhất hoặc dịch vụ cấp cứu y tế tại địa phương để được hỗ trợ và xử trí kịp thời."
        )
    if reason_code == ReasonCode.MEDICAL_DIAGNOSIS_REQUEST:
        return (
            "Mình không thể đưa ra chẩn đoán bệnh hoặc khẳng định tình trạng bệnh lý của bạn. "
            "Bạn nên trao đổi trực tiếp với bác sĩ chuyên khoa để được thăm khám chính xác. "
            "Mình có thể hỗ trợ giải thích ý nghĩa các chỉ số xét nghiệm hoặc gợi ý câu hỏi để bạn trao đổi cùng bác sĩ."
        )
    if reason_code == ReasonCode.MEDICAL_CAUSE_REQUEST:
        return (
            "Mình không thể xác định nguyên nhân cá nhân dẫn đến kết quả này. "
            "Để hiểu rõ nguyên nhân, bác sĩ cần thăm khám kết hợp với các triệu chứng lâm sàng và tiền sử bệnh của bạn. "
            "Mình có thể hỗ trợ giải thích ý nghĩa tổng quan của chỉ số hoặc gợi ý câu hỏi cho bác sĩ."
        )
    if reason_code == ReasonCode.TREATMENT_REQUEST:
        return (
            "Mình không thể hướng dẫn phương pháp điều trị hay tư vấn sử dụng thuốc. "
            "Bạn nên tham khảo ý kiến bác sĩ để có kế hoạch chăm sóc và điều trị phù hợp và an toàn nhất."
        )
    if reason_code == ReasonCode.PERSONAL_MEDICAL_ADVICE:
        return (
            "Mình không thể đưa ra tư vấn về chế độ ăn uống, thực phẩm bổ sung, hoặc điều trị cá nhân hóa. "
            "Bạn nên tham khảo ý kiến bác sĩ hoặc chuyên gia dinh dưỡng để có chế độ phù hợp với tình trạng sức khỏe của bạn. "
            "Mình có thể hỗ trợ giải thích ý nghĩa các chỉ số xét nghiệm hoặc gợi ý câu hỏi để bạn trao đổi cùng bác sĩ."
        )
    return "Tôi không thể hỗ trợ yêu cầu này an toàn."


def _degraded_response(current_report_ref: str | None, message: str) -> OrchestratorResponse:
    from src.orchestrator.agent import _intent_hint

    actions: list[RetryAction | OpenReportAction] = [RetryAction(reason_code=ReasonCode.LLM_UNAVAILABLE)]
    if current_report_ref:
        actions.append(OpenReportAction(report_ref=current_report_ref))
    return OrchestratorResponse(
        intent=_intent_hint(message) or IntentEnum.UNSUPPORTED_OR_UNSAFE,
        status=ResponseStatus.ERROR,
        message=_DEGRADED_MESSAGE,
        data_type=DataType.BLOCKED,
        data=BlockedPayload(
            safety_notice=_DEGRADED_MESSAGE,
            disclaimer="Thông tin này chỉ mang tính giáo dục và không thay thế tư vấn y khoa.",
            reason_code=ReasonCode.LLM_UNAVAILABLE,
        ),
        reason_code=ReasonCode.LLM_UNAVAILABLE,
        suggested_actions=actions,
        sources=[],
        safety_notice=_DEGRADED_MESSAGE,
    )


def _ambiguous_analyte_response() -> OrchestratorResponse:
    message = "Bạn đang hỏi về chỉ số nào? Vui lòng cho biết tên chỉ số, ví dụ WBC hoặc HbA1c."
    return OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.NEEDS_INPUT,
        message=message,
        data_type=DataType.NEEDS_INPUT,
        data=NeedsInputPayload(prompt=message, missing_fields=["analyte"]),
        reason_code=ReasonCode.AMBIGUOUS_CONTEXT,
        sources=[],
        safety_notice=None,
    )


def _is_unclear_input(message: str) -> bool:
    from src.orchestrator.message_context import (
        _is_referential_analyte,
        _normalize_no_accents,
        extract_explicit_analyte,
        extract_explicit_report_date,
        extract_explicit_report_ref,
    )

    raw = message.strip()
    if not raw:
        return True
    if emergency_safety_gate(message) is not None or medical_safety_gate(message) is not None:
        return False
    if extract_explicit_analyte(message) is not None or contains_lab_value(message) or _is_ocr_bypass_request(message):
        return False
    if extract_explicit_report_ref(message) is not None or extract_explicit_report_date(message) is not None:
        return False

    normalized = _normalize_no_accents(message)
    if _is_referential_analyte(normalized):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]+", message)
    if not tokens or (all(token.isdigit() for token in tokens) and len(tokens) >= 2):
        return True

    lower_tokens = [token.lower() for token in tokens]
    if len(lower_tokens) >= 2 and len(set(lower_tokens)) == 1:
        return True
    vowels = set("aeiouyáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ")
    for token in lower_tokens:
        if not token.isdigit() and len(token) >= 3 and not any(character in vowels for character in token):
            return True
        if token in {"asdf", "asdfg", "asdfgh", "qwerty", "zxcv", "zxcvb", "qwer", "hjkl"}:
            return True
    if len(lower_tokens) <= 2:
        if all(
            token in {"abc", "xyz", "qwe", "asd", "zxc", "123", "456", "789", "bla", "blah", "test"}
            for token in lower_tokens
        ):
            return True
        if normalized in {"o kia", "noi gi do", "abc xyz", "123 abc", "blah blah", "test test"}:
            return True
    return False


_looks_like_gibberish = _is_unclear_input


def _log_turn(
    *,
    request_id: str,
    session_id: str,
    role: str,
    intent: IntentEnum | None,
    workflow_selected: str,
    failure_code: ReasonCode | None,
    started_at: float,
    guardrail_triggered: bool = False,
) -> None:
    logger.info(
        "orchestrator_turn",
        extra={
            "request_id": request_id,
            "session_id_hash": _session_hash(session_id),
            "role": role,
            "intent": intent.value if intent is not None else None,
            "route_confidence": 1.0 if intent is not None else None,
            "workflow_selected": workflow_selected,
            "workflow_outcome": "blocked" if failure_code else "completed",
            "failure_code": failure_code.value if failure_code is not None else None,
            "guardrail_triggered": guardrail_triggered,
            "authorization_outcome": "denied" if failure_code == ReasonCode.UNSUPPORTED_CAPABILITY else "allowed",
            "chat_engine": "agent",
            "fallback_reason": "provider_failure" if failure_code == ReasonCode.LLM_UNAVAILABLE else None,
            "latency_ms": round((time.perf_counter() - started_at) * 1000, 1),
        },
    )


async def handle_message(
    request: OrchestratorRequest,
    *,
    current_user: object,
    db: object,
    runtime: OrchestratorRuntime | None = None,
    progress_callback: ProgressCallback | None = None,
    conversation: object | None = None,
) -> OrchestratorResponse:
    if conversation is None:
        return await _handle_message_core(
            request,
            current_user=current_user,
            db=db,
            runtime=runtime,
            progress_callback=progress_callback,
        )

    _persist_message(db, conversation=conversation, role=conversation_repository.ROLE_USER, content=request.message)
    with bind_conversation(db, conversation):
        response = await _handle_message_core(
            request,
            current_user=current_user,
            db=db,
            runtime=runtime,
            progress_callback=progress_callback,
        )
    _persist_message(
        db,
        conversation=conversation,
        role=conversation_repository.ROLE_ASSISTANT,
        content=response.message,
        intent=response.intent.value,
        reason_code=response.reason_code.value if response.reason_code else None,
        data_type=response.data_type.value,
    )
    return response


def _persist_message(
    db: object,
    *,
    conversation: object,
    role: str,
    content: str,
    intent: str | None = None,
    reason_code: str | None = None,
    data_type: str | None = None,
) -> None:
    try:
        conversation_repository.append_message(
            db,
            conversation=conversation,
            role=role,
            content=content,
            intent=intent,
            reason_code=reason_code,
            data_type=data_type,
        )
    except Exception:
        logger.warning("conversation_message_persist_failed", exc_info=True)


def _immediately_previous_reason_code(db: object, current_user: object) -> ReasonCode | None:
    binding = current_binding()
    patient_id = getattr(current_user, "user_id", None)
    if binding is None or not isinstance(patient_id, int):
        return None
    _, conversation = binding
    conversation_id = getattr(conversation, "id", None)
    if not isinstance(conversation_id, int):
        return None
    rows = conversation_repository.list_messages(db, conversation_id=conversation_id, patient_id=patient_id)
    if not rows or len(rows) < 2:
        return None
    previous, current = rows[-2], rows[-1]
    if previous.role != conversation_repository.ROLE_ASSISTANT or current.role != conversation_repository.ROLE_USER:
        return None
    try:
        return ReasonCode(previous.reason_code) if previous.reason_code else None
    except ValueError:
        return None


async def _handle_message_core(
    request: OrchestratorRequest,
    *,
    current_user: object,
    db: object,
    runtime: OrchestratorRuntime | None = None,
    progress_callback: ProgressCallback | None = None,
) -> OrchestratorResponse:
    runtime = runtime or OrchestratorRuntime()
    started_at = time.perf_counter()
    timing = get_current_timing()
    request_id = timing.request_id if timing is not None else uuid.uuid4().hex
    role = str(getattr(current_user, "role", ""))

    reason = role_admission_gate(current_user)
    if reason is not None:
        return _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vai trò này chưa được hỗ trợ trong trợ lý.")
    try:
        session = runtime.session_store.get_or_create(current_user)
    except ValueError:
        return _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE, ReasonCode.AUTH_EXPIRED, "Phiên đăng nhập không hợp lệ."
        )

    def finish(
        response: OrchestratorResponse,
        *,
        workflow: str = "",
        intent: IntentEnum | None = None,
    ) -> OrchestratorResponse:
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            intent=intent or response.intent,
            workflow_selected=workflow,
            failure_code=response.reason_code,
            started_at=started_at,
            guardrail_triggered=response.reason_code == ReasonCode.GUARDRAIL_BLOCKED,
        )
        return response

    emergency_reason = emergency_safety_gate(request.message)
    if emergency_reason is not None:
        return finish(
            _blocked_response(
                IntentEnum.UNSUPPORTED_OR_UNSAFE, emergency_reason, _safety_refusal_message(emergency_reason)
            )
        )

    reason = onboarding_gate(session)
    if reason is not None:
        return finish(
            _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vui lòng xác nhận hướng dẫn sử dụng trước.")
        )

    safety_reason = medical_safety_gate(request.message)
    if safety_reason is not None:
        return finish(
            _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, safety_reason, _safety_refusal_message(safety_reason))
        )

    from src.orchestrator.gates import out_of_scope_gate, sensitive_system_gate

    sensitive_reason = sensitive_system_gate(request.message)
    if sensitive_reason is not None:
        return finish(_blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, sensitive_reason, SENSITIVE_SYSTEM_MESSAGE))

    if not session.conversation_state.get_active_pending_question() and _is_unclear_input(request.message):
        return finish(
            _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, ReasonCode.UNKNOWN_INTENT, UNCLEAR_INPUT_MESSAGE)
        )

    from src.orchestrator.message_context import (
        _is_referential_analyte,
        _normalize_no_accents,
        extract_explicit_analyte,
    )

    explicit_analyte = extract_explicit_analyte(request.message)
    if (
        explicit_analyte is None
        and session.current_analyte is None
        and _is_referential_analyte(_normalize_no_accents(request.message))
    ):
        return finish(_ambiguous_analyte_response(), workflow="clarify_analyte")

    out_of_scope_reason = out_of_scope_gate(request.message)
    if out_of_scope_reason is not None:
        return finish(_blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, out_of_scope_reason, OUT_OF_SCOPE_MESSAGE))

    followup_reason = treatment_followup_gate(
        request.message,
        session,
        prior_reason_code=_immediately_previous_reason_code(db, current_user),
    )
    if followup_reason is not None:
        return finish(
            _blocked_response(
                IntentEnum.UNSUPPORTED_OR_UNSAFE, followup_reason, _safety_refusal_message(followup_reason)
            )
        )

    if _is_ocr_bypass_request(request.message):
        return finish(
            _blocked_response(
                IntentEnum.ANALYZE_REPORT,
                ReasonCode.OCR_REVIEW_REQUIRED,
                "Bạn cần xác nhận OCR trước khi phân tích phiếu từ ảnh.",
            )
        )

    await emit_progress(progress_callback, ProgressStage.ROUTING)
    response_style = str(
        getattr(request.ui_context, "response_style", None)
        or getattr(current_user, "response_style", None)
        or getattr(session, "response_style", "simple")
    ).casefold()
    if response_style not in {"concise", "simple", "detailed"}:
        response_style = "simple"
    try:
        from src.orchestrator.agent import run_agent

        agent_result = await run_agent(
            message=request.message,
            current_user=current_user,
            db=db,
            current_report_ref=session.current_report_ref,
            current_analyte=explicit_analyte or session.current_analyte,
            response_style=response_style,
        )
    except Exception:
        logger.warning("Canonical Agent unavailable; returning deterministic degraded response", exc_info=True)
        return finish(_degraded_response(session.current_report_ref, request.message), workflow="provider_degraded")

    runtime.session_store.update_after_turn(
        current_user,
        session,
        last_intent=agent_result.response.intent,
        current_report_ref=agent_result.current_report_ref,
        current_analyte=agent_result.current_analyte,
        transient_ui_context=request.ui_context,
        conversation_state=ConversationState(),
    )
    await emit_progress(progress_callback, ProgressStage.RESPONSE_COMPOSITION)
    return finish(agent_result.response, workflow=agent_result.workflow_selected)


def acknowledge_onboarding(
    current_user: object,
    *,
    runtime: OrchestratorRuntime | None = None,
    db: object | None = None,
    conversation: object | None = None,
) -> OrchestratorResponse:
    runtime = runtime or OrchestratorRuntime()
    if conversation is None:
        runtime.session_store.acknowledge_onboarding(current_user)
    else:
        with bind_conversation(db, conversation):
            runtime.session_store.acknowledge_onboarding(current_user)
    return OrchestratorResponse(
        intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
        status=ResponseStatus.SUCCESS,
        message="Đã ghi nhận xác nhận hướng dẫn sử dụng.",
        data_type=DataType.NEEDS_INPUT,
        data=NeedsInputPayload(prompt="Bạn có thể tiếp tục.", missing_fields=[]),
        reason_code=None,
        sources=[],
        safety_notice=None,
    )


__all__ = [
    "OrchestratorRuntime",
    "acknowledge_onboarding",
    "handle_message",
]
