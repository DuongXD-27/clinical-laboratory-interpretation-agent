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


# --- CHAT-V1.5-R1-G4: treatment/action request form detection ---------------
#
# Two complementary layers:
#
# Layer 1 - context-free (medical_safety_gate): a treatment construction
#   (patient direction + advice request + change/improve/treat component)
#   is classified as TREATMENT_REQUEST only when the message itself carries
#   a MEDICAL ANCHOR (explicit analyte, result/index nouns, or medication).
#   Broad action forms without an anchor ("Lam sao de giam dung luong file?")
#   must never be classified context-free.
#
# Layer 2 - session-aware elevation (treatment_followup_gate): short,
#   ambiguous action follow-ups ("Vay toi nen lam gi tiep?") are elevated to
#   TREATMENT_REQUEST ONLY when an authenticated active report/analyte
#   context exists. Medical context may elevate safety; it must never
#   downgrade safety nor manufacture a medical answer.
#
# Normalization-collision safety: need-modal "can" collides with the word
# for weigh/balance after accent stripping, and cure "chua" collides with
# "not yet". Bare "can"/"chua" tokens are therefore NEVER used as semantic
# signals. The need-modal is omitted entirely; cure semantics are honored
# only via accent-aware raw constructions already present in the fixed
# phrase lists ("cach chua").

_TREATMENT_PRONOUN_RE = re.compile(r"\b(?:toi|em|minh)\b|\bchung toi\b")
_TREATMENT_MODAL_TOKENS = frozenset({"nen", "phai"})
_TREATMENT_ADVICE_FRAMES = (
    "nen lam gi", "phai lam gi", "nen lam sao",
    "lam gi de", "lam sao de", "co cach nao", "cach nao de",
)
_TREATMENT_CHANGE_VERBS = ("ha", "giam", "cai thien", "dieu tri")
_TREATMENT_DRUG_BIGRAMS = ("dung thuoc", "uong thuoc", "mua thuoc")
_TREATMENT_ANCHOR_PHRASES = ("chi so", "ket qua", "xet nghiem", "benh", "thuoc")
_DOCTOR_QUESTION_FRAME_MARKERS = ("hoi bac si", "chuan bi cau hoi")
_AMBIGUOUS_FOLLOWUP_EXCLUSIONS = (
    "file", "dung luong", "giao dien", "phieu", "anh", "ocr",
    "ung dung", "lich su", "tai khoan", "mat khau", "tieng anh",
    "code", "lap trinh", "game", "nau an", "world cup",
)


def _has_treatment_medical_anchor(normalized: str, original_lower: str) -> bool:
    """The message itself references an analyte/result/index or medication."""
    from src.orchestrator.medical_context import extract_explicit_analyte

    if extract_explicit_analyte(original_lower) is not None:
        return True
    return any(
        _contains_phrase_norm(normalized, phrase)
        for phrase in _TREATMENT_ANCHOR_PHRASES
    )


def _matches_treatment_request_form(normalized: str, original_lower: str) -> bool:
    """CHAT-V1.5-R1-G4 layer 1: form-based treatment detection (context-free).

    Recognizes the request FORM "patient asks what they personally should do
    to change/improve/treat their result" without relying on any single
    keyword, and only when the message carries its own medical anchor so
    that generic (non-medical) how-to questions are never blocked.
    """
    # Doctor-question preparation frames ask what to ASK the clinician about
    # management; they are question preparation, not patient-directed action.
    if any(marker in normalized for marker in _DOCTOR_QUESTION_FRAME_MARKERS):
        return False

    tokens = set(normalized.split())
    has_pronoun = _TREATMENT_PRONOUN_RE.search(normalized) is not None
    has_modal = bool(tokens & _TREATMENT_MODAL_TOKENS)
    advice_frame = any(frame in normalized for frame in _TREATMENT_ADVICE_FRAMES)

    patient_direction = has_pronoun or advice_frame
    advice_request = (has_pronoun and has_modal) or advice_frame
    # Multi-token verbs ("cai thien") require word-boundary phrase matching;
    # single-token set membership can never see them.
    change_component = any(
        _contains_phrase_norm(normalized, verb)
        for verb in _TREATMENT_CHANGE_VERBS
    ) or any(
        _contains_phrase_norm(normalized, bigram)
        for bigram in _TREATMENT_DRUG_BIGRAMS
    )

    return (
        patient_direction
        and advice_request
        and change_component
        and _has_treatment_medical_anchor(normalized, original_lower)
    )


