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

# Narrow, accent-insensitive inference patterns derived from actual unsafe
# patient explanations. These intentionally target conclusions, not source
# context or deterministic critical-warning language.
INFERENCE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("Loại trừ bệnh lý từ kết quả xét nghiệm", r"\bkhong co dau hieu\b"),
    ("Loại trừ viêm/nhiễm/vấn đề y khoa", r"\bkhong co (?:viem nhiem|nhiem trung|van de)\b"),
    ("Khẳng định không triệu chứng từ kết quả xét nghiệm", r"\bkhong (?:gay|co)(?: [a-z0-9]+){0,3} trieu chung\b"),
    ("Khẳng định không ảnh hưởng từ kết quả xét nghiệm", r"\bkhong (?:gay|co)(?: [a-z0-9]+){0,5} anh huong\b"),
    ("Khẳng định miễn dịch ổn định", r"\bmien dich(?: [a-z0-9]+){0,6} on dinh\b"),
    ("Khẳng định chức năng bình thường", r"\bchuc nang(?: [a-z0-9]+){0,6} binh thuong\b"),
    ("Khẳng định sinh lý bình thường", r"\bdam bao(?: [a-z0-9]+){0,10} binh thuong\b"),
    ("Khẳng định mức tối ưu", r"\bmuc toi uu\b"),
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
    without_accents = without_accents.replace("đ", "d")
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

        normalized = " ".join(tokens)
        for label, pattern in INFERENCE_PATTERNS:
            match = re.search(pattern, normalized)
            if match:
                violations.append(SafetyViolation(f"Kiểm tra suy luận tại chỗ ({label})", match.group(0)))

        # Preserve order while avoiding duplicate evidence from overlapping checks.
        return list(dict.fromkeys(violations))
