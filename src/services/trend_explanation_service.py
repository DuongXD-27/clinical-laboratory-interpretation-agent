from __future__ import annotations

import logging
import re
import textwrap
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from src.models.schemas import TrendExplanationResponse, TrendFilter, TrendResponse
from src.services.llm import get_llm
from src.services.medical_safety_validator import MedicalSafetyValidator
from src.services.request_timing import add_timing_event
from src.services.trend_service import get_patient_trend

logger = logging.getLogger(__name__)

TREND_EXPLANATION_FALLBACK = (
    "Biểu đồ trên thể hiện các giá trị xét nghiệm đã được ghi nhận theo thời gian. "
    "Phần giải thích tự động hiện không khả dụng; bạn có thể sử dụng biểu đồ này khi trao đổi với bác sĩ."
)


class TrendExplanationUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class TrendExplanationViolation:
    reason: str
    evidence: str


def _decimal_variants(value: float | int) -> set[str]:
    raw = str(value)
    try:
        decimal_value = Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return {raw}
    normalized = format(decimal_value, "f")
    variants = {raw, raw.replace(".", ","), normalized, normalized.replace(".", ",")}
    if "." in normalized:
        variants.add(normalized.rstrip("0").rstrip("."))
        variants.add(normalized.rstrip("0").rstrip(".").replace(".", ","))
    return {item for item in variants if item}


# Đơn vị dạng khoa học, bắt cả khi model viết khác đơn vị canonical một chút:
# "10^9/L", "x10^9/L", "× 10 ^ 12 / L".
_SCIENTIFIC_UNIT_RE = re.compile(r"(?:x|×)?\s*10\s*\^\s*\d+(?:\s*/\s*\w+)?", re.IGNORECASE)


def _strip_unit_mentions(text: str, unit: str | None) -> str:
    """Bỏ đơn vị khỏi text trước khi quét số.

    Validator chặn mọi con số không có trong dữ liệu trend, để model không bịa ra
    số liệu. Nhưng **đơn vị của một số chỉ số có chứa chữ số**: WBC là `10^9/L`,
    RBC là `10^12/L`. Model viết "dao động quanh 7.2 10^9/L" — hoàn toàn đúng —
    thì `10` bị coi là số bịa và cả câu trả lời bị thay bằng mẫu dự phòng.

    Đó là nguyên nhân thật của lỗi "lúc được lúc không" báo ngày 16/08: nó phụ
    thuộc model có tình cờ nhắc đơn vị hay không. Glucose đơn vị `mmol/L` không có
    chữ số nên luôn chạy; WBC gần như lần nào cũng bị chặn.

    Bỏ đơn vị đi thay vì cho phép hẳn chữ số của nó: nếu whitelist thêm "10" thì
    model bịa "tăng 10%" cũng lọt. Ở đây chỉ chỗ nào đúng là đơn vị mới được
    miễn, phần còn lại vẫn bị soi.
    """

    cleaned = text

    if unit:
        # Khớp linh hoạt khoảng trắng giữa các ký tự của đơn vị.
        pattern = r"\s*".join(re.escape(char) for char in unit if not char.isspace())
        if pattern:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    return _SCIENTIFIC_UNIT_RE.sub(" ", cleaned)


def _allowed_numbers(trend: TrendResponse) -> set[str]:
    allowed = {"3", "5", str(len(trend.points)), str(trend.result_count)}
    for point in trend.points:
        allowed.update(_decimal_variants(point.value))
        year, month, day = point.test_date.isoformat().split("-")
        allowed.update({year, str(int(month)), month, str(int(day)), day})
    return allowed