def _is_ambiguous_treatment_followup(normalized: str) -> bool:
    """CHAT-V1.5-R1-G4 layer 2: short ambiguous action follow-up form.

    Matches utterances whose medical target can only come from active
    session context. Domain-bearing questions never match.
    """
    tokens = normalized.split()
    if not tokens or 12 < len(tokens):
        return False
    if any(marker in normalized for marker in _DOCTOR_QUESTION_FRAME_MARKERS):
        return False
    if any(_contains_phrase_norm(normalized, term) for term in _AMBIGUOUS_FOLLOWUP_EXCLUSIONS):
        return False

    has_pronoun = _TREATMENT_PRONOUN_RE.search(normalized) is not None
    has_modal = bool(set(tokens) & _TREATMENT_MODAL_TOKENS)
    advice_frame = any(frame in normalized for frame in _TREATMENT_ADVICE_FRAMES)
    if not ((has_pronoun and has_modal) or advice_frame):
        return False

    continuation_signal = (
        "tiep" in tokens
        or any(
            _contains_phrase_norm(normalized, ref)
            for ref in ("chi so nay", "ket qua nay", "chung nay")
        )
        or any(_contains_phrase_norm(normalized, verb) for verb in _TREATMENT_CHANGE_VERBS)
    )
    return continuation_signal


_DIET_SUPPLEMENT_VERBS = (
    "an", "uong", "kieng", "bo sung", "dung", "nap", "uong thuoc", "dung thuoc",
    "uong vitamin", "uong la", "uong tra", "an gi", "uong gi", "kieng gi", "kieng an",
)
_DIET_FOOD_ITEMS = (
    "thit bo", "thit", "rau", "hoa qua", "tra", "sua", "duong", "muoi", "trung",
    "hai san", "ca", "yen", "sam", "sat", "canxi", "vitamin", "thuoc nam", "thuoc bac",
    "thao duoc", "thuc pham chuc nang", "tpcn", "nuoc dua", "la cay",
)
_HEALTH_TARGET_GOALS = (
    "tang mau", "bo mau", "tang hgb", "ha men gan", "ha duong huyet",
    "ha duong", "giam duong", "giam cholesterol", "giam mo mau", "tang tieu cau",
    "tang bach cau", "giam axit uric", "giam acid uric",
    "tang suc de khang", "tot cho mau", "tot cho gan", "tot cho than",
)


def _matches_personal_medical_advice_form(normalized: str, original_lower: str) -> bool:
    """Detect personal diet, nutrition, supplement, and herbal advice requests.

    Does not intercept pharmaceutical treatment requests (e.g. 'uống thuốc gì').
    """
    if any(marker in normalized for marker in _DOCTOR_QUESTION_FRAME_MARKERS):
        return False

    for suf in _EDUCATIONAL_DEFINITIONAL_SUFFIXES:
        if normalized.endswith(f" {suf}") or normalized == suf:
            return False

    # Pharmaceutical prescription / medication questions belong to TREATMENT_REQUEST
    if any(p in normalized for p in ("thuoc gi", "uong thuoc gi", "dung thuoc gi", "ke don", "mua thuoc gi", "uong thuoc tay", "dung thuoc tay")):
        return False
    if "uong thuoc" in normalized or "dung thuoc" in normalized:
        if "thuoc nam" not in normalized and "thuoc bac" not in normalized:
            return False

    # Indicator reduction / treatment actions belong to TREATMENT_REQUEST
    if any(p in normalized for p in (
        "ha chi so", "giam chi so", "cai thien chi so", "cai thien ket qua",
        "uong gi de giam", "uong gi de ha", "lam gi de giam", "lam gi de ha",
        "uong gi giam", "uong gi ha",
    )):
        return False

    has_pronoun = _TREATMENT_PRONOUN_RE.search(normalized) is not None
    has_advice_indicator = (
        has_pronoun
        or any(token in normalized for token in ("nen", "co nen", "phai", "duoc khong", "co duoc khong", "co the"))
        or any(frame in normalized for frame in ("an gi de", "uong gi de", "lam sao de", "lam gi de", "an gi bo", "uong gi bo", "kieng an gi", "an gi ha", "uong gi ha", "kieng gi"))
    )
    if not has_advice_indicator:
        return False

    has_diet_verb = any(_contains_phrase_norm(normalized, v) for v in _DIET_SUPPLEMENT_VERBS)
    has_food_item = any(_contains_phrase_norm(normalized, item) for item in _DIET_FOOD_ITEMS)
    has_health_goal = any(_contains_phrase_norm(normalized, goal) for goal in _HEALTH_TARGET_GOALS)

    from src.orchestrator.medical_context import extract_explicit_analyte
    has_explicit_analyte = extract_explicit_analyte(original_lower) is not None

    if (has_diet_verb or has_food_item) and (has_health_goal or has_explicit_analyte):
        return True

    if has_food_item and (has_advice_indicator or has_diet_verb):
        return True

    if any(q in normalized for q in (
        "an gi de", "uong gi de", "an gi bo mau", "an gi tang mau", "kieng an gi",
        "nen kieng an gi", "nen kieng gi", "nen an gi", "nen uong gi",
        "bo sung sat", "bo sung vitamin", "uong thuoc nam", "dung thuoc nam",
        "uong thuoc bac", "dung thuoc bac"
    )):
        return True

    return False


