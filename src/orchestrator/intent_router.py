from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.models.orchestrator_schemas import IntentEnum, OrchestratorSessionContext, ReasonCode
from src.orchestrator.medical_context import extract_explicit_analyte, extract_explicit_report_ref
from src.services.llm import get_llm
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError


@dataclass(frozen=True)
class RouteDecision:
    intent: IntentEnum
    reason_code: ReasonCode | None = None
    route_confidence: float = 1.0


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _sanitize_for_prompt(message: str) -> str:
    sanitized = re.sub(r"\b[\w.%+-]+@[\w.-]+\.[A-Za-z]{2,}\b", "[redacted]", message)
    sanitized = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "[date]", sanitized)
    sanitized = re.sub(r"\b\d+(?:[.,]\d+)?\b", "[number]", sanitized)
    return sanitized[:500]


def contains_lab_value(message: str) -> bool:
    normalized = _normalize(message)
    has_number = re.search(r"(?<!\w)[+-]?\d+(?:[.,]\d+)?(?!\w)", message) is not None
    analyte = extract_explicit_analyte(message) or extract_explicit_analyte(normalized)
    try:
        has_analyte = analyte in ReferenceRepository.from_default_files().approved_analytes
    except ReferenceRepositoryError:
        has_analyte = False
    has_unit = any(term in normalized for term in ("mmol", "mg", "dl", "g l", "u l", "10 9"))
    return has_number and (has_analyte or has_unit)


def _is_trend_request(message: str, normalized: str) -> bool:
    strong_trend_cues = (
        "xu huong",
        "trend",
        "so voi",
        "thay doi",
        "tang hay giam",
        "co tang khong",
        "co giam khong",
        "tang bao nhieu",
        "giam bao nhieu",
        "theo thoi gian",
        "qua cac lan xet nghiem",
        "qua cac lan",
        "cu tang",
        "cu giam",
        "tang lien tuc",
        "giam lien tuc",
    )
    if any(term in normalized for term in strong_trend_cues):
        return True

    has_explicit_analyte = extract_explicit_analyte(message) is not None
    has_temporal_context = any(
        term in normalized
        for term in ("dao nay", "gan day", "thoi gian gan day")
    )
    asks_how_it_is_changing = any(
        term in normalized
        for term in ("ra sao", "the nao")
    )
    names_current_result = "ket qua" in normalized
    return (
        has_explicit_analyte
        and has_temporal_context
        and asks_how_it_is_changing
        and not names_current_result
    )


def _is_explicit_current_result_request(message: str, normalized: str) -> bool:
    if extract_explicit_analyte(message) is None:
        return False
    return any(
        term in normalized
        for term in (
            "hien tai",
            "gan nhat",
            "moi nhat",
            "la bao nhieu",
        )
    )




