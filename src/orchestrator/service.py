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
    DataType,
    HistorySummaryPayload,
    IntentEnum,
    NeedsInputPayload,
    OrchestratorRequest,
    OrchestratorResponse,
    ProgressStage,
    ReasonCode,
    ResponseStatus,
    RetryAction,
    TrendDataPayload,
)
from src.orchestrator.context_resolver import resolve_context
from src.orchestrator.dispatcher import DispatchContext, WorkflowResult, dispatch_workflow
from src.orchestrator.gates import medical_safety_gate, onboarding_gate, policy_gate, role_admission_gate
from src.orchestrator.intent_router import RouteDecision, contains_lab_value, route_intent
from src.orchestrator.progress import ProgressCallback, emit_progress
from src.orchestrator.response_composer import _safety_refusal_message, build_final_response, map_needs_input_prompt
from src.orchestrator.session_store import SessionStore, default_session_store
from src.services.ocr_review_gate import get_current_review_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OrchestratorRuntime:
    session_store: SessionStore = field(default_factory=lambda: default_session_store)


def _session_hash(session_id: str) -> str:
    return hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:16]


def _blocked_response(intent: IntentEnum, reason_code: ReasonCode, message: str) -> OrchestratorResponse:
    action = (
        [ConfirmOcrAction(review_ref="ocr-review")]
        if reason_code == ReasonCode.OCR_REVIEW_REQUIRED
        else []
    )
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


def _needs_input_response(intent: IntentEnum, reason_code: ReasonCode, message: str, missing: list[str]) -> OrchestratorResponse:
    friendly_message = map_needs_input_prompt(missing, message)
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.NEEDS_INPUT,
        message=friendly_message,
        data_type=DataType.NEEDS_INPUT,
        data=NeedsInputPayload(prompt=friendly_message, missing_fields=missing),
        reason_code=reason_code,
        suggested_actions=[RetryAction(reason_code=reason_code)],
    )


async def _response_from_workflow(
    intent: IntentEnum,
    result: WorkflowResult,
    *,
    progress_callback: ProgressCallback | None = None,
) -> OrchestratorResponse:
    await emit_progress(progress_callback, ProgressStage.RESPONSE_COMPOSITION)
    return await build_final_response(
        intent=intent,
        status=result.status,
        data=result.data,
        reason_code=result.reason_code,
    )


def _context_after_workflow(
    *,
    result: WorkflowResult,
    current_report_ref: str | None,
    current_analyte: str | None,
) -> tuple[str | None, str | None]:
    data = result.data
    next_report_ref = current_report_ref
    next_analyte = current_analyte

    if result.status == ResponseStatus.SUCCESS and isinstance(data, HistorySummaryPayload):
        next_report_ref = data.report_ref
    if result.status == ResponseStatus.SUCCESS and isinstance(data, TrendDataPayload):
        next_analyte = data.trend.analyte_canonical
    if result.status == ResponseStatus.SUCCESS and result.workflow_selected == "get_my_report_summary":
        next_analyte = None

    return next_report_ref, next_analyte


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


def _looks_like_gibberish(message: str) -> bool:
    from src.orchestrator.medical_context import extract_explicit_analyte
    if extract_explicit_analyte(message) is not None or contains_lab_value(message):
        return False
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]+", message)
    return bool(message.strip()) and len(tokens) <= 2 and not any(ch.isspace() for ch in message.strip())