def treatment_followup_gate(message: str, session: object) -> ReasonCode | None:
    """CHAT-V1.5-R1-G4 layer 2: elevate ambiguous action follow-ups to
    TREATMENT_REQUEST only when an authenticated active report/analyte
    context exists. Without active context this gate never fires, so the
    bare sentence alone can never manufacture a medical safety refusal."""
    has_active_context = getattr(session, "current_report_ref", None) is not None or getattr(
        session, "current_analyte", None
    ) is not None
    if not has_active_context:
        return None
    if _is_ambiguous_treatment_followup(_normalize(message)):
        return ReasonCode.TREATMENT_REQUEST
    return None


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

    # 3. Personal diet, supplement, medication & medical advice requests
    if _matches_personal_medical_advice_form(normalized, original_lower):
        return ReasonCode.PERSONAL_MEDICAL_ADVICE

    # 4. Treatment requests & rapid indicator reduction advice
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

    # 4b. CHAT-V1.5-R1-G4 layer 1: form-based detection. Context-free
    # classification requires the message to carry its own medical anchor;
    # broad action forms without one are left unclassified here and may only
    # be elevated to safety by treatment_followup_gate with session context.
    if _matches_treatment_request_form(normalized, original_lower):
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


# --- CHAT-V1.5-R1-G1: provenance / source follow-up detection ---------------
#
# A patient asking where an explanation comes from ("Thông tin này dựa trên
# đâu?", "Nguồn nào nói vậy?") must reach ONE canonical approved-source path
# instead of being re-routed to EXPLAIN_CURRENT_RESULT or generic
# SAFE_GENERAL. Detection is form-based and context-free: the QUESTION SHAPE
# asks for stored provenance. Combined explain+provenance messages ("Giải
# thích ... và cho em biết thông tin này dựa trên đâu") stay on the single-
# analyte explanation path, which already attaches its own approved sources.

_PROVENANCE_FRAMES = (
    "dua tren dau",
    "dua tren nguon",
    "dua vao dau",
    "lay tu nguon",
    "lay tu dau",
    "tu nguon nao",
    "tu nguon gi",
    "nguon nao",
    "nguon gi",
    "nguon dau",
    "nguon tham khao",
    "nguon o dau",
    "co nguon khong",
    "nguon cua nguong",
    "nguon cua phan giai",
    "nguon cua thong tin",
    "nguon nay la cua",
    "to chuc nao",
    "can cu nao",
    "theo who",
    "co phai who",
    "who khong",
    "theo cdc",
    "co phai cdc",
    "cdc khong",
)

# Combined explanation requests keep the explanation path; they are never
# intercepted as bare provenance follow-ups. The possessive noun phrase
# "phần giải thích" (= "phan giai thich") is itself a provenance TARGET, so
# only explain cues outside that phrase count as combined requests.


def is_provenance_request(message: str) -> bool:
    """CHAT-V1.5-R1-G1: deterministic provenance follow-up form detection."""
    normalized = _normalize(message)
    # "phan giai thich" mentions the explanation as a source target, not an
    # explanation request; any other "giai thich" marks a combined request.
    if re.search(r"(?<!phan )giai thich", normalized):
        return False
    return any(frame in normalized for frame in _PROVENANCE_FRAMES)


# --- VMEC-05 TIP-P0-SAFETY-002: Emergency / Urgent Symptom Gate ---------------
#
# Detects acute emergency symptoms, distress pleas, and urgent symptom action
# requests deterministically BEFORE ordinary intent routing or context
# resolution.
#
# Criteria:
# 1. Distinguish personal symptom reporting / acute distress from educational,
#    definitional, or lab-analyte correlation questions.
# 2. Never allow active lab context (e.g. HGB/RBC) to hijack or continue
#    an urgent symptom turn.
# 3. Short-circuit directly with ReasonCode.EMERGENCY_INPUT_SAFETY.

