from __future__ import annotations

import re
import unicodedata

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


# --- CHAT-V1.5-003: form-based personal disease confirmation ---------------
#
# Detects the semantic request FORM "user + disease/condition + asking whether
# they have it" without maintaining a disease dictionary and WITHOUT any
# analyte/value exemption: an explicit analyte or lab value must never
# downgrade a personal disease-confirmation question.

_DIAGNOSIS_PRONOUN = r"(?:toi|em|minh|chung toi)"
_CONDITION_VERB = r"(?:bi|mac)"
_CONFIRMATION_PARTICLES = frozenset({"khong", "chu", "a", "nha"})

# Result-property adjectives: asking about the result's own state is NOT a
# diagnosis proposition ("Chi so nay co phai cao khong?").
_RESULT_PROPERTY_TOKENS = frozenset(
    {"cao", "thap", "on", "tot", "bat", "thuong", "binh", "nguy", "hiem", "lon", "nho"}
)

# App/report nouns never form diagnostic propositions over the result.
_APP_REPORT_NOUNS = ("bao cao", "phieu", "lich su", "chuc nang", "ocr", "ung dung")

_PERSONAL_CONDITION_CONFIRMATION = re.compile(
    rf"\b{_DIAGNOSIS_PRONOUN}\b\s+(?:co\s+)?{_CONDITION_VERB}\s+\S+"
)
_PERSONAL_DISEASE_NP_CONFIRMATION = re.compile(
    rf"\b{_DIAGNOSIS_PRONOUN}\b\s+co\s+(?:benh|chung)\s+\S+"
)
_REFERENTIAL_DIAGNOSIS_LABEL = re.compile(
    r"\b(?:ket qua nay|chi so nay|ket qua xet nghiem nay|chung nay)\s+"
    r"(?:thi\s+)?co\s+phai\s+(?:la\s+)?(.+?)\s+(?:khong|chu|a|nha)\Z"
)


def _matches_personal_diagnosis_form(normalized: str) -> bool:
    """CHAT-V1.5-003: deterministic form detection for diagnosis requests."""
    tokens = normalized.split()
    if not tokens:
        return False
    ends_with_particle = tokens[-1] in _CONFIRMATION_PARTICLES

    # R1/R2 - first-person confirmation: pronoun + condition verb / disease noun
    # + sentence-final confirmation particle.
    if ends_with_particle and (
        _PERSONAL_CONDITION_CONFIRMATION.search(normalized) is not None
        or _PERSONAL_DISEASE_NP_CONFIRMATION.search(normalized) is not None
    ):
        return True

    # R3 - referential disease labeling over the current result
    # ("Ket qua nay co phai ung thu khong?"). Strong forms containing a personal
    # clause ("ket qua nay co nghia la toi bi X khong?") are already caught by R1.
    match = _REFERENTIAL_DIAGNOSIS_LABEL.search(normalized)
    if match is None:
        return False
    from src.orchestrator.medical_context import extract_explicit_analyte

    np_norm = match.group(1).strip()
    if not np_norm or extract_explicit_analyte(np_norm) is not None:
        return False
    if set(np_norm.split()) & _RESULT_PROPERTY_TOKENS:
        return False
    if any(term in np_norm for term in _APP_REPORT_NOUNS):
        return False
    return True


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

    # 1b. Form-based personal disease confirmation (CHAT-V1.5-003).
    # Detect the semantic REQUEST FORM instead of matching only fixed phrases.
    # Explicit analytes or lab values NEVER suppress this detection.
    if _matches_personal_diagnosis_form(normalized):
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


def sensitive_system_gate(message: str) -> ReasonCode | None:
    """Detect requests attempting to access/extract secrets, credentials, internal prompts, or DB."""
    normalized = _normalize(message)

    # 1. System prompt / instructions extraction
    prompt_terms = (
        "system prompt", "prompt he thong", "prompt cua ban", "developer prompt",
        "system instruction", "chi thi he thong", "in prompt", "show prompt",
    )
    if any(term in normalized for term in prompt_terms):
        return ReasonCode.SENSITIVE_SYSTEM_REQUEST

    # 2. Database dump / query / internal access
    db_actions = (
        "query database", "dump database", "truy van database", "query csdl",
        "dump csdl", "database benh nhan", "csdl benh nhan", "sql injection",
        "mat khau database", "password database", "database password",
    )
    if any(term in normalized for term in db_actions):
        return ReasonCode.SENSITIVE_SYSTEM_REQUEST

    # 3. Secret keys, credentials, tokens extraction
    # Negative control: pure definition questions like "API key là gì?", "JWT là gì?" must NOT be blocked here.
    if normalized in {"api key la gi", "jwt la gi", "database la gi", "prompt la gi"}:
        return None
    if normalized.endswith(" la gi") and any(k in normalized for k in ("api key", "jwt", "database", "prompt", "token")):
        return None

    secret_terms = (
        "api key", "gemini key", "gemini api key", "openai key", "openai api key",
        "secret key", "jwt", "access token", "bearer token", "token dang nhap",
        "mat khau he thong", "mat khau admin", "mat khau root", "db password",
        "source code bi mat", "ma nguon bi mat", "source code cua he thong", "ma nguon he thong",
        "file env", "bien moi truong he thong", "internal config",
    )
    for term in secret_terms:
        if term in normalized:
            extraction_terms = ("cho toi", "cho em", "xin", "lay", "cung cap", "in", "show", "hien thi", "xuat", "dump", "query", "truy van", "gui toi", "gui em")
            if any(ext in normalized for ext in extraction_terms) or term in (
                "jwt", "gemini key", "gemini api key", "secret key", "access token",
                "bearer token", "source code bi mat", "ma nguon bi mat", "token dang nhap",
            ) or "cua he thong" in normalized or "cua ban" in normalized:
                return ReasonCode.SENSITIVE_SYSTEM_REQUEST

    return None