def _log_turn(
    *,
    request_id: str,
    session_id: str,
    role: str,
    route: RouteDecision | None,
    workflow_selected: str,
    failure_code: ReasonCode | None,
    started_at: float,
) -> None:
    logger.info(
        "orchestrator_turn",
        extra={
            "request_id": request_id,
            "session_id_hash": _session_hash(session_id),
            "role": role,
            "intent": route.intent.value if route is not None else None,
            "route_confidence": route.route_confidence if route is not None else None,
            "workflow_selected": workflow_selected,
            "workflow_outcome": "blocked" if failure_code else "completed",
            "failure_code": failure_code.value if failure_code is not None else None,
            "guardrail_triggered": False,
            "authorization_outcome": "denied" if failure_code == ReasonCode.UNSUPPORTED_CAPABILITY else "allowed",
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
) -> OrchestratorResponse:
    runtime = runtime or OrchestratorRuntime()
    started_at = time.perf_counter()
    request_id = uuid.uuid4().hex
    role = str(getattr(current_user, "role", ""))

    reason = role_admission_gate(current_user)
    if reason is not None:
        return _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vai trò này chưa được hỗ trợ trong Orchestrator V1.")

    try:
        session = runtime.session_store.get_or_create(current_user)
    except ValueError:
        return _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, ReasonCode.AUTH_EXPIRED, "Phiên đăng nhập không hợp lệ.")

    route: RouteDecision | None = None

    reason = onboarding_gate(session)
    if reason is not None:
        response = _blocked_response(IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vui lòng xác nhận hướng dẫn sử dụng trước.")
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=reason,
            started_at=started_at,
        )
        return response

    # 1. Medical safety gate
    safety_reason = medical_safety_gate(request.message)
    if safety_reason is not None:
        route = RouteDecision(intent=IntentEnum.UNSUPPORTED_OR_UNSAFE, reason_code=safety_reason, route_confidence=1.0)
        response = _blocked_response(route.intent, route.reason_code, _safety_refusal_message(route.reason_code))
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
            started_at=started_at,
        )
        return response

    active_pending = session.conversation_state.get_active_pending_question()
    if not active_pending and _looks_like_gibberish(request.message):
        return _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE,
            ReasonCode.UNKNOWN_INTENT,
            "Tôi chưa hiểu yêu cầu này. Vui lòng diễn đạt lại.",
        )

    if _is_ocr_bypass_request(request.message):
        route = RouteDecision(intent=IntentEnum.ANALYZE_REPORT, reason_code=ReasonCode.OCR_REVIEW_REQUIRED, route_confidence=1.0)
        response = _blocked_response(
            route.intent,
            route.reason_code,
            "Bạn cần xác nhận OCR trước khi phân tích phiếu từ ảnh.",
        )
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
            started_at=started_at,
        )
        return response

    # 2. Intent router
    from src.models.db import ROLE_PATIENT

    has_medical_context = (
        session.current_report_ref is not None
        or session.current_analyte is not None
        or (role == ROLE_PATIENT)
    )
    await emit_progress(progress_callback, ProgressStage.ROUTING)
    route = await route_intent(request.message, session, role, has_medical_context=has_medical_context)
    if route.reason_code == ReasonCode.UNKNOWN_INTENT:
        response = _needs_input_response(
            route.intent,
            ReasonCode.UNKNOWN_INTENT,
            "Tôi chưa chắc bạn muốn làm gì. Tôi có thể giúp bạn xem kết quả xét nghiệm, xem xu hướng hoặc chuẩn bị câu hỏi cho bác sĩ.",
            []
        )
        from src.models.orchestrator_schemas import ConversationState
        runtime.session_store.update_after_turn(
            current_user,
            session,
            last_intent=route.intent,
            conversation_state=ConversationState(
                pending_question=response.message,
                pending_question_timestamp=time.time(),
            )
        )
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.UNKNOWN_INTENT,
            started_at=started_at,
        )
        return response
        
    # 3. Medical context resolver (Autonomous context retrieval)
    from src.orchestrator.medical_context import resolve_medical_context
    await emit_progress(progress_callback, ProgressStage.MEDICAL_CONTEXT)
    resolved = resolve_medical_context(
        message=request.message,
        session=session,
        ui_context=request.ui_context,
        current_user=current_user,
        db=db,
        intent=route.intent,
    )
    if resolved.reason_code == ReasonCode.AMBIGUOUS_CONTEXT:
        response = _needs_input_response(
            route.intent,
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Bạn muốn nói đến chỉ số nào?",
            ["current_analyte"],
        )
        from src.models.orchestrator_schemas import ConversationState
        runtime.session_store.update_after_turn(
            current_user,
            session,
            last_intent=route.intent,
            current_report_ref=resolved.current_report_ref,
            conversation_state=ConversationState(
                pending_question=response.message,
                pending_question_timestamp=time.time(),
            ),
        )
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.AMBIGUOUS_CONTEXT,
            started_at=started_at,
        )
        return response
    if resolved.forced_intent:
        route = RouteDecision(intent=resolved.forced_intent, route_confidence=1.0)

    if route.reason_code in {
        ReasonCode.MEDICAL_DIAGNOSIS_REQUEST,
        ReasonCode.MEDICAL_CAUSE_REQUEST,
        ReasonCode.TREATMENT_REQUEST,
    }:
        response = _blocked_response(route.intent, route.reason_code, _safety_refusal_message(route.reason_code))
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
            started_at=started_at,
        )
        return response

    reason = policy_gate(role, route.intent)
    if reason is not None:
        response = _blocked_response(route.intent, reason, "Chức năng này chưa được hỗ trợ cho phiên hiện tại.")
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected="",
            failure_code=reason,
            started_at=started_at,
        )
        return response

    result = await dispatch_workflow(
        route.intent,
        DispatchContext(
            current_user=current_user,
            db=db,
            current_report_ref=resolved.current_report_ref,
            current_analyte=resolved.current_analyte,
            progress_callback=progress_callback,
        ),
    )
    next_report_ref, next_analyte = _context_after_workflow(
        result=result,
        current_report_ref=resolved.current_report_ref,
        current_analyte=resolved.current_analyte,
    )
    final_response = await _response_from_workflow(
        route.intent,
        result,
        progress_callback=progress_callback,
    )
    
    # Save conversation state with active timestamp
    from src.models.orchestrator_schemas import ConversationState
    new_state = ConversationState(
        pending_question=final_response.message if final_response.status == ResponseStatus.NEEDS_INPUT else None,
        pending_question_timestamp=time.time() if final_response.status == ResponseStatus.NEEDS_INPUT else None,
    )

    clear_analyte = (
        result.status == ResponseStatus.SUCCESS
        and result.workflow_selected == "get_my_report_summary"
    )

    runtime.session_store.update_after_turn(
        current_user,
        session,
        last_intent=route.intent,
        current_report_ref=next_report_ref,
        current_analyte=next_analyte,
        transient_ui_context=request.ui_context,
        conversation_state=new_state,
        clear_analyte=clear_analyte,
    )
    _log_turn(
        request_id=request_id,
        session_id=session.session_id,
        role=role,
        route=route,
        workflow_selected=result.workflow_selected,
        failure_code=result.reason_code,
        started_at=started_at,
    )
    return final_response


def acknowledge_onboarding(current_user: object, *, runtime: OrchestratorRuntime | None = None) -> OrchestratorResponse:
    runtime = runtime or OrchestratorRuntime()
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