_EMERGENCY_DISTRESS_PLEAS = (
    "cap cuu",
    "cuu toi voi",
    "cuu em voi",
    "cuu voi",
    "cuu toi",
    "cuu em",
    "cuu nguoi",
    "goi cap cuu",
    "can cap cuu gap",
    "cap cuu khan cap",
    "cap cuu gap",
    "nguy kich qua",
    "khan cap",
)

_URGENT_RESPIRATORY_SYMPTOMS = (
    "kho tho",
    "ngat tho",
    "ngop tho",
    "nghet tho",
    "tho gap",
    "tho doc",
    "khong tho duoc",
    "khong tho noi",
    "ngung tho",
    "dung tho",
    "hut hoi",
)

_URGENT_CARDIAC_CHEST_SYMPTOMS = (
    "dau nguc",
    "dau tim",
    "tuc nguc",
    "nang nguc",
    "that nguc",
    "dau that nguc",
    "dau nhoi nguc",
    "dau tuc nguc",
    "nhoi tim",
)

_URGENT_NEURO_CONSCIOUSNESS_SYMPTOMS = (
    "ngat xiu",
    "bat tinh",
    "hon me",
    "co giat",
    "dot quy",
    "tai bien",
    "liet nua nguoi",
    "meo mieng",
    "mat y thuc",
)

_URGENT_BLEEDING_HEMORRHAGE_SYMPTOMS = (
    "non ra mau",
    "oi ra mau",
    "ho ra mau",
    "chay mau o at",
    "chay mau khong cam",
    "chay mau xoi xa",
    "mat mau nhieu",
    "soc phan ve",
)

_URGENT_POISONING_SYMPTOMS = (
    "ngo doc cap",
    "uong nham thuoc",
    "uong nham hoa chat",
    "ngo doc thuoc",
)

_ALL_URGENT_SYMPTOMS = (
    _URGENT_RESPIRATORY_SYMPTOMS
    + _URGENT_CARDIAC_CHEST_SYMPTOMS
    + _URGENT_NEURO_CONSCIOUSNESS_SYMPTOMS
    + _URGENT_BLEEDING_HEMORRHAGE_SYMPTOMS
    + _URGENT_POISONING_SYMPTOMS
)

_CATASTROPHIC_ACUTE_CONDITIONS = (
    "ngat xiu",
    "bat tinh",
    "hon me",
    "co giat",
    "dot quy",
    "tai bien",
    "liet nua nguoi",
    "meo mieng",
    "non ra mau",
    "oi ra mau",
    "ho ra mau",
    "chay mau khong cam",
    "chay mau o at",
    "uong nham thuoc",
    "uong nham hoa chat",
    "soc phan ve",
)

_EMERGENCY_PRONOUN_RE = re.compile(
    r"\b(?:toi|em|minh|chung toi|bac|ong|ba|me|bo|cha|con|chau|nguoi nha|ban toi|chong|vo)\b"
)
_EMERGENCY_STATE_VERBS = (
    "bi", "dang", "dang bi", "thay", "cam thay", "len con", "bi len con",
    "khoi phat", "co bieu hien", "co trieu chung", "vua bi", "nha toi bi", "tu dung bi",
)
_EMERGENCY_ACTION_FRAMES = (
    "nen lam gi", "phai lam gi", "can lam gi", "phai lam sao", "nen lam sao",
    "lam gi bay gio", "lam the nao", "lam sao de", "lam gi de", "phai xu ly sao",
    "xu ly the nao", "cach xu ly", "cap cuu the nao", "co sao khong",
)
_EMERGENCY_SEVERITY_MODIFIERS = (
    "du doi", "du lam", "qua", "rat nhieu", "o at", "khong tho duoc",
    "khong tho noi", "khong cam duoc", "khong ngung", "nguy kich", "cap",
    "don dap", "quan quai", "nhoi", "that lai", "kho chiu qua", "nang qua",
)

_EDUCATIONAL_DEFINITIONAL_SUFFIXES = (
    "la gi", "nghia la gi", "la sao", "la nhu the nao",
)
_EDUCATIONAL_REFERENCE_MARKERS = (
    "tai lieu noi", "sach y hoc", "sach bao", "bai viet noi", "tim hieu ve",
    "nguyen nhan gay", "nguyen nhan cua", "co che gay", "co che cua",
    "giai thich ve trieu chung", "dinh nghia", "the nao la",
    "co phai dau hieu", "dau hieu cua", "trieu chung cua", "bieu hien cua",
    "co phai bieu hien", "dau hieu benh", "bieu hien benh", "bieu hien cho thay",
    "co phai la trieu chung", "la dau hieu cua",
)
_EDUCATIONAL_CORRELATION_MARKERS = (
    "co lien quan", "lien quan toi", "lien quan den", "co gay", "co lam",
    "co dan den", "tai sao lai gay", "tai sao gay", "vi sao gay", "tai sao lam",
)


