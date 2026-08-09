"""Deterministic, local medical-language validator used by the guardrail.

It combines the existing regex blacklist with accent-insensitive intent rules.
The intent rules operate on normalized tokens, so variants such as ``ke thuoc``
or ``bạn nên sử dụng loại thuốc`` are caught without a model or network call.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

RESTRICTED_PATTERNS = (
    r"chẩn đoán bạn bị",
    r"bạn mắc bệnh",
    r"chắc chắn bị",
    r"kê đơn",
    r"uống thuốc",
    r"dùng thuốc",
    r"phẫu thuật",
    r"liều lượng",
    r"điều trị bằng",
    r"bạn đang bị",
    r"chữa khỏi",
    r"có thể do",
    r"nguyên nhân do",
    r"thường liên quan đến",
    r"do ảnh hưởng của",
)


@dataclass(frozen=True)
class SafetyViolation:
    mechanism: str
    evidence: str

    def describe(self) -> str:
        return f"{self.mechanism}: '{self.evidence}'"


def _normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _contains_phrase(tokens: list[str], phrase: tuple[str, ...]) -> bool:
    width = len(phrase)
    return any(tuple(tokens[index : index + width]) == phrase for index in range(len(tokens) - width + 1))


class MedicalSafetyValidator:
    """Run regex and local intent checks and return every detected violation."""

    _intent_phrases: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("Khẳng định chẩn đoán", ("ban", "mac", "benh")),
        ("Khẳng định chẩn đoán", ("ban", "dang", "bi")),
        ("Khẳng định chẩn đoán", ("chac", "chan", "bi")),
        ("Chỉ định dùng thuốc", ("hay", "uong", "thuoc")),
        ("Chỉ định dùng thuốc", ("nen", "uong", "thuoc")),
        ("Chỉ định dùng thuốc", ("can", "dung", "thuoc")),
        ("Chỉ định dùng thuốc", ("nen", "su", "dung", "thuoc")),
        ("Kê đơn", ("ke", "don")),
        ("Kê đơn", ("ke", "thuoc")),
        ("Liều dùng cụ thể", ("lieu", "dung")),
        ("Suy đoán nguyên nhân", ("co", "the", "do")),
        ("Suy đoán nguyên nhân", ("nguyen", "nhan", "la", "do")),
        ("Suy đoán nguyên nhân", ("thuong", "lien", "quan", "den")),
    )

    def validate(self, text: str) -> list[SafetyViolation]:
        if not text or not text.strip():
            return []

        violations: list[SafetyViolation] = []
        lowered = text.casefold()
        for pattern in RESTRICTED_PATTERNS:
            if re.search(pattern, lowered):
                violations.append(SafetyViolation("Regex", pattern))

        tokens = _normalize(text).split()
        for label, phrase in self._intent_phrases:
            if _contains_phrase(tokens, phrase):
                violations.append(SafetyViolation(f"Kiểm tra ý định tại chỗ ({label})", " ".join(phrase)))

        # Preserve order while avoiding duplicate evidence from overlapping checks.
        return list(dict.fromkeys(violations))