def _deterministic_route(
    message: str,
    session: OrchestratorSessionContext | None = None,
    has_medical_context: bool = False,
) -> RouteDecision | None:
    normalized = _normalize(message)
    original_lower = message.casefold()

    # 0. APP_HELP: navigational "how do I use this app feature" questions
    # (upload, history, trends, OCR review, profile...). Must run BEFORE
    # VIEW_HISTORY/ANALYZE_TREND/EXPLAIN_CURRENT_RESULT, since those match on
    # bare feature nouns ("lich su", "xu huong", "tai sao") that also appear
    # inside navigational phrasing like "xem lich su o dau". Requires a
    # navigation cue AND an app-feature cue together so genuine medical
    # questions ("tại sao WBC cao?", no feature cue) are never caught here.
    app_help_explicit_patterns = (
        "huong dan su dung", "huong dan dung", "huong dan toi su dung",
        "huong dan toi tai phieu", "huong dan tai phieu", "huong dan dung ocr",
        "huong dan toi dung ocr", "huong dan xem ket qua", "huong dan xem lich su",
        "huong dan xem xu huong", "cach su dung", "cach dung ung dung",
        "tai phieu xet nghiem o dau", "tai phieu o dau", "khong tai duoc phieu",
        "chuc nang ocr", "ocr dung de lam gi", "ocr cua ung dung",
        "tai sao phai xac nhan ocr", "vi sao phai xac nhan ocr",
        "sua ho so o dau", "sua thong tin ca nhan o dau", "chinh sua ho so o dau",
        "xem canh bao khan cap o dau",
    )
    app_help_nav_cues = (
        "o dau", "lam sao", "huong dan", "cach ", "tai sao", "vi sao",
        "sao khong", "khong duoc", "co can phai",
    )
    app_help_feature_cues = (
        "tai phieu", "tai anh", "upload", "tai len phieu",
        "lich su", "xu huong", "trend",
        "xac nhan ocr", "ocr",
        "ho so", "thong tin ca nhan", "profile", "tai khoan",
        "canh bao khan cap", "canh bao nguy kich",
        "chuc nang", "tinh nang cua ung dung",
    )
    is_app_help = any(term in normalized for term in app_help_explicit_patterns) or (
        any(term in normalized for term in app_help_nav_cues)
        and any(term in normalized for term in app_help_feature_cues)
    )
    if is_app_help:
        return RouteDecision(intent=IntentEnum.APP_HELP, route_confidence=0.95)

    # 1. VIEW_HISTORY
    if any(term in normalized for term in ("lich su", "history", "lan truoc", "thang truoc", "xem lai", "lan truoc nua")):
        return RouteDecision(intent=IntentEnum.VIEW_HISTORY, route_confidence=0.95)

    # 2. ANALYZE_TREND: explicit longitudinal semantics take precedence over
    # ingestion/current-value hints, including when the message has a value.
    if _is_trend_request(message, normalized):
        return RouteDecision(intent=IntentEnum.ANALYZE_TREND, route_confidence=0.95)

    # 3. GET_DOCTOR_QUESTIONS
    if any(term in normalized for term in ("hoi bac si", "hoi gi bac si", "cau hoi", "doctor question")):
        return RouteDecision(intent=IntentEnum.GET_DOCTOR_QUESTIONS, route_confidence=0.95)

    # 4. SAFE_GENERAL (Greetings and general capability questions — specific
    # "how do I use feature X" questions are routed to APP_HELP above)
    safe_general_patterns = (
        "chao ban", "chao em", "chao bac", "chao anh", "chao chi", "xin chao",
        "hello", "cam on", "thank", "ban lam duoc gi", "tro ly nay giup gi",
        "bat dau tu dau", "ban la ai", "giup toi lam gi", "giup gi", "co the giup",
        "lam duoc gi", "ban giup duoc gi", "ban co the lam gi",
    )
    if any(term in normalized for term in safe_general_patterns) or "hi" in normalized.split():
        return RouteDecision(intent=IntentEnum.SAFE_GENERAL, route_confidence=1.0)

    # Ingestion / Active upload context detection
    has_active_ingestion = session is not None and (
        session.pending_ocr_review
        or (session.conversation_state and session.conversation_state.pending_question == "ocr-review")
    )
    explicit_new_ingestion_markers = (
        "phan tich", "analyze", "tai anh", "gui anh", "anh nay", "anh xet nghiem",
        "doc giup toi phieu", "doc phieu", "doc anh",
        "cai xet nghiem", "cai xet nghiem nay",
        "toi co phieu moi", "vua nhan phieu", "moi nhan phieu", "moi nhan ket qua",
        "nhan ket qua moi", "nhap ket qua", "nhap thu cong"
    )
    is_explicit_new_ingestion = any(term in normalized for term in explicit_new_ingestion_markers)

    # Existing report review & summary cues
    existing_report_cues = (
        "phieu nay the nao", "phieu nay sao", "phieu nay sao roi",
        "tom tat phieu nay", "tom tat phieu", "tom tat ket qua",
        "co gi dang chu y trong phieu nay", "co gi can chu y trong phieu nay",
        "nhin chung ca phieu", "xem tong the phieu", "xem tong quan phieu",
        "xem phieu nay", "ket qua nay the nao",
        "co gi dang chu y", "co gi can chu y", "nhin chung ca phieu cua em thi sao",
        "xem tong the ket qua", "xem tong quan ket qua", "tong the phieu nay",
        "xem tong quan", "tong quan", "xem tong the", "tong the"
    )
    is_existing_report_overview = any(term in normalized for term in existing_report_cues)

    # When active OCR review or explicit new ingestion is present, prioritize ANALYZE_REPORT
    if is_explicit_new_ingestion or (has_active_ingestion and any(term in normalized for term in ("phieu nay", "anh nay", "phieu xet nghiem", "xem phieu"))):
        return RouteDecision(intent=IntentEnum.ANALYZE_REPORT, route_confidence=0.9)

    # If it's an existing report overview, route to EXPLAIN_CURRENT_RESULT
    if is_existing_report_overview:
        return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)

    # 5. EXPLAIN_CURRENT_RESULT (Explicit current-result markers or lab values or explicit/referential analytes)
    explain_markers = ("giai thich", "explain", "nghia la gi", "y nghia", "mau do", "tai sao", "thap", "cao")
    has_explicit_analyte = extract_explicit_analyte(message) is not None
    is_analyte_switch = has_explicit_analyte and (
        normalized.startswith("con ") or normalized.startswith("the con ") or "con " in normalized
    )
    from src.orchestrator.medical_context import _is_referential_analyte, _normalize_no_accents
    is_referential = _is_referential_analyte(_normalize_no_accents(message))
    is_explicit_current_result = _is_explicit_current_result_request(message, normalized)
    is_lab_value = contains_lab_value(message)
    has_explain_marker = any(term in normalized for term in explain_markers) or any(term in original_lower for term in ("nghĩa là gì", "ý nghĩa", "màu đỏ"))

    if is_explicit_current_result or is_lab_value or is_analyte_switch or has_explain_marker or has_explicit_analyte or is_referential:
        return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)

    # Generic report queries (e.g. 'phiếu gần nhất', 'kết quả của tôi')
    generic_report_queries = (
        "phieu gan nhat", "ket qua gan nhat", "ket qua moi nhat",
        "ket qua cua toi", "ket qua cua em", "ket qua cua minh",
        "doc ket qua", "xem ket qua", "doc phieu", "xem phieu",
    )
    if any(term in normalized for term in generic_report_queries):
        return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)

    # 6. ANALYZE_REPORT (Fallback for new report phrases)
    if any(term in normalized for term in ("cai xet nghiem", "nhan phieu", "phieu xet nghiem", "anh xet nghiem")):
        if has_active_ingestion:
            return RouteDecision(intent=IntentEnum.ANALYZE_REPORT, route_confidence=0.9)
        elif has_medical_context:
            return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)
        else:
            return RouteDecision(intent=IntentEnum.ANALYZE_REPORT, route_confidence=0.9)

    # 7. Context-aware Vague Patient Expressions (Only active when patient has accessible medical data/session)
    if has_medical_context:
        vague_result_patterns = (
            "xem giup em", "xem giup toi", "xem giup minh",
            "coi giup em", "coi giup toi", "coi dum em", "coi dum minh",
            "em hoi lo", "toi hoi lo", "lo lang", "co sao khong",
            "co van de gi khong", "co can chu y", "dang chu y",
            "co bat thuong khong", "chi so nao bat thuong", "bat thuong khong",
            "chi so nay nghia la gi", "ket qua nay nghia la gi",
            "ket qua gan nhat", "ket qua gan day", "ket qua cua em the nao",
            "ket qua the nao", "ket qua the nao roi", "xem ket qua giup em",
            "xem ket qua", "xem tong the", "tong the ket qua", "khong hieu ket qua",
            "khong hieu ket qua nay", "em khong hieu ket qua",
            "phieu nay", "phieu nay the nao", "ket qua nay",
            "xem tong quan", "tong quan", "tong quan giup",
        )
        if any(term in normalized for term in vague_result_patterns):
            return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)

    return None