def _is_educational_or_non_personal(normalized: str, raw_message: str) -> bool:
    """Detect purely educational, definitional, or theoretical queries."""
    # 1. Definitional questions: "khó thở nghĩa là gì?", "đột quỵ là gì?"
    tokens = normalized.split()
    if not tokens:
        return False
    for suffix in _EDUCATIONAL_DEFINITIONAL_SUFFIXES:
        if normalized.endswith(f" {suffix}") or normalized == suffix:
            return True
        if f" {suffix} " in normalized:
            return True

    # 2. Reference / literature / educational causation: "tài liệu nói khó thở là sao?"
    if any(marker in normalized for marker in _EDUCATIONAL_REFERENCE_MARKERS):
        return True

    # 3. Lab analyte theoretical correlation: "HGB thấp có liên quan tới khó thở không?"
    from src.orchestrator.medical_context import extract_explicit_analyte
    has_analyte = (
        extract_explicit_analyte(raw_message) is not None
        or any(term in normalized for term in ("hgb", "rbc", "wbc", "glucose", "hba1c", "creatinine", "plt", "thieu mau", "tieu duong"))
    )
    if has_analyte:
        has_correlation = any(corr in normalized for corr in _EDUCATIONAL_CORRELATION_MARKERS)
        has_personal_active = (
            "dang bi" in normalized
            or "toi dang" in normalized
            or "em dang" in normalized
            or "du doi" in normalized
            or "o at" in normalized
            or "nen lam gi" in normalized
            or "phai lam sao" in normalized
            or any(plea in normalized for plea in _EMERGENCY_DISTRESS_PLEAS)
        )
        if has_correlation and not has_personal_active:
            return True

    return False


def emergency_safety_gate(message: str) -> ReasonCode | None:
    """VMEC-05 TIP-P0-SAFETY-002: Deterministic emergency & urgent symptom gate.
    
    Detects personal acute symptom reports and emergency distress pleas BEFORE
    ordinary intent routing and session context resolution.
    """
    normalized = _normalize(message)
    if not normalized:
        return None

    # Check educational / non-personal exclusions first
    if _is_educational_or_non_personal(normalized, message):
        return None

    # 1. Distress pleas & emergency exclamation (e.g. "cấp cứu", "cứu tôi với")
    if any(_contains_phrase_norm(normalized, plea) for plea in _EMERGENCY_DISTRESS_PLEAS):
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    # 2. Check for presence of any urgent symptom
    matched_symptoms = [
        symptom for symptom in _ALL_URGENT_SYMPTOMS
        if _contains_phrase_norm(normalized, symptom)
    ]
    if not matched_symptoms:
        return None

    has_pronoun = _EMERGENCY_PRONOUN_RE.search(normalized) is not None
    has_state_verb = any(_contains_phrase_norm(normalized, verb) for verb in _EMERGENCY_STATE_VERBS)
    has_action_frame = any(frame in normalized for frame in _EMERGENCY_ACTION_FRAMES)
    has_severity_modifier = any(_contains_phrase_norm(normalized, sev) for sev in _EMERGENCY_SEVERITY_MODIFIERS)

    # Frame 1: Personal reporting (e.g. "tôi bị khó thở", "tôi đang khó thở", "tôi đau ngực dữ dội")
    if has_pronoun and (has_state_verb or has_severity_modifier or has_action_frame):
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    # Frame 2: Action frame + symptom (e.g. "tôi bị khó thở nên làm gì", "khó thở nên làm gì", "đau ngực phải làm sao")
    if has_action_frame:
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    # Frame 3: Severity modifier + symptom (e.g. "khó thở quá", "đau ngực dữ dội", "chảy máu không cầm")
    if has_severity_modifier:
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    # Frame 4: Direct catastrophic conditions (e.g. "bị ngất xỉu", "đang co giật", "nghi đột quỵ", "nôn ra máu")
    matched_catastrophic = [
        sym for sym in _CATASTROPHIC_ACUTE_CONDITIONS
        if _contains_phrase_norm(normalized, sym)
    ]
    if matched_catastrophic:
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    # Frame 5: Simple pronoun + symptom without extra verb if unambiguous (e.g. "tôi khó thở", "em đau tim")
    if has_pronoun:
        return ReasonCode.EMERGENCY_INPUT_SAFETY

    return None

