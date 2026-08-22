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
    ReasonCode,
    ResponseStatus,
    RetryAction,
    TrendDataPayload,
)
from src.orchestrator.context_resolver import resolve_context
from src.orchestrator.dispatcher import DispatchContext, WorkflowResult, dispatch_workflow
from src.orchestrator.gates import onboarding_gate, policy_gate, role_admission_gate
from src.orchestrator.intent_router import RouteDecision, contains_lab_value, route_intent
from src.orchestrator.response_composer import build_final_response
from src.orchestrator.session_store import SessionStore, default_session_store
from src.services.ocr_review_gate import get_current_review_state
from src.services.request_timing import get_current_timing

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
    return OrchestratorResponse(
        intent=intent,
        status=ResponseStatus.NEEDS_INPUT,
        message=message,
        data_type=DataType.NEEDS_INPUT,
        data=NeedsInputPayload(prompt=message, missing_fields=missing),
        reason_code=reason_code,
        suggested_actions=[RetryAction(reason_code=reason_code)],
    )


async def _response_from_workflow(intent: IntentEnum, result: WorkflowResult) -> OrchestratorResponse:
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
        "không cần xác nhận",
        "khong can xac nhan",
        "cứ phân tích",
        "cu phan tich",
    )
    return any(pattern in lowered for pattern in patterns)


def _looks_like_gibberish(message: str) -> bool:
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
) -> OrchestratorResponse:
    runtime = runtime or OrchestratorRuntime()
    started_at = time.perf_counter()
    # Dung request_id CUA REQUEST dang phuc vu, khong sinh id moi.
    #
    # Mot luot goi HTTP sinh ra hai dong log: `request_timing` tu middleware va
    # `orchestrator_turn` tu day. Sinh uuid rieng o day nghia la hai dong mang
    # hai id khac nhau va khong cach nao noi lai — dung thu ma ca lop trace ton
    # tai de lam. Cung id do con di ra header X-Request-ID va vao bang
    # request_traces, nen admin dan mot id la thay ca chuoi.
    #
    # Fallback ve uuid moi cho truong hop goi ngoai vong doi request (test goi
    # thang `handle_message`), luc do khong co timing nao trong context.
    timing = get_current_timing()
    request_id = timing.request_id if timing is not None else uuid.uuid4().hex
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

    resolved = resolve_context(request.message, session, request.ui_context)
    if resolved.reason_code == ReasonCode.AMBIGUOUS_CONTEXT:
        response = _needs_input_response(
            IntentEnum.ANALYZE_TREND,
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Vui lòng chọn chỉ số cần so sánh trước.",
            ["current_analyte"],
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

    if contains_lab_value(request.message):
        return _needs_input_response(
            IntentEnum.ANALYZE_REPORT,
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Vui lòng nhập chỉ số qua form phân tích hoặc xác nhận OCR trước.",
            ["analysis_input"],
        )

    if _looks_like_gibberish(request.message):
        return _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE,
            ReasonCode.UNKNOWN_INTENT,
            "Tôi chưa hiểu yêu cầu này. Vui lòng diễn đạt lại.",
        )

    if _is_ocr_bypass_request(request.message):
        review_state = get_current_review_state(db, current_user=current_user)
        session = runtime.session_store.replace_pending_review(
            current_user,
            session,
            pending_ocr_review=review_state.pending,
        )
        if review_state.pending:
            return _blocked_response(
                IntentEnum.ANALYZE_REPORT,
                ReasonCode.OCR_REVIEW_REQUIRED,
                "Bạn cần xác nhận OCR trước khi phân tích phiếu từ ảnh.",
            )

    route = RouteDecision(intent=resolved.forced_intent, route_confidence=1.0) if resolved.forced_intent else await route_intent(
        request.message,
        session,
        role,
    )
    if route.reason_code in {
        ReasonCode.MEDICAL_DIAGNOSIS_REQUEST,
        ReasonCode.MEDICAL_CAUSE_REQUEST,
        ReasonCode.TREATMENT_REQUEST,
        ReasonCode.UNKNOWN_INTENT,
    }:
        response = _blocked_response(route.intent, route.reason_code, "Tôi không thể hỗ trợ yêu cầu này an toàn.")
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
        ),
    )
    next_report_ref, next_analyte = _context_after_workflow(
        result=result,
        current_report_ref=resolved.current_report_ref,
        current_analyte=resolved.current_analyte,
    )
    runtime.session_store.update_after_turn(
        current_user,
        session,
        last_intent=route.intent,
        current_report_ref=next_report_ref,
        current_analyte=next_analyte,
        transient_ui_context=request.ui_context,
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
    return await _response_from_workflow(route.intent, result)


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
