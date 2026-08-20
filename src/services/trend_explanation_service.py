from __future__ import annotations

import logging
import re
import textwrap
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from src.agents.nodes.reference_range_checker_node import get_reference_repository
from src.models.schemas import TrendExplanationResponse, TrendFilter, TrendResponse
from src.services.critical_value_service import evaluate_critical
from src.services.llm import get_llm
from src.services.medical_safety_validator import MedicalSafetyValidator
from src.services.reference_repository import ReferenceRepositoryError
from src.services.request_timing import add_timing_event
from src.services.trend_service import get_patient_trend, get_report_patient_snapshot

logger = logging.getLogger(__name__)

TREND_EXPLANATION_FALLBACK = (
    "Biểu đồ trên thể hiện các giá trị xét nghiệm đã được ghi nhận theo thời gian. "
    "Phần giải thích tự động hiện không khả dụng; bạn có thể sử dụng biểu đồ này khi trao đổi với bác sĩ."
)

# ADR-010 CRIT-TREND-03: cảnh báo cố định, không do LLM sinh ra — luôn hiển thị khi
# điểm mới nhất đã đạt hoặc đang tiến gần ngưỡng nguy kịch, bất kể LLM có khả dụng hay
# bị guardrail chặn hay không. Không đi qua validate_trend_explanation vì đây không
# phải nội dung model sinh ra.
CONTACT_DOCTOR_NOTICE = (
    "Chỉ số này đang ở mức cần chú ý đặc biệt — vui lòng liên hệ bác sĩ sớm để được tư vấn kịp thời."
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


def strip_units(text: str, units: list[str | None]) -> str:
    """Bỏ đơn vị khỏi text trước khi quét số — hỗ trợ nhiều chỉ số cùng lúc.

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

    for unit in units:
        if not unit:
            continue
        # Khớp linh hoạt khoảng trắng giữa các ký tự của đơn vị.
        pattern = r"\s*".join(re.escape(char) for char in unit if not char.isspace())
        if pattern:
            cleaned = re.sub(pattern, " ", cleaned, flags=re.IGNORECASE)

    return _SCIENTIFIC_UNIT_RE.sub(" ", cleaned)


def _strip_unit_mentions(text: str, unit: str | None) -> str:
    return strip_units(text, [unit])


def collect_allowed_numbers(
    trends: list[TrendResponse],
    *,
    extras: list[list[float | None]] | None = None,
) -> set[str]:
    """ADR-010 CRIT-TREND-05: whitelist mở rộng cho một hay nhiều trend.

    Với mỗi trend: giá trị/ngày/đếm điểm sẵn có. ``extras`` mang thêm, cho mỗi
    trend, các số backend đã tính và xác thực: cận khoảng tham chiếu đã khớp theo
    sex/age, cận ngưỡng nguy kịch active, và % biến động giữa hai lần đo gần nhất.
    Model chỉ được LẶP LẠI các số này, không được tự tính hay tự bịa số khác.

    Ở chế độ nhóm (CRIT-TREND-07), kết quả là **hợp** của whitelist từng chỉ số —
    model được nói số của đúng chỉ số mà câu đang đề cập, nhưng vẫn không được
    gộp số của hai chỉ số thành một phép tính mới.

    Lưu ý các số đếm vô hại {0, 1, 2} và {3, 5} được cho phép sẵn: "3 kết quả gần
    nhất", "5 điểm", "1 tháng", "2 lần đo" là từ nối tự nhiên của model chứ không
    phải số liệu xét nghiệm — chặn chúng tạo lỗi "lúc được lúc không" như trường
    hợp đơn vị khoa học của WBC. Con số lâm sàng bịa vẫn bị chặn (vd "tăng 8%").
    """
    allowed = {"0", "1", "2", "3", "5"}
    for trend in trends:
        allowed.update({str(len(trend.points)), str(trend.result_count)})
        for point in trend.points:
            allowed.update(_decimal_variants(point.value))
            year, month, day = point.test_date.isoformat().split("-")
            allowed.update({year, str(int(month)), month, str(int(day)), day})
    for extra in extras or ():
        for value in extra:
            if value is None:
                continue
            allowed.update(_decimal_variants(value))
    return allowed


def scan_fabricated_numbers(text: str, allowed: set[str], units: list[str | None]) -> list[str]:
    """Trả các token số xuất hiện trong ``text`` nhưng không nằm trong whitelist.

    Bỏ đơn vị (kể cả đơn vị khoa học) của tất cả chỉ số trước khi quét; đây là bước
    dùng chung cho validator đơn chỉ số và validator nhóm.
    """
    scannable = strip_units(text, units)
    return [token for token in re.findall(r"\d+(?:[.,]\d+)?", scannable) if token not in allowed]


def _allowed_numbers(trend: TrendResponse, *, extra: list[float | None] | None = None) -> set[str]:
    """Wrapper đơn chỉ số của ``collect_allowed_numbers`` (CRIT-TREND-05)."""
    return collect_allowed_numbers([trend], extras=[extra] if extra else None)


# ADR-010 CRIT-TREND-01: từ vựng bị cấm tuyệt đối, mở rộng ngoài blacklist chẩn
# đoán/liều dùng/dự đoán tương lai đã có trong MedicalSafetyValidator.
_RESTRICTED_PATTERNS: dict[str, str] = {
    "Dự đoán xu hướng": r"\b(dự đoán|du doan|forecast|lần tới|lan toi|kết quả tiếp theo|ket qua tiep theo)\b",
    "Suy diễn tương lai": r"\b(sẽ đạt|se dat|có thể đạt|co the dat|có thể lên|co the len)\b",
    "Suy diễn nguy cơ": r"\b(nguy cơ|nguy co|dấu hiệu của|dau hieu cua|đáng lo ngại|dang lo ngai)\b",
    "Khuyến nghị xét nghiệm/thăm khám thêm": (
        r"\b(xét nghiệm thêm|xet nghiem them|nên đi khám|nen di kham|cần đi khám|can di kham|"
        r"nên gặp bác sĩ|nen gap bac si)\b"
    ),
    # ADR-010 amendment 2026-08-19 (CRIT-TREND-07): kết luận lâm sàng từ tổ hợp
    # chỉ số trong một nhóm — ranh giới "chẩn đoán theo nhóm" của Business Description.
    "Kết luận lâm sàng theo nhóm": (
        r"\b(sự kết hợp này cho thấy|su ket hop nay cho thay|nhóm chỉ số này nghĩa là|"
        r"nhom chi so nay nghia la|hội chứng chuyển hóa|hoi chung chuyen hoa)\b"
    ),
}


def validate_trend_explanation(
    text: str,
    trend: TrendResponse,
    *,
    extra_allowed_numbers: list[float | None] | None = None,
) -> list[TrendExplanationViolation]:
    violations = [
        TrendExplanationViolation(violation.mechanism, violation.evidence)
        for violation in MedicalSafetyValidator().validate(text)
    ]
    lowered = text.casefold()
    for label, pattern in _RESTRICTED_PATTERNS.items():
        if re.search(pattern, lowered):
            violations.append(TrendExplanationViolation(label, pattern))

    allowed = _allowed_numbers(trend, extra=extra_allowed_numbers)
    for token in scan_fabricated_numbers(text, allowed, [trend.canonical_unit]):
        violations.append(TrendExplanationViolation("Số không có trong dữ liệu trend", token))
    return list(dict.fromkeys(violations))


def validate_section_explanation(
    text: str,
    trends: list[TrendResponse],
    *,
    extra_allowed_numbers: list[list[float | None]] | None = None,
) -> list[TrendExplanationViolation]:
    """ADR-010 CRIT-TREND-07: kiểm duyệt giải thích theo nhóm chức năng.

    Cùng khung an toàn như validator đơn chỉ số, nhưng whitelist là **hợp** của mọi
    chỉ số trong nhóm (CRIT-TREND-05 amendment) và đơn vị được bỏ ra cho tất cả
    chỉ số. Banned vocabulary bao gồm cả kết luận lâm sàng theo nhóm.
    """
    violations = [
        TrendExplanationViolation(violation.mechanism, violation.evidence)
        for violation in MedicalSafetyValidator().validate(text)
    ]
    lowered = text.casefold()
    for label, pattern in _RESTRICTED_PATTERNS.items():
        if re.search(pattern, lowered):
            violations.append(TrendExplanationViolation(label, pattern))

    allowed = collect_allowed_numbers(trends, extras=extra_allowed_numbers)
    units = [trend.canonical_unit for trend in trends]
    for token in scan_fabricated_numbers(text, allowed, units):
        violations.append(TrendExplanationViolation("Số không có trong dữ liệu trend", token))
    return list(dict.fromkeys(violations))


def _parse_bound(value: object) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(Decimal(text))
    except InvalidOperation:
        return None


def matched_reference_bounds(db: Session, trend: TrendResponse) -> tuple[float | None, float | None]:
    """ADR-010 CRIT-TREND-02: khớp khoảng tham chiếu theo sex/age tại lần đo gần nhất.

    Dùng đúng snapshot giới tính/tuổi mà pipeline chính đã dùng cho lần đo đó
    (``lab_reports.patient_gender_at_test`` / ``patient_age_at_test``), không phải hồ sơ
    hiện tại của bệnh nhân. Không khớp được (chưa hỗ trợ, thiếu dữ liệu, sai đơn vị...)
    thì trả về (None, None) — bên gọi không được đưa ra nhận định "trong khoảng/vượt
    ngưỡng" nào trong trường hợp đó.
    """
    if not trend.points:
        return None, None
    gender, age = get_report_patient_snapshot(db, report_id=trend.points[-1].report_id)
    if gender is None:
        return None, None
    try:
        repository = get_reference_repository()
    except ReferenceRepositoryError:
        return None, None
    result = repository.select_rule(
        analyte=trend.analyte_canonical,
        unit=trend.canonical_unit,
        patient_gender=gender,
        patient_age=age,
    )
    if not result.matched or not result.rule:
        return None, None
    return _parse_bound(result.rule.get("range_lower")), _parse_bound(result.rule.get("range_upper"))


def critical_threshold_bounds(trend: TrendResponse) -> tuple[float | None, float | None]:
    """ADR-010 CRIT-TREND-03/05: cận ngưỡng nguy kịch active, chỉ khi cần escalate.

    Dùng lại ``critical_value_service.evaluate_critical`` — cùng module mà
    ``trend_service`` đã dùng để set ``critical_status``/``approaching_critical`` — để
    tránh hai nơi tính hai kết quả lệch nhau.
    """
    if not (trend.critical_status or trend.approaching_critical) or not trend.points:
        return None, None
    latest = trend.points[-1]
    evaluation = evaluate_critical(trend.analyte_canonical, latest.value, trend.canonical_unit)
    low = float(evaluation.active_low[0]) if evaluation.active_low else None
    high = float(evaluation.active_high[0]) if evaluation.active_high else None
    return low, high


def _percent_change(trend: TrendResponse) -> tuple[float | None, str | None]:
    """ADR-010 CRIT-TREND-04: % biến động giữa 2 lần đo gần nhất, tính ở backend.

    Trả về (độ lớn tuyệt đối đã làm tròn 1 chữ số thập phân, hướng "tăng"/"giảm").
    Model chỉ lặp lại số này, không tự tính — nếu để model tự tính, guardrail không
    còn cách nào phân biệt số thật với số bịa.
    """
    if len(trend.points) < 2:
        return None, None
    latest, previous = trend.points[-1].value, trend.points[-2].value
    if previous == 0:
        return None, None
    change = round(abs((latest - previous) / previous * 100), 1)
    direction = "tăng" if latest > previous else "giảm" if latest < previous else "không đổi"
    if direction == "không đổi":
        return 0.0, direction
    return change, direction


def _trend_prompt(
    trend: TrendResponse,
    *,
    range_bounds: tuple[float | None, float | None] = (None, None),
    pct_change: float | None = None,
    pct_direction: str | None = None,
    critical_bounds: tuple[float | None, float | None] = (None, None),
) -> str:
    point_lines = "\n".join(
        f"- {point.test_date.isoformat()}: {point.value} {trend.canonical_unit}, trạng thái {point.assessment}"
        for point in trend.points
    )
    values = [point.value for point in trend.points]
    latest = trend.points[-1]
    previous = trend.points[-2]

    range_lower, range_upper = range_bounds
    if range_lower is not None or range_upper is not None:
        range_section = (
            f"Khoảng tham chiếu đã khớp theo giới tính/độ tuổi bệnh nhân tại lần đo gần nhất: "
            f"{range_lower if range_lower is not None else 'không giới hạn dưới'} - "
            f"{range_upper if range_upper is not None else 'không giới hạn trên'} {trend.canonical_unit}. "
            "Bạn ĐƯỢC PHÉP nói giá trị gần nhất nằm trong khoảng, đã vượt ngưỡng trên/dưới, hay đang tiến "
            "gần ngưỡng trên/dưới của khoảng này — chỉ dùng đúng hai số trên, không tự đổi số."
        )
    else:
        range_section = (
            "Chưa khớp được khoảng tham chiếu theo giới tính/độ tuổi bệnh nhân cho chỉ số này — "
            "TUYỆT ĐỐI KHÔNG được nói giá trị 'trong khoảng tham chiếu' hay 'đã vượt ngưỡng' dưới bất kỳ hình thức nào."
        )

    pct_section = ""
    if pct_change is not None and pct_direction is not None:
        change_phrase = (
            f"{pct_direction} {pct_change}%"
            if pct_direction != "không đổi"
            else f"không có biến động ({pct_change}%)"
        )
        pct_section = (
            f"\nMức biến động giữa lần gần nhất và lần ngay trước: {change_phrase} "
            "(số do backend tính sẵn — chỉ được lặp lại nguyên số này, không được tự tính lại)."
        )

    critical_low, critical_high = critical_bounds
    critical_section = ""
    if critical_low is not None or critical_high is not None:
        critical_section = (
            f"\nNgưỡng nguy kịch của chỉ số này: thấp "
            f"{critical_low if critical_low is not None else 'không áp dụng'} / cao "
            f"{critical_high if critical_high is not None else 'không áp dụng'} {trend.canonical_unit}. "
            "Giá trị gần nhất đã đạt hoặc đang tiến gần một trong hai ngưỡng này — nêu đúng dữ kiện vị trí "
            "so với ngưỡng bằng các số đã cho. KHÔNG tự thêm mức độ nghiêm trọng, KHÔNG khuyến nghị hành động "
            "y tế (hệ thống sẽ tự thêm khuyến cáo liên hệ bác sĩ ở nơi khác, bạn không cần viết câu đó)."
        )

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

        {range_section}{pct_section}{critical_section}

        Nhiệm vụ: viết MỘT đoạn ngắn tiếng Việt, dễ hiểu cho bệnh nhân, chỉ được ghép các
        dạng câu sau (bỏ dạng nào không có dữ liệu tương ứng ở trên):
        1. Vị trí so với khoảng tham chiếu, chỉ dùng số cận đã cho ở trên.
        2. Mức biến động giữa hai lần đo gần nhất, chỉ dùng số phần trăm đã cho ở trên.
        3. Hướng đi tổng thể của chuỗi: tăng dần, giảm dần, dao động, hay ổn định tương đối.
        Quy tắc bắt buộc:
        - Không chẩn đoán bệnh, không kết luận tình trạng sức khỏe.
        - Không suy đoán nguyên nhân.
        - Không suy diễn mức độ nguy cơ hay ý nghĩa lâm sàng ngoài dữ kiện đã cho.
        - Không khuyến nghị thuốc, điều trị, xét nghiệm thêm hoặc hành động y khoa.
        - Không dự đoán giá trị tương lai.
        - Không tạo số, ngày hoặc đơn vị ngoài dữ liệu đã cung cấp ở trên.
        - Không thêm từ nối số đếm/khoảng thời gian tự đặt như "1 tháng", "1 ngày", "2 lần đo",
          "khoảng 3 tuần" — chỉ nói đến dữ liệu các lần đo, không đo khoảng cách thời gian.
        - Không viết disclaimer.
        Chỉ trả về đoạn giải thích, không bullet list.
        """
    )


