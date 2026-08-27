"""Plain-language and patient-grounding policy for analysis explanations."""

from __future__ import annotations

import re

from src.services.medical_safety_assets import STATUS_QUALIFIERS
from src.services.safe_grounding import filter_safe_grounding_text

PLAIN_DEFINITIONS = {
    "rbc": (
        "RBC là số lượng hồng cầu trong máu. "
        "Hồng cầu có vai trò chính là giúp đưa oxy đi khắp cơ thể."
    ),
    "hgb": (
        "HGB là lượng hemoglobin trong máu. "
        "Hemoglobin là chất trong hồng cầu giúp vận chuyển oxy."
    ),
    "chloride": (
        "Chloride (clorua) là một chất điện giải trong máu. "
        "Chất điện giải giúp cơ thể giữ cân bằng nước và axit–kiềm."
    ),
    "fasting_plasma_glucose": (
        "Đường huyết lúc đói là lượng glucose trong máu sau thời gian nhịn ăn. "
        "Glucose là một nguồn năng lượng của cơ thể."
    ),
    "potassium": (
        "Potassium (kali) là một chất điện giải trong máu. "
        "Kali tham gia vào hoạt động bình thường của cơ và thần kinh."
    ),
}

_PATIENT_UNGROUNDED_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:bạn|bệnh nhân)\s+(?:đang|bị|mắc|có thể bị|có)\b",
        r"\b(?:mệt mỏi|khó thở|chóng mặt|xanh xao|nhợt nhạt|tê|buồn nôn|đau nhức|khó ngủ|táo bón|chướng bụng|co giật|hôn mê)\b",
        r"\b(?:các bệnh|bệnh lý|danh sách bệnh|liên quan đến|gặp trong).{0,100}\b(?:thiếu máu|đa hồng cầu|bệnh tim|bệnh phổi|bệnh thận|đái tháo đường)\b",
        r"\b(?:có thể do|thường do|nguyên nhân|thường gặp khi|gây ra)\b",
        r"\b(?:điều trị|kê đơn|dùng thuốc|uống thuốc|bổ sung|truyền máu|điều chỉnh lối sống)\b",
    )
)

LIMITATION_SENTENCE = (
    "Một kết quả riêng lẻ không tự xác định bệnh, nguyên nhân hoặc triệu chứng."
)


def filter_patient_education_text(text: str) -> str:
    """Keep general education while dropping ungrounded patient implications."""
    safe = filter_safe_grounding_text(text)
    segments = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+|\n+", safe) if segment.strip()]
    return " ".join(
        segment
        for segment in segments
        if not any(pattern.search(segment) for pattern in _PATIENT_UNGROUNDED_PATTERNS)
    )


def plain_definition(*, analyte_id: str, curated_description: str) -> str:
    return PLAIN_DEFINITIONS.get(analyte_id, filter_patient_education_text(curated_description))


def build_patient_explanation(
    *,
    analyte_id: str,
    name: str,
    value: object,
    unit: str,
    status: str,
    critical_status: str | None,
    is_critical: bool,
    curated_description: str,
    supplemental_text: str = "",
) -> str:
    """Compose the three-part patient contract from controlled inputs."""
    parts: list[str] = []
    definition = plain_definition(
        analyte_id=analyte_id,
        curated_description=curated_description,
    )
    if definition:
        parts.append(definition)
    if name and value is not None and unit:
        parts.append(f"Kết quả {name} là {value} {unit}.")
    effective_status = critical_status if is_critical and critical_status else status
    qualifier = STATUS_QUALIFIERS.get(effective_status)
    if qualifier:
        parts.append(qualifier)
    supplemental = filter_patient_education_text(supplemental_text)
    if supplemental and supplemental not in " ".join(parts):
        parts.append(supplemental)
    parts.append(LIMITATION_SENTENCE)
    return " ".join(parts)
