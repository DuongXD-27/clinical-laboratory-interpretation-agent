from __future__ import annotations

from src.models.db import ROLE_DOCTOR, ROLE_PATIENT
from src.models.orchestrator_schemas import IntentEnum, OrchestratorSessionContext, ReasonCode
from src.services.auth import ROLE_GUEST


def onboarding_gate(context: OrchestratorSessionContext) -> ReasonCode | None:
    if not context.onboarding_acknowledged:
        return ReasonCode.ONBOARDING_REQUIRED
    return None


def role_admission_gate(current_user: object) -> ReasonCode | None:
    role = getattr(current_user, "role", None)
    if role in {ROLE_GUEST, ROLE_PATIENT}:
        return None
    if role == ROLE_DOCTOR:
        return ReasonCode.UNSUPPORTED_CAPABILITY
    return ReasonCode.AUTH_EXPIRED


def policy_gate(role: str, intent: IntentEnum) -> ReasonCode | None:
    if role == ROLE_GUEST and intent in {IntentEnum.VIEW_HISTORY, IntentEnum.ANALYZE_TREND}:
        return ReasonCode.UNSUPPORTED_CAPABILITY
    return None


import re
import unicodedata

def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _contains_phrase_norm(normalized_text: str, phrase_norm: str) -> bool:
    escaped = re.escape(phrase_norm)
    pattern = rf"(?:\A|\s){escaped}(?:\Z|\s)"
    return re.search(pattern, normalized_text) is not None


def _contains_phrase_raw(raw_text: str, phrase_raw: str) -> bool:
    escaped = re.escape(phrase_raw)
    pattern = rf"(?:\A|[^\wÀ-ỹ]){escaped}(?:\Z|[^\wÀ-ỹ])"
    return re.search(pattern, raw_text, re.IGNORECASE) is not None


def medical_safety_gate(message: str) -> ReasonCode | None:
    """Run before intent routing to block explicit medical questions."""
    
    normalized = _normalize(message)
    original_lower = message.casefold()
    
    # 1. Diagnosis requests & reassurance
    diag_patterns_raw = (
        "bị bệnh gì", "đoán bệnh", "đoán giúp tôi bệnh gì", "chẩn đoán",
        "có phải tôi bị", "có phải em bị", "tôi có bị", "em có bị",
        "mắc bệnh gì", "bị tiểu đường",
        "chắc chắn tôi không bị", "chắc chắn em không bị",
        "tôi có bị bệnh không", "em có bị bệnh không",
        "tôi bị bệnh gì", "em bị bệnh gì",
    )
    if any(_contains_phrase_raw(original_lower, phrase) for phrase in diag_patterns_raw):
        return ReasonCode.MEDICAL_DIAGNOSIS_REQUEST

    diag_patterns_norm = (
        "bi benh gi", "doan benh", "doan giup toi benh gi", "chan doan",
        "co phai toi bi", "co phai em bi", "toi co bi", "em co bi",
        "mac benh gi", "bi tieu duong",
        "chac chan toi khong bi", "chac chan em khong bi",
        "toi co bi benh khong", "em co bi benh khong",
        "toi bi benh gi", "em bi benh gi",
    )
    if any(_contains_phrase_norm(normalized, phrase) for phrase in diag_patterns_norm):
        return ReasonCode.MEDICAL_DIAGNOSIS_REQUEST

    # 2. Personal Cause requests (distinguish from educational questions like "WBC cao do nguyên nhân gì?")
    personal_cause_raw = (
        "tại sao tôi lại bị", "tại sao em lại bị",
        "tại sao tôi bị", "tại sao em bị",
        "vì sao tôi bị", "vì sao em bị",
        "nguyên nhân tôi bị", "nguyên nhân em bị",
        "do đâu tôi bị", "do đâu em bị",
        "do đâu tôi mắc", "do đâu em mắc",
    )
    if any(_contains_phrase_raw(original_lower, phrase) for phrase in personal_cause_raw):
        return ReasonCode.MEDICAL_CAUSE_REQUEST

    personal_cause_norm = (
        "tai sao toi lai bi", "tai sao em lai bi",
        "tai sao toi bi", "tai sao em bi",
        "vi sao toi bi", "vi sao em bi",
        "nguyen nhan toi bi", "nguyen nhan em bi",
        "do dau toi bi", "do dau em bi",
        "do dau toi mac", "do dau em mac",
    )
    if any(_contains_phrase_norm(normalized, phrase) for phrase in personal_cause_norm):
        return ReasonCode.MEDICAL_CAUSE_REQUEST

    # Generic cause patterns if asked directly about cause of condition
    if any(_contains_phrase_raw(original_lower, phrase) for phrase in ("nguyên nhân là gì", "nguyên nhân do đâu")):
        return ReasonCode.MEDICAL_CAUSE_REQUEST
    if any(_contains_phrase_norm(normalized, phrase) for phrase in ("nguyen nhan la gi", "nguyen nhan do dau")):
        return ReasonCode.MEDICAL_CAUSE_REQUEST

    # 3. Treatment requests & rapid indicator reduction advice
    treatment_raw = (
        "uống thuốc gì", "uống gì", "kê đơn", "điều trị thế nào",
        "làm gì để hạ", "làm gì để giảm", "hạ chỉ số nhanh",
        "giảm chỉ số nhanh", "hạ chỉ số này nhanh", "cách chữa",
        "cách điều trị", "dùng thuốc gì", "mua thuốc gì",
    )
    if any(_contains_phrase_raw(original_lower, phrase) for phrase in treatment_raw):
        return ReasonCode.TREATMENT_REQUEST

    treatment_norm = (
        "uong thuoc gi", "uong gi", "ke don", "dieu tri the nao",
        "lam gi de ha", "lam gi de giam", "ha chi so nhanh",
        "giam chi so nhanh", "ha chi so nay nhanh", "cach chua",
        "cach dieu tri", "dung thuoc gi", "mua thuoc gi",
    )
    if any(_contains_phrase_norm(normalized, phrase) for phrase in treatment_norm):
        return ReasonCode.TREATMENT_REQUEST

    return None