def _with_escalation_notice(text: str, *, escalate: bool) -> str:
    if not escalate:
        return text
    return f"{CONTACT_DOCTOR_NOTICE} {text}".strip()


def _extract_text_content(content: object) -> str:
    """Rút phần text hiển thị từ ``response.content`` của model.

    langchain trả content dạng ``str`` (model cũ) hoặc list content block
    (gemini mới): ``[{'type': 'text', 'text': '...', 'extras': {'signature':
    '...'}}]``. Nếu dùng ``str(response.content)`` thì signature/provider
    metadata lọt vào text; chữ số ngẫu nhiên trong đó khiến guardrail chặn
    nhầm cả câu trả lời đúng (fallback "không khả dụng" dù model trả nội dung
    hợp lệ). Cùng mẫu với ``_visible_text_content`` trong guardrail_node.py.
    """
    if isinstance(content, str):
        return content

    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return "\n".join(text_parts).strip()


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

    escalate = bool(trend.critical_status or trend.approaching_critical)
    range_lower, range_upper = matched_reference_bounds(db, trend)
    pct_change, pct_direction = _percent_change(trend)
    critical_low, critical_high = critical_threshold_bounds(trend)
    extra_allowed = [range_lower, range_upper, pct_change, critical_low, critical_high]

    try:
        llm = get_llm()
    except Exception as exc:
        logger.error("Trend explanation LLM unavailable: %s", exc)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="PROVIDER_UNAVAILABLE",
        )

    prompt = _trend_prompt(
        trend,
        range_bounds=(range_lower, range_upper),
        pct_change=pct_change,
        pct_direction=pct_direction,
        critical_bounds=(critical_low, critical_high),
    )

    started_at = time.perf_counter()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text = _extract_text_content(response.content).strip()
    except Exception as exc:
        add_timing_event(
            "trend-explanation-call",
            (time.perf_counter() - started_at) * 1000,
            outcome="error",
            target=analyte_canonical,
        )
        logger.error("Trend explanation failed for %s: %s", analyte_canonical, exc)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
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
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="EMPTY_OUTPUT",
        )

    violations = validate_trend_explanation(text, trend, extra_allowed_numbers=extra_allowed)
    if violations:
        logger.warning("Trend explanation blocked: %s\nBlocked text: %s", violations, text)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="GUARDRAIL_BLOCKED",
        )

    return TrendExplanationResponse(
        explanation=_with_escalation_notice(text, escalate=escalate),
        fallback=False,
    )