def _deterministic_follow_up_route(message: str, session: OrchestratorSessionContext) -> RouteDecision | None:
    active_pending = session.conversation_state.get_active_pending_question()
    if not session.last_intent:
        return None

    normalized = _normalize(message)
    explicit_analyte = extract_explicit_analyte(message)

    # Follow-up with an explicit analyte
    if session.last_intent in {IntentEnum.EXPLAIN_CURRENT_RESULT, IntentEnum.ANALYZE_TREND}:
        if explicit_analyte is not None:
            if active_pending or normalized.startswith("con ") or normalized.startswith("the con ") or len(normalized.split()) <= 3:
                return RouteDecision(intent=session.last_intent, route_confidence=1.0)

    # Follow-up with an explicit report reference
    if session.last_intent in {IntentEnum.GET_DOCTOR_QUESTIONS, IntentEnum.EXPLAIN_CURRENT_RESULT}:
        if extract_explicit_report_ref(message) is not None:
            if active_pending or len(normalized.split()) <= 2:
                return RouteDecision(intent=session.last_intent, route_confidence=1.0)

    return None


def _prompt_for(message: str, session: OrchestratorSessionContext, role: str, has_medical_context: bool = False) -> str:
    active_pending = session.conversation_state.get_active_pending_question()
    context = {
        "has_current_report": session.current_report_ref is not None,
        "current_analyte_name": session.current_analyte,
        "last_intent": session.last_intent.value if session.last_intent is not None else None,
        "pending_question": active_pending,
        "pending_ocr_review": session.pending_ocr_review,
        "has_medical_context": has_medical_context,
        "role": role,
    }
    return (
        "Classify the user request into exactly one VMEC-05 V1 intent. "
        "Return only the intent name.\n"
        f"Allowed intents: {[intent.value for intent in IntentEnum]}\n"
        "RULES:\n"
        "- Prefer EXPLAIN_CURRENT_RESULT when the user asks about an existing indicator/analyte or asks to review/summarize an existing report (e.g. 'Phiếu này thế nào?', 'Tóm tắt phiếu này cho em', 'Có gì đáng chú ý trong phiếu này?').\n"
        "- If the user is a patient with medical context and expresses general concern about their results (e.g. 'Em hơi lo', 'Có bất thường không?'), classify as EXPLAIN_CURRENT_RESULT.\n"
        "- Route ANALYZE_TREND when the user asks about changes over time, history comparisons, or trends (e.g. 'thay đổi thế nào', 'thay đổi ra sao', 'tăng hay giảm').\n"
        "- Route VIEW_HISTORY when asking about past reports (e.g. 'kết quả tháng trước', 'lần trước').\n"
        "- Route APP_HELP when the user asks how/where to use an app feature itself (upload, history list, trends chart, OCR review, profile, alerts) rather than asking about their own medical data (e.g. 'Làm sao tải phiếu?', 'Tôi xem lịch sử ở đâu?', 'Tại sao phải xác nhận OCR?', 'Tôi sửa hồ sơ ở đâu?'). Never use APP_HELP for medical/educational questions or requests about the user's actual results.\n"
        "- Only route ANALYZE_REPORT when the user explicitly requests new report ingestion/processing or when there is an active pending OCR review (e.g. 'Phân tích phiếu này', 'Tôi có phiếu mới', 'Phân tích ảnh này').\n"
        "- If `pending_question` is present and the user gives a short response answering it, rely heavily on `last_intent`.\n"
        "- If the utterance is unclear, nonsense, off-topic, unsupported, or does not clearly match any supported intent, classify as UNSUPPORTED_OR_UNSAFE.\n"
        "- Do NOT guess or infer a medical intent for an utterance that does not specifically ask about tests, reports, analytes, trends, or medical questions, even if medical context is present.\n"
        f"Sanitized user utterance: {_sanitize_for_prompt(message)}\n"
        f"Sanitized context: {context}"
    )


