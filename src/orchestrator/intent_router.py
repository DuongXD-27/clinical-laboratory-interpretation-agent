from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from src.models.orchestrator_schemas import IntentEnum, OrchestratorSessionContext, ReasonCode
from src.services.llm import get_llm


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
    has_number = re.search(r"\d+(?:[.,]\d+)?", message) is not None
    has_analyte = any(term in normalized for term in ("hba1c", "ldl", "wbc", "glucose", "cholesterol"))
    has_unit = any(term in normalized for term in ("mmol", "mg", "dl", "g l", "u l", "10 9"))
    return has_number and (has_analyte or has_unit)


def _unsafe_reason(normalized: str) -> ReasonCode | None:
    if any(phrase in normalized for phrase in ("mac benh gi", "toi bi benh gi", "chan doan", "co benh khong")):
        return ReasonCode.MEDICAL_DIAGNOSIS_REQUEST
    if any(phrase in normalized for phrase in ("nguyen nhan", "tai sao", "co the do")):
        return ReasonCode.MEDICAL_CAUSE_REQUEST
    if any(phrase in normalized for phrase in ("uống thuốc", "uong thuoc", "dung thuoc", "ke don", "dieu tri")):
        return ReasonCode.TREATMENT_REQUEST
    return None


def _deterministic_route(message: str) -> RouteDecision | None:
    normalized = _normalize(message)
    reason_code = _unsafe_reason(normalized)
    if reason_code is not None:
        return RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=reason_code,
            route_confidence=1.0,
        )
    if any(term in normalized for term in ("lich su", "history", "lan truoc")):
        return RouteDecision(intent=IntentEnum.VIEW_HISTORY, route_confidence=0.95)
    if any(term in normalized for term in ("xu huong", "trend", "so voi")):
        return RouteDecision(intent=IntentEnum.ANALYZE_TREND, route_confidence=0.95)
    if any(term in normalized for term in ("hoi bac si", "cau hoi", "doctor question")):
        return RouteDecision(intent=IntentEnum.GET_DOCTOR_QUESTIONS, route_confidence=0.95)
    if any(term in normalized for term in ("giai thich", "explain")):
        return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=0.9)
    if any(term in normalized for term in ("phan tich", "analyze", "ket qua", "xet nghiem")):
        return RouteDecision(intent=IntentEnum.ANALYZE_REPORT, route_confidence=0.9)
    return None


def _prompt_for(message: str, session: OrchestratorSessionContext, role: str) -> str:
    context = {
        "has_current_report": session.current_report_ref is not None,
        "current_analyte_name": session.current_analyte,
        "last_intent": session.last_intent.value if session.last_intent is not None else None,
        "pending_ocr_review": session.pending_ocr_review,
        "role": role,
    }
    return (
        "Classify the user request into exactly one VMEC-05 V1 intent. "
        "Return only the intent name.\n"
        f"Allowed intents: {[intent.value for intent in IntentEnum]}\n"
        f"Sanitized user utterance: {_sanitize_for_prompt(message)}\n"
        f"Sanitized context: {context}"
    )


async def route_intent(message: str, session: OrchestratorSessionContext, role: str) -> RouteDecision:
    deterministic = _deterministic_route(message)
    if deterministic is not None:
        return deterministic

    prompt = _prompt_for(message, session, role)
    try:
        response = await get_llm().ainvoke(prompt)
    except Exception:
        return RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=ReasonCode.UNKNOWN_INTENT,
            route_confidence=0.0,
        )

    content = str(getattr(response, "content", response)).strip()
    try:
        return RouteDecision(intent=IntentEnum(content), route_confidence=0.5)
    except ValueError:
        return RouteDecision(
            intent=IntentEnum.UNSUPPORTED_OR_UNSAFE,
            reason_code=ReasonCode.UNKNOWN_INTENT,
            route_confidence=0.0,
        )
