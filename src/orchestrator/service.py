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
from src.orchestrator.dispatcher import (
    DispatchContext,
    WorkflowResult,
    dispatch_provenance_followup,
    dispatch_workflow,
)
from src.orchestrator.gates import (
    emergency_safety_gate,
    is_provenance_request,
    medical_safety_gate,
    onboarding_gate,
    policy_gate,
    role_admission_gate,
    treatment_followup_gate,
)
from src.orchestrator.intent_router import RouteDecision, contains_lab_value, route_intent
from src.orchestrator.progress import ProgressCallback, emit_progress
from src.orchestrator.response_composer import (
    _safety_refusal_message,
    build_final_response,
    build_provenance_response,
    map_needs_input_prompt,
)
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


def _needs_input_response(
    intent: IntentEnum, reason_code: ReasonCode, message: str, missing: list[str]
) -> OrchestratorResponse:
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
    response_style: str = "simple",
    user_message: str | None = None,
) -> OrchestratorResponse:
    await emit_progress(progress_callback, ProgressStage.RESPONSE_COMPOSITION)
    return await build_final_response(
        intent=intent,
        status=result.status,
        data=result.data,
        reason_code=result.reason_code,
        response_style=response_style,
        user_message=user_message,
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


def _is_unclear_input(message: str) -> bool:
    from src.orchestrator.medical_context import (
        _is_referential_analyte,
        _normalize_no_accents,
        extract_explicit_analyte,
        extract_explicit_report_date,
        extract_explicit_report_ref,
    )

    raw = message.strip()
    if not raw:
        return True

    # 1. Any medical safety trigger (emergency, diagnosis, cause, treatment) is coherent
    if emergency_safety_gate(message) is not None or medical_safety_gate(message) is not None:
        return False

    # 2. Any explicit analyte or lab value or OCR bypass is coherent
    if extract_explicit_analyte(message) is not None or contains_lab_value(message) or _is_ocr_bypass_request(message):
        return False

    # 3. Explicit report ref or report date is coherent
    if extract_explicit_report_ref(message) is not None or extract_explicit_report_date(message) is not None:
        return False

    norm_no_acc = _normalize_no_accents(message)

    # 4. Referential terms ("chỉ số này", "nó") are coherent
    if _is_referential_analyte(norm_no_acc):
        return False

    # 5. Pure punctuation / non-alphanumeric
    tokens = re.findall(r"[A-Za-zÀ-ỹ0-9]+", message)
    if not tokens:
        return True

    # 6. Check for pure numbers without context (e.g. "123 456")
    if all(t.isdigit() for t in tokens) and len(tokens) >= 2:
        return True

    # 7. Check for repetitive nonsense tokens (e.g. "test test test", "blah blah", "bla bla bla")
    lower_tokens = [t.lower() for t in tokens]
    if len(lower_tokens) >= 2 and len(set(lower_tokens)) == 1:
        return True

    # 8. Check for random consonant clusters / keyboard mash (e.g. "asdfgh", "xqz", "qwerty", "zxcv", "asdf")
    vowels = set("aeiouyáàảãạăắằẳẵặâấầẩẫậéèẻẽẹêếềểễệíìỉĩịóòỏõọôốồổỗộơớờởỡợúùủũụưứừửữựýỳỷỹỵ")
    for t in lower_tokens:
        if not t.isdigit() and len(t) >= 3 and not any(ch in vowels for ch in t):
            return True
        if t in {"asdf", "asdfg", "asdfgh", "qwerty", "zxcv", "zxcvb", "qwer", "hjkl"}:
            return True

    # 9. Short nonsense tokens combination (e.g. "abc xyz", "123 abc")
    if len(lower_tokens) <= 2:
        if all(
            t in {"abc", "xyz", "qwe", "asd", "zxc", "123", "456", "789", "bla", "blah", "test"} for t in lower_tokens
        ):
            return True
        if norm_no_acc in {"o kia", "noi gi do", "abc xyz", "123 abc", "blah blah", "test test"}:
            return True

    return False


_looks_like_gibberish = _is_unclear_input


def _log_turn(
    *,
    request_id: str,
    session_id: str,
    role: str,
    route: RouteDecision | None,
    workflow_selected: str,
    failure_code: ReasonCode | None,
    started_at: float,
    guardrail_triggered: bool = False,
    chat_engine: str = "canonical",
    fallback_reason: str | None = None,
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
            "guardrail_triggered": guardrail_triggered,
            "authorization_outcome": "denied" if failure_code == ReasonCode.UNSUPPORTED_CAPABILITY else "allowed",
            "chat_engine": chat_engine,
            "fallback_reason": fallback_reason,
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
    """Xu ly mot luot, va neu co hoi thoai thi luu lai luot do.

    `conversation` do ROUTE giai ra, khong phai o day: giai ra tu
    `request.conversation_id` co the that bai vi khong dung chu so huu, va do la
    404 -- mot quyet dinh thuoc tang HTTP. Service khong nen nem HTTPException.

    `conversation is None` nghia la khach, hoac bac si, hoac mot lenh goi
    truc tiep trong test. Luc do khong gan, khong ghi, va toan bo hanh vi cu
    giu nguyen tung dong -- day la ly do lop bao nay mong nhu vay.
    """

    if conversation is None:
        return await _handle_message_core(
            request,
            current_user=current_user,
            db=db,
            runtime=runtime,
            progress_callback=progress_callback,
        )

    # Ghi cau hoi TRUOC khi xu ly. Neu lat sang sau, mot luot loi giua duong se
    # lam mat han cau hoi cua benh nhan khoi transcript, va ho tai lai trang thi
    # thay minh chua tung hoi gi. Thay cau hoi khong co tra loi thi con doc duoc.
    _persist_message(
        db,
        conversation=conversation,
        role=conversation_repository.ROLE_USER,
        content=request.message,
    )

    with bind_conversation(db, conversation):
        response = await _handle_message_core(
            request,
            current_user=current_user,
            db=db,
            runtime=runtime,
            progress_callback=progress_callback,
        )

    # `response.message` la van ban DA qua guardrail -- dung thu benh nhan thay
    # tren man hinh. Khong luu ban tien kiem duyet: doc lai lich su phai thay
    # dung thu da hien, khong thay thu he thong da co y chan.
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
    """Ghi mot luot, va khong bao gio lam do luot dang phuc vu.

    Nuot loi o BIEN chu khong chi trong repository: neu ghi that bai truoc khi
    vao duoc block try cua repository (session dut, ai do doi ky hieu ham) thi
    exception se bay len va bien mot cau tra loi dung thanh 500. Mat lich su la
    thiet hai nho hon mat cau tra loi. Log lai de con lan ra duoc.
    """

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


def _immediately_previous_reason_code(
    db: object,
    current_user: object,
) -> ReasonCode | None:
    """Read the assistant turn directly preceding the current persisted user turn."""

    binding = current_binding()
    patient_id = getattr(current_user, "user_id", None)
    if binding is None or not isinstance(patient_id, int):
        return None
    _, conversation = binding
    conversation_id = getattr(conversation, "id", None)
    if not isinstance(conversation_id, int):
        return None
    rows = conversation_repository.list_messages(
        db,
        conversation_id=conversation_id,
        patient_id=patient_id,
    )
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
        return _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vai trò này chưa được hỗ trợ trong Orchestrator V1."
        )

    try:
        session = runtime.session_store.get_or_create(current_user)
    except ValueError:
        return _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE, ReasonCode.AUTH_EXPIRED, "Phiên đăng nhập không hợp lệ."
        )

    v2_failure = False

    def _log_turn_canonical(
        *,
        route: RouteDecision | None,
        workflow_selected: str = "",
        failure_code: ReasonCode | None = None,
        guardrail_triggered: bool = False,
    ) -> None:
        from src.config import get_settings
        from src.models.db import ROLE_PATIENT

        fallback_reason = (
            "v2_failure"
            if v2_failure
            else ("v2_disabled" if not get_settings().agent_chat_v2 and role == ROLE_PATIENT else None)
        )
        _log_turn(
            request_id=request_id,
            session_id=session.session_id,
            role=role,
            route=route,
            workflow_selected=workflow_selected,
            failure_code=failure_code,
            started_at=started_at,
            guardrail_triggered=guardrail_triggered,
            chat_engine="canonical",
            fallback_reason=fallback_reason,
        )

    route: RouteDecision | None = None

    # 0. Emergency / Urgent symptom safety gate (deterministic short-circuit)
    emergency_reason = emergency_safety_gate(request.message)
    if emergency_reason is not None:
        route = RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=emergency_reason,
            route_confidence=1.0,
        )
        response = _blocked_response(
            route.intent,
            route.reason_code,
            _safety_refusal_message(route.reason_code),
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    reason = onboarding_gate(session)
    if reason is not None:
        response = _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE, reason, "Vui lòng xác nhận hướng dẫn sử dụng trước."
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=reason,
        )
        return response

    # 1. Medical safety gate
    safety_reason = medical_safety_gate(request.message)
    if safety_reason is not None:
        route = RouteDecision(intent=IntentEnum.UNSUPPORTED_OR_UNSAFE, reason_code=safety_reason, route_confidence=1.0)
        response = _blocked_response(route.intent, route.reason_code, _safety_refusal_message(route.reason_code))
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    # 2. Sensitive system / security gate
    from src.orchestrator.gates import out_of_scope_gate, sensitive_system_gate

    sensitive_reason = sensitive_system_gate(request.message)
    if sensitive_reason is not None:
        route = RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE, reason_code=sensitive_reason, route_confidence=1.0
        )
        response = _blocked_response(route.intent, route.reason_code, SENSITIVE_SYSTEM_MESSAGE)
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    # 3. Unclear / gibberish input gate
    active_pending = session.conversation_state.get_active_pending_question()
    if not active_pending and _is_unclear_input(request.message):
        route = RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=ReasonCode.UNKNOWN_INTENT,
            route_confidence=1.0,
        )
        response = _blocked_response(
            route.intent,
            route.reason_code,
            UNCLEAR_INPUT_MESSAGE,
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    # 4. Out of scope gate (deterministic high-confidence)
    out_of_scope_reason = out_of_scope_gate(request.message)
    if out_of_scope_reason is not None:
        route = RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=out_of_scope_reason,
            route_confidence=1.0,
        )
        response = _blocked_response(
            route.intent,
            route.reason_code,
            OUT_OF_SCOPE_MESSAGE,
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    # 4b. CHAT-V1.5-R1-G4 layer 2: context-aware treatment follow-up
    # elevation. An ambiguous short action follow-up is elevated to
    # TREATMENT_REQUEST only when an authenticated active report/analyte
    # context exists; without context this gate never fires. Context may
    # elevate safety but never downgrade it.
    followup_reason = treatment_followup_gate(
        request.message,
        session,
        prior_reason_code=_immediately_previous_reason_code(db, current_user),
    )
    if followup_reason is not None:
        route = RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE, reason_code=followup_reason, route_confidence=1.0
        )
        response = _blocked_response(route.intent, route.reason_code, _safety_refusal_message(route.reason_code))
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=followup_reason,
        )
        return response

    # 5. OCR bypass check
    if _is_ocr_bypass_request(request.message):
        route = RouteDecision(
            intent=IntentEnum.ANALYZE_REPORT, reason_code=ReasonCode.OCR_REVIEW_REQUIRED, route_confidence=1.0
        )
        response = _blocked_response(
            route.intent,
            route.reason_code,
            "Bạn cần xác nhận OCR trước khi phân tích phiếu từ ảnh.",
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    # VMEC-05 fast slice: deterministic input gates above retain precedence.
    # Only authenticated patients enter the tool-calling graph; guests keep
    # the established capability policy. Any V2 runtime failure falls through
    # to the complete canonical path below.
    from src.config import get_settings
    from src.models.db import ROLE_PATIENT

    v2_failure = False
    if get_settings().agent_chat_v2 and role == ROLE_PATIENT:
        await emit_progress(progress_callback, ProgressStage.ROUTING)
        try:
            from src.orchestrator.agent_v2 import run_agent_v2

            agent_result = await run_agent_v2(
                message=request.message,
                current_user=current_user,
                db=db,
                current_report_ref=session.current_report_ref,
                current_analyte=session.current_analyte,
            )
        except Exception:
            v2_failure = True
            logger.warning("Agent Chat V2 unavailable; falling back to canonical orchestrator", exc_info=True)
        else:
            from src.models.orchestrator_schemas import ConversationState

            runtime.session_store.update_after_turn(
                current_user,
                session,
                last_intent=agent_result.response.intent,
                current_report_ref=agent_result.current_report_ref,
                current_analyte=agent_result.current_analyte,
                transient_ui_context=request.ui_context,
                conversation_state=ConversationState(),
            )
            _log_turn(
                request_id=request_id,
                session_id=session.session_id,
                role=role,
                route=RouteDecision(intent=agent_result.response.intent, route_confidence=1.0),
                workflow_selected=agent_result.workflow_selected,
                failure_code=agent_result.response.reason_code,
                started_at=started_at,
                guardrail_triggered=(agent_result.response.reason_code == ReasonCode.GUARDRAIL_BLOCKED),
                chat_engine="agent_v2",
                fallback_reason=None,
            )
            return agent_result.response

    # 6. Intent router
    # 6a. CHAT-V1.5-R1-G1: constrained provenance follow-up mode.
    # A bare stored-provenance question ("Thông tin này dựa trên đâu?") is
    # routed deterministically to the canonical approved-source path BEFORE
    # the LLM router, so it can neither be re-explained nor fall to generic
    # SAFE_GENERAL, and composer availability cannot change the answer.
    # All earlier gates (unclear, out-of-scope, treatment elevation, OCR)
    # keep their precedence; this detection never overrides a safety route.
    provenance_turn = is_provenance_request(request.message)

    has_medical_context = (
        session.current_report_ref is not None or session.current_analyte is not None or (role == ROLE_PATIENT)
    )
    await emit_progress(progress_callback, ProgressStage.ROUTING)
    if provenance_turn:
        route = RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=1.0)
    else:
        route = await route_intent(request.message, session, role, has_medical_context=has_medical_context)
    if route.reason_code == ReasonCode.UNKNOWN_INTENT:
        response = _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE,
            ReasonCode.UNKNOWN_INTENT,
            UNCLEAR_INPUT_MESSAGE,
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.UNKNOWN_INTENT,
        )
        return response
    if route.reason_code == ReasonCode.OUT_OF_SCOPE:
        response = _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE,
            ReasonCode.OUT_OF_SCOPE,
            OUT_OF_SCOPE_MESSAGE,
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.OUT_OF_SCOPE,
        )
        return response
    if route.reason_code == ReasonCode.SENSITIVE_SYSTEM_REQUEST:
        response = _blocked_response(
            IntentEnum.UNSUPPORTED_OR_UNSAFE,
            ReasonCode.SENSITIVE_SYSTEM_REQUEST,
            SENSITIVE_SYSTEM_MESSAGE,
        )
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.SENSITIVE_SYSTEM_REQUEST,
        )
        return response

    # 7. Medical context resolver (Autonomous context retrieval)
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
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=ReasonCode.AMBIGUOUS_CONTEXT,
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
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=route.reason_code,
        )
        return response

    reason = policy_gate(role, route.intent)
    if reason is not None:
        response = _blocked_response(route.intent, reason, "Chức năng này chưa được hỗ trợ cho phiên hiện tại.")
        _log_turn_canonical(
            route=route,
            workflow_selected="",
            failure_code=reason,
        )
        return response

    dispatch_context = DispatchContext(
        current_user=current_user,
        db=db,
        current_report_ref=resolved.current_report_ref,
        current_analyte=resolved.current_analyte,
        progress_callback=progress_callback,
        # Carried for: (a) CHAT-V1.5-R1-G1 provenance follow-up named-source
        # verification, and (b) APP_HELP retrieval, which embeds the raw
        # question against the App Help corpus.
        message=request.message,
    )
    if provenance_turn:
        result = await dispatch_provenance_followup(dispatch_context)
    else:
        result = await dispatch_workflow(route.intent, dispatch_context)
    next_report_ref, next_analyte = _context_after_workflow(
        result=result,
        current_report_ref=resolved.current_report_ref,
        current_analyte=resolved.current_analyte,
    )
    if provenance_turn and result.status == ResponseStatus.SUCCESS:
        # CHAT-V1.5-R1-G1: the provenance-specific deterministic builder only
        # accepts a successful provenance payload. Any non-success dispatch
        # outcome (ownership BLOCKED, DB unavailable, ...) flows through the
        # existing generic composition path instead, so unauthorized or stale
        # report references fail closed without a runtime error.
        # HOTFIX-001.
        await emit_progress(progress_callback, ProgressStage.RESPONSE_COMPOSITION)
        final_response = build_provenance_response(result.data)
    else:
        # Resolve effective response style: per-message override takes precedence over persisted user style
        effective_style = "simple"
        if request.ui_context and getattr(request.ui_context, "response_style", None):
            style_val = str(request.ui_context.response_style).casefold()
            if style_val in {"concise", "simple", "detailed"}:
                effective_style = style_val
        elif getattr(current_user, "response_style", None):
            style_val = str(current_user.response_style).casefold()
            if style_val in {"concise", "simple", "detailed"}:
                effective_style = style_val
        elif getattr(session, "response_style", None):
            style_val = str(session.response_style).casefold()
            if style_val in {"concise", "simple", "detailed"}:
                effective_style = style_val

        final_response = await _response_from_workflow(
            route.intent,
            result,
            progress_callback=progress_callback,
            response_style=effective_style,
            user_message=request.message,
        )

    # Save conversation state with active timestamp
    from src.models.orchestrator_schemas import ConversationState

    new_state = ConversationState(
        pending_question=final_response.message if final_response.status == ResponseStatus.NEEDS_INPUT else None,
        pending_question_timestamp=time.time() if final_response.status == ResponseStatus.NEEDS_INPUT else None,
    )

    clear_analyte = result.status == ResponseStatus.SUCCESS and result.workflow_selected == "get_my_report_summary"

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
    _log_turn_canonical(
        route=route,
        workflow_selected=result.workflow_selected,
        failure_code=result.reason_code,
        guardrail_triggered=(final_response.reason_code == ReasonCode.GUARDRAIL_BLOCKED),
    )
    return final_response


def acknowledge_onboarding(
    current_user: object,
    *,
    runtime: OrchestratorRuntime | None = None,
    db: object | None = None,
    conversation: object | None = None,
) -> OrchestratorResponse:
    """Ghi nhan da doc huong dan.

    `conversation` la BAT BUOC voi benh nhan, du chu ky cho phep None.

    Ly do: context giờ gan theo hoi thoai. Khong gan o day thi xac nhan roi vao
    ban ghi in-memory khoa theo `patient:{uid}`, con luot chat sau doc hang
    `conv:{id}` -- va benh nhan ket o man onboarding vinh vien, dung mot buoc
    sau khi vua bam "Toi da hieu". Bo test tip006 bat dung loi nay.
    """

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