async def route_intent(
    message: str,
    session: OrchestratorSessionContext,
    role: str,
    has_medical_context: bool = False,
) -> RouteDecision:
    follow_up_route = _deterministic_follow_up_route(message, session)
    if follow_up_route is not None:
        return follow_up_route

    deterministic = _deterministic_route(message, session=session, has_medical_context=has_medical_context)
    if deterministic is not None:
        return deterministic

    prompt = _prompt_for(message, session, role, has_medical_context=has_medical_context)
    try:
        response = await get_llm().ainvoke(prompt)
    except Exception:
        from src.orchestrator.gates import out_of_scope_gate, sensitive_system_gate
        from src.orchestrator.service import _is_unclear_input
        if sensitive_system_gate(message) is not None:
            reason = ReasonCode.SENSITIVE_SYSTEM_REQUEST
        elif _is_unclear_input(message):
            reason = ReasonCode.UNKNOWN_INTENT
        elif out_of_scope_gate(message) is not None:
            reason = ReasonCode.OUT_OF_SCOPE
        else:
            reason = ReasonCode.UNKNOWN_INTENT
        return RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=reason,
            route_confidence=0.0,
        )

    content = str(getattr(response, "content", response)).strip()
    try:
        parsed_intent = IntentEnum(content)
        if parsed_intent == IntentEnum.UNSUPPORTED_OR_UNSAFE:
            from src.orchestrator.gates import out_of_scope_gate, sensitive_system_gate
            from src.orchestrator.service import _is_unclear_input
            if sensitive_system_gate(message) is not None:
                reason = ReasonCode.SENSITIVE_SYSTEM_REQUEST
            elif _is_unclear_input(message):
                reason = ReasonCode.UNKNOWN_INTENT
            elif out_of_scope_gate(message) is not None:
                reason = ReasonCode.OUT_OF_SCOPE
            else:
                reason = ReasonCode.OUT_OF_SCOPE
            return RouteDecision(
                intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
                reason_code=reason,
                route_confidence=0.5,
            )
        return RouteDecision(intent=parsed_intent, route_confidence=0.5)
    except ValueError:
        from src.orchestrator.gates import out_of_scope_gate, sensitive_system_gate
        from src.orchestrator.service import _is_unclear_input
        if sensitive_system_gate(message) is not None:
            reason = ReasonCode.SENSITIVE_SYSTEM_REQUEST
        elif _is_unclear_input(message):
            reason = ReasonCode.UNKNOWN_INTENT
        elif out_of_scope_gate(message) is not None:
            reason = ReasonCode.OUT_OF_SCOPE
        else:
            reason = ReasonCode.UNKNOWN_INTENT
        return RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=reason,
            route_confidence=0.0,
        )
