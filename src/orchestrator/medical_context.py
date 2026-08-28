"""Medical context resolver for Orchestrator V1.

Autonomous medical context retrieval layer. Resolves patient lab reports and
analytes with the following priority:
1. Explicit user mention in message
2. Conversation memory / session state
3. UIContext (low-priority untrusted hint)
4. Autonomous DB fetch (only when intent requires patient report data)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorSessionContext,
    ReasonCode,
    UIContext,
)
from src.services import history_repository
from src.services.analyte_resolver import LOCKED_35_ANALYTES
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

_COMPARISON_PATTERNS = (
    "so voi lan truoc",
    "so với lần trước",
    "compared with last time",
    "compare with last time",
)

_REPORT_REF_PATTERNS = (
    re.compile(r"(?:phiếu|kết quả|báo cáo|lần khám)\s*(?:số|xét nghiệm)?\s*#?\s*(\d+)", re.IGNORECASE),
    re.compile(r"#\s*(\d+)"),
)

_REPORT_DATE_PATTERNS = (
    re.compile(r"(?:phiếu|kết quả|báo cáo).*?\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", re.IGNORECASE),
    re.compile(r"(?:phiếu|kết quả|báo cáo).*?\b(\d{4})-(\d{1,2})-(\d{1,2})\b", re.IGNORECASE),
)

_LATEST_REPORT_CUES = ("gan nhat", "moi nhat")

_GENERIC_REPORT_DEFAULT_CUES = (
    "doc ket qua cua em",
    "doc ket qua cua toi",
    "doc ket qua cua minh",
    "ket qua cua em",
    "ket qua cua toi",
    "ket qua cua minh",
    "xem ket qua cua em",
    "xem ket qua cua toi",
    "xem ket qua cua minh",
)


@dataclass(frozen=True)
class ResolvedMedicalContext:
    current_report_ref: str | None
    current_analyte: str | None
    forced_intent: IntentEnum | None = None
    reason_code: ReasonCode | None = None


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-zA-Z0-9À-ỹ]+", text.casefold()))


_COMMON_ALIAS_MAP: dict[str, str] = {
    "glucose": "Fasting plasma glucose",
    "duong huyet": "Fasting plasma glucose",
    "duong": "Fasting plasma glucose",
    "fpg": "Fasting plasma glucose",
    "fbg": "Fasting plasma glucose",
    "cholesterol": "Total cholesterol",
    "bach cau": "WBC",
    "hong cau": "RBC",
    "huyet sac to": "HGB",
    "hemoglobin": "HGB",
    "creatinin": "Creatinine",
    "creatinine": "Creatinine",
    "hba1c": "HbA1c",
    "ldl": "LDL-C",
    "ldl c": "LDL-C",
    "ldl cholesterol": "LDL-C",
    "hdl": "HDL-C",
    "hdl c": "HDL-C",
    "hdl cholesterol": "HDL-C",
    "kali": "Potassium",
    "potassium": "Potassium",
    "acid uric": "Uric acid",
    "axit uric": "Uric acid",
    "uric acid": "Uric acid",
    "triglyceride": "Triglyceride",
    "men gan": "ALT",
}


def extract_explicit_analyte(message: str) -> str | None:
    normalized = _normalize(message)

    # 1. Try ReferenceRepository aliases if available
    try:
        repo = ReferenceRepository.from_default_files()
        for alias, canonical in sorted(repo.analyte_aliases.items(), key=lambda x: len(x[0]), reverse=True):
            token = _normalize(alias)
            if token and re.search(rf"\b{re.escape(token)}\b", normalized):
                return canonical
    except ReferenceRepositoryError:
        pass

    # 2. Try common clinical aliases map
    for alias, canonical in sorted(_COMMON_ALIAS_MAP.items(), key=lambda x: len(x[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return canonical

    # 3. Try LOCKED_35_ANALYTES
    for analyte in sorted(LOCKED_35_ANALYTES, key=len, reverse=True):
        token = _normalize(analyte)
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return analyte

    return None


def extract_explicit_report_ref(message: str) -> str | None:
    for pattern in _REPORT_REF_PATTERNS:
        match = pattern.search(message)
        if match:
            return match.group(1)
    # Check if the entire message is just an integer (e.g. follow-up answering report id)
    cleaned = message.strip()
    if cleaned.isdigit() and 0 < int(cleaned) < 100000000:
        return cleaned
    return None


def extract_explicit_report_date(message: str) -> date | None:
    for index, pattern in enumerate(_REPORT_DATE_PATTERNS):
        match = pattern.search(message)
        if not match:
            continue
        first, second, third = (int(value) for value in match.groups())
        try:
            if index == 0:
                return date(third, second, first)
            return date(first, second, third)
        except ValueError:
            return None
    return None


def _fetch_latest_patient_report(current_user: object, db: object) -> str | None:
    role = getattr(current_user, "role", None)
    if role != ROLE_PATIENT:
        return None
    actor_key = getattr(current_user, "user_id", None)
    if not isinstance(actor_key, int) or db is None:
        return None

    try:
        _, items = history_repository.list_reports(
            db,
            patient_id=actor_key,
            limit=1,
            offset=0,
        )
        if items and len(items) > 0:
            return str(items[0].id)
    except Exception:
        return None
    return None


def _fetch_patient_report_by_date(current_user: object, db: object, report_date: date) -> str | None:
    role = getattr(current_user, "role", None)
    if role != ROLE_PATIENT:
        return None
    actor_key = getattr(current_user, "user_id", None)
    if not isinstance(actor_key, int) or db is None:
        return None

    try:
        _, items = history_repository.list_reports(
            db,
            patient_id=actor_key,
            from_date=report_date,
            to_date=report_date,
            limit=1,
            offset=0,
        )
        if items:
            return str(items[0].id)
    except Exception:
        return None
    return None


def _normalize_no_accents(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


WHOLE_REPORT_CUES = (
    "tong the",
    "tong quan",
    "tat ca",
    "gan nhat",
    "gan day",
    "nhin chung",
    "ca phieu",
    "toan bo",
    "phieu nay",
    "ket qua nay",
    "co gi can chu y",
    "co gi dang chu y",
    "can chu y",
    "dang chu y",
    "co bat thuong",
    "bat thuong khong",
    "co van de",
    "the nao",
    "ra sao",
    "sao roi",
    "xem giup",
    "coi giup",
    "coi dum",
    "tom tat",
    "em hoi lo",
    "toi hoi lo",
    "lo lang",
    "co sao khong",
    "nhin chung ca phieu",
    "tong the phieu",
    "tong quan phieu",
)

REFERENTIAL_ANALYTE_CUES = (
    "chi so nay",
    "chi so do",
    "chi so ay",
    "chi so vua roi",
    "gia tri cua no",
    "gia tri hien tai cua no",
    "gia tri hien tai cua chi so nay",
    "ve chi so nay",
    "ve chi so do",
)


def _is_referential_analyte(norm_no_accents: str) -> bool:
    return any(cue in norm_no_accents for cue in REFERENTIAL_ANALYTE_CUES) or bool(
        re.search(r"\bno\b", norm_no_accents)
    )


def _single_relevant_report_analyte(
    *,
    report_ref: str | None,
    current_user: object,
    db: object,
) -> str | None:
    """Return the sole authoritative out-of-range analyte for this patient report."""
    if getattr(current_user, "role", None) != ROLE_PATIENT:
        return None
    patient_id = getattr(current_user, "user_id", None)
    if not isinstance(patient_id, int) or not report_ref or not report_ref.isdigit() or db is None:
        return None

    try:
        report = history_repository.get_report(db, int(report_ref))
    except Exception:
        return None
    if report is None or getattr(report, "patient_id", None) != patient_id:
        return None

    relevant_analytes: set[str] = set()
    for indicator in getattr(report, "indicators", ()):
        status = getattr(indicator, "status", "")
        status_value = getattr(status, "value", status)
        critical_status = getattr(indicator, "critical_status", None)
        if str(status_value).casefold() not in {"high", "low"} and not critical_status:
            continue
        analyte = getattr(indicator, "analyte_canonical", None) or getattr(indicator, "name", None)
        if isinstance(analyte, str) and analyte:
            relevant_analytes.add(analyte)

    if len(relevant_analytes) == 1:
        return next(iter(relevant_analytes))
    return None


def resolve_medical_context(
    message: str,
    session: OrchestratorSessionContext,
    ui_context: UIContext | None,
    current_user: object,
    db: object,
    intent: IntentEnum,
) -> ResolvedMedicalContext:
    # 1. Start with session state
    current_report_ref = session.current_report_ref
    current_analyte = session.current_analyte

    # 2. Apply UIContext as hint if session doesn't have it
    if ui_context is not None:
        current_report_ref = current_report_ref or ui_context.candidate_report_ref
        current_analyte = current_analyte or ui_context.candidate_analyte

    norm_no_acc = _normalize_no_accents(message)
    is_referential = _is_referential_analyte(norm_no_acc)
    is_generic_report_request = any(cue in norm_no_acc for cue in _GENERIC_REPORT_DEFAULT_CUES)

    # 3. Explicit mentions vs referential vs whole-report override
    explicit_analyte = extract_explicit_analyte(message)
    if explicit_analyte:
        current_analyte = explicit_analyte
    else:
        if is_referential and current_analyte is None:
            if intent == IntentEnum.EXPLAIN_CURRENT_RESULT and session.last_intent == IntentEnum.EXPLAIN_CURRENT_RESULT:
                current_analyte = _single_relevant_report_analyte(
                    report_ref=current_report_ref,
                    current_user=current_user,
                    db=db,
                )
            if current_analyte is None:
                return ResolvedMedicalContext(
                    current_report_ref=current_report_ref,
                    current_analyte=None,
                    reason_code=ReasonCode.AMBIGUOUS_CONTEXT,
                )
        elif not is_referential:
            is_whole_report = is_generic_report_request or any(cue in norm_no_acc for cue in WHOLE_REPORT_CUES)
            if is_whole_report:
                current_analyte = None

    previous_report_ref = current_report_ref
    explicit_report_ref = extract_explicit_report_ref(message)
    explicit_report_date = extract_explicit_report_date(message)
    if explicit_report_ref:
        current_report_ref = explicit_report_ref
    elif explicit_report_date is not None:
        current_report_ref = _fetch_patient_report_by_date(current_user, db, explicit_report_date)
    elif intent in {
        IntentEnum.ANALYZE_REPORT,
        IntentEnum.EXPLAIN_CURRENT_RESULT,
        IntentEnum.GET_DOCTOR_QUESTIONS,
    } and (is_generic_report_request or any(cue in norm_no_acc for cue in _LATEST_REPORT_CUES)):
        current_report_ref = _fetch_latest_patient_report(current_user, db)

    report_changed = current_report_ref != previous_report_ref
    if report_changed and explicit_analyte is None:
        current_analyte = None
        if is_referential:
            return ResolvedMedicalContext(
                current_report_ref=current_report_ref,
                current_analyte=None,
                reason_code=ReasonCode.AMBIGUOUS_CONTEXT,
            )

    # 4. Autonomous DB Fetch:
    # Only fetch patient's latest report when workflow requires patient data and report is missing.
    # Strictly do NOT fetch latest report for knowledge-only, SAFE_GENERAL, ANALYZE_TREND, or ANALYZE_REPORT.
    if current_report_ref is None and intent in {
        IntentEnum.EXPLAIN_CURRENT_RESULT,
        IntentEnum.GET_DOCTOR_QUESTIONS,
    }:
        latest_report_id = _fetch_latest_patient_report(current_user, db)
        if latest_report_id:
            current_report_ref = latest_report_id

    # 5. Check comparison intent override
    normalized = _normalize(message)
    asks_comparison = any(pattern in normalized for pattern in _COMPARISON_PATTERNS)
    if asks_comparison:
        return ResolvedMedicalContext(
            current_report_ref=current_report_ref,
            current_analyte=current_analyte,
            forced_intent=IntentEnum.ANALYZE_TREND,
        )

    return ResolvedMedicalContext(
        current_report_ref=current_report_ref,
        current_analyte=current_analyte,
    )
