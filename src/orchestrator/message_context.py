"""Deterministic parsing of analyte and report references in chat messages."""

from __future__ import annotations

import re
import unicodedata
from datetime import date

from src.services.analyte_resolver import LOCKED_35_ANALYTES
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

_REPORT_REF_PATTERNS = (
    re.compile(r"(?:phiếu|kết quả|báo cáo|lần khám)\s*(?:số|xét nghiệm)?\s*#?\s*(\d+)", re.IGNORECASE),
    re.compile(r"#\s*(\d+)"),
)
_REPORT_DATE_PATTERNS = (
    re.compile(r"(?:phiếu|kết quả|báo cáo).*?\b(\d{1,2})[/-](\d{1,2})[/-](\d{4})\b", re.IGNORECASE),
    re.compile(r"(?:phiếu|kết quả|báo cáo).*?\b(\d{4})-(\d{1,2})-(\d{1,2})\b", re.IGNORECASE),
)

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


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-zA-Z0-9À-ỹ]+", text.casefold()))


def _normalize_no_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def extract_explicit_analyte(message: str) -> str | None:
    normalized = _normalize(message)
    try:
        repository = ReferenceRepository.from_default_files()
        aliases = sorted(repository.analyte_aliases.items(), key=lambda item: len(item[0]), reverse=True)
        for alias, canonical in aliases:
            token = _normalize(alias)
            if token and re.search(rf"\b{re.escape(token)}\b", normalized):
                return canonical
    except ReferenceRepositoryError:
        pass

    for alias, canonical in sorted(_COMMON_ALIAS_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        if re.search(rf"\b{re.escape(alias)}\b", normalized):
            return canonical
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
            return date(third, second, first) if index == 0 else date(first, second, third)
        except ValueError:
            return None
    return None


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


def _is_referential_analyte(normalized: str) -> bool:
    return any(cue in normalized for cue in REFERENTIAL_ANALYTE_CUES) or bool(re.search(r"\bno\b", normalized))


__all__ = [
    "extract_explicit_analyte",
    "extract_explicit_report_date",
    "extract_explicit_report_ref",
]