def validate_trend_explanation(text: str, trend: TrendResponse) -> list[TrendExplanationViolation]:
    violations = [
        TrendExplanationViolation(violation.mechanism, violation.evidence)
        for violation in MedicalSafetyValidator().validate(text)
    ]
    lowered = text.casefold()
    restricted_patterns = {
        "Dự đoán xu hướng": r"\b(dự đoán|du doan|forecast|lần tới|lan toi|kết quả tiếp theo|ket qua tiep theo)\b",
        "Suy diễn tương lai": r"\b(sẽ đạt|se dat|có thể đạt|co the dat|có thể lên|co the len)\b",
    }
    for label, pattern in restricted_patterns.items():
        if re.search(pattern, lowered):
            violations.append(TrendExplanationViolation(label, pattern))

    allowed = _allowed_numbers(trend)
    scannable = _strip_unit_mentions(text, trend.canonical_unit)
    for token in re.findall(r"\d+(?:[.,]\d+)?", scannable):
        if token not in allowed:
            violations.append(TrendExplanationViolation("Số không có trong dữ liệu trend", token))
    return list(dict.fromkeys(violations))


def _trend_prompt(trend: TrendResponse) -> str:
    point_lines = "\n".join(
        f"- {point.test_date.isoformat()}: {point.value} {trend.canonical_unit}, trạng thái {point.assessment}"
        for point in trend.points
    )
    values = [point.value for point in trend.points]
    latest = trend.points[-1]
    previous = trend.points[-2]
    return textwrap.dedent(
        f"""\
        Bạn là trợ lý giải thích biểu đồ xu hướng xét nghiệm cho mục đích giáo dục.

        Dữ liệu đã được backend xác thực, KHÔNG được sửa, không được thêm số/ngày mới:
        Chỉ số: {trend.display_name}
        Đơn vị: {trend.canonical_unit}
        Số điểm: {len(trend.points)}
        Giá trị đầu tiên: {trend.points[0].value}
        Giá trị gần nhất: {latest.value}
        Giá trị ngay trước đó: {previous.value}
        Giá trị thấp nhất: {min(values)}
        Giá trị cao nhất: {max(values)}
        Các điểm theo thời gian:
        {point_lines}

        Nhiệm vụ:
        1. Viết một đoạn ngắn tiếng Việt, dễ hiểu cho bệnh nhân.
        2. Chỉ mô tả xu hướng quan sát được trong dữ liệu lịch sử ở trên.
        3. Có thể nói tăng, giảm, dao động, ổn định tương đối nếu đúng với dữ liệu.
        4. Không chẩn đoán bệnh.
        5. Không suy đoán nguyên nhân.
        6. Không khuyến nghị thuốc, điều trị, xét nghiệm thêm hoặc hành động y khoa.
        7. Không dự đoán giá trị tương lai.
        8. Không tạo số, ngày hoặc đơn vị ngoài dữ liệu đã cung cấp.
        9. Không viết disclaimer.
        Chỉ trả về đoạn giải thích, không bullet list.
        """
    )


async def explain_patient_trend(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
) -> TrendExplanationResponse:
    trend = get_patient_trend(
        db,
        username=username,
        analyte_canonical=analyte_canonical,
        trend_filter=trend_filter,
    )
    if not trend.trend_available:
        raise TrendExplanationUnavailable("Trend chưa đủ dữ liệu để tạo giải thích.")

    try:
        llm = get_llm()
    except Exception as exc:
        logger.error("Trend explanation LLM unavailable: %s", exc)
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="PROVIDER_UNAVAILABLE",
        )

    started_at = time.perf_counter()
    try:
        response = await llm.ainvoke([HumanMessage(content=_trend_prompt(trend))])
        text = str(response.content).strip()
    except Exception as exc:
        add_timing_event(
            "trend-explanation-call",
            (time.perf_counter() - started_at) * 1000,
            outcome="error",
            target=analyte_canonical,
        )
        logger.error("Trend explanation failed for %s: %s", analyte_canonical, exc)
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="PROVIDER_ERROR",
        )

    add_timing_event(
        "trend-explanation-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target=analyte_canonical,
    )
    if not text:
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="EMPTY_OUTPUT",
        )

    violations = validate_trend_explanation(text, trend)
    if violations:
        logger.warning("Trend explanation blocked: %s", violations)
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="GUARDRAIL_BLOCKED",
        )

    return TrendExplanationResponse(explanation=text, fallback=False)