def out_of_scope_gate(message: str) -> ReasonCode | None:
    """Detect clear out-of-scope requests (coding, math, translation, trivia, general writing)."""
    from src.orchestrator.intent_router import contains_lab_value
    from src.orchestrator.medical_context import extract_explicit_analyte

    # Positive controls: explicit analyte or lab values are medical
    if extract_explicit_analyte(message) is not None or contains_lab_value(message):
        return None

    normalized = _normalize(message)

    # In-scope app help / capabilities must NEVER be blocked
    in_scope_app_cues = (
        "tai phieu", "khong tai duoc phieu", "tai duoc phieu", "tai anh",
        "dung ocr", "chuc nang ocr", "ocr dung de lam gi", "ocr cua ung dung", "ocr la gi",
        "xem lich su", "xem xu huong", "xem ket qua", "xem phieu",
        "ung dung nay", "chatbot nay", "tro ly nay", "ban lam duoc gi",
        "huong dan su dung", "huong dan dung", "huong dan toi tai phieu",
        "huong dan toi dung ocr", "huong dan toi su dung",
    )
    if any(cue in normalized for cue in in_scope_app_cues):
        return None

    # High-confidence coding & programming requests
    coding_cues = (
        "viet code", "viet python", "code python", "tinh fibonacci", "fibonacci",
        "viet script", "lap trinh", "viet ham", "giai bai python",
        "huong dan viet python", "huong dan lap trinh", "code java", "code c",
        "viet chuong trinh", "debug code",
    )
    if any(cue in normalized for cue in coding_cues):
        return ReasonCode.OUT_OF_SCOPE

    # Math calculations and problem solving
    math_cues = (
        "giai toan", "giai bai toan", "tinh bai toan", "giai phuong trinh",
        "tinh dao ham", "tinh tich phan", "bai tap ve nha", "giai bai tap",
        "huong dan giai toan",
    )
    if any(cue in normalized for cue in math_cues):
        return ReasonCode.OUT_OF_SCOPE

    # Specific math expressions e.g. "2 + 2", "2+2", "giải bài toán 2 + 2"
    if re.search(r"\b\d+\s*[\+\-\*\/]\s*\d+\b", message):
        return ReasonCode.OUT_OF_SCOPE

    # Translation
    translation_cues = (
        "dich tieng anh", "dich sang tieng anh", "dich doan nay", "dich doan",
        "dich cau nay sang tieng anh", "dich cau nay", "dich van ban", "dich sang tieng viet",
        "dich doan tieng anh",
    )
    if any(cue in normalized for cue in translation_cues):
        return ReasonCode.OUT_OF_SCOPE

    # Generic writing & essays
    writing_cues = (
        "viet email xin viec", "viet cv", "viet don xin viec", "viet email",
        "viet thu xin viec", "viet bai van", "viet tho", "viet truyen",
    )
    if any(cue in normalized for cue in writing_cues):
        return ReasonCode.OUT_OF_SCOPE

    # Entertainment & trivia
    trivia_cues = (
        "ke chuyen cuoi", "ke chuyen hai", "chuyen cuoi", "ke chuyen",
        "ai vo dich world cup", "world cup",
    )
    if any(cue in normalized for cue in trivia_cues):
        return ReasonCode.OUT_OF_SCOPE

    # Out-of-scope guidance (e.g. "hướng dẫn nấu ăn", "hướng dẫn chơi game")
    unrelated_guidance = (
        "huong dan nau an", "huong dan choi game", "huong dan tap gym",
    )
    if any(cue in normalized for cue in unrelated_guidance):
        return ReasonCode.OUT_OF_SCOPE

    return None

