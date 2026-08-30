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
from src.services.trend_claims import (
    REFERENCE_NEAR_MARGIN_RATIO,
    TrendClaim,
    TrendClaimSet,
    TrendPointReferenceFact,
    build_claim_set,
    classify_reference_position,
    compose_deterministic_explanation,
    decimal_variants,
    format_claims_for_prompt,
    format_point_reference_facts,
    percent_change,
    point_reference_extra_numbers,
    reference_relation_text,
    validate_claims,
)
from src.services.trend_service import get_patient_trend, get_report_patient_snapshot

# Bí danh giữ nguyên đường import cũ sau khi lớp dữ kiện tách sang ``trend_claims``.
_decimal_variants = decimal_variants
_classify_reference_position = classify_reference_position
_reference_relation_text = reference_relation_text
_percent_change = percent_change

__all__ = [
    "CONTACT_DOCTOR_NOTICE",
    "REFERENCE_NEAR_MARGIN_RATIO",
    "TREND_EXPLANATION_FALLBACK",
    "TrendClaim",
    "TrendClaimSet",
    "TrendExplanationUnavailableError",
    "TrendExplanationViolation",
    "TrendPointReferenceFact",
    "build_claim_set",
    "build_point_reference_facts",
    "collect_allowed_numbers",
    "critical_threshold_bounds",
    "explain_patient_trend",
    "format_point_reference_facts",
    "matched_reference_bounds",
    "point_reference_extra_numbers",
    "scan_fabricated_numbers",
    "strip_units",
    "validate_section_explanation",
    "validate_trend_explanation",
]

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


class TrendExplanationUnavailableError(ValueError):
    pass


@dataclass(frozen=True)
class TrendExplanationViolation:
    reason: str
    evidence: str


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
    claims: list[TrendClaim] | tuple[TrendClaim, ...] | None = None,
) -> list[TrendExplanationViolation]:
    """Kiểm duyệt giải thích đơn chỉ số.

    Bốn lớp: từ vựng y khoa cấm, từ vựng ADR-010 cấm, số bịa, và — khi bên gọi
    truyền ``claims`` — mâu thuẫn ngữ nghĩa với dữ kiện backend đã chốt. Lớp cuối là
    lớp duy nhất bắt được lỗi model đảo hướng ("giảm 33.3%" khi backend tính ra
    "tăng 33.3%"), vì lỗi đó không sinh ra con số mới nào.
    """
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

    for reason, evidence in validate_claims(text, claims or ()):
        violations.append(TrendExplanationViolation(reason, evidence))
    return list(dict.fromkeys(violations))


def validate_section_explanation(
    text: str,
    trends: list[TrendResponse],
    *,
    extra_allowed_numbers: list[list[float | None]] | None = None,
    claims: list[TrendClaim] | tuple[TrendClaim, ...] | None = None,
) -> list[TrendExplanationViolation]:
    """ADR-010 CRIT-TREND-07: kiểm duyệt giải thích theo nhóm chức năng.

    Cùng khung an toàn như validator đơn chỉ số, nhưng whitelist là **hợp** của mọi
    chỉ số trong nhóm (CRIT-TREND-05 amendment) và đơn vị được bỏ ra cho tất cả
    chỉ số. Banned vocabulary bao gồm cả kết luận lâm sàng theo nhóm.

    ``claims`` là hợp claim của mọi chỉ số trong nhóm. Bên gọi phải neo claim hình
    dạng chuỗi theo tên chỉ số (``build_claim_set(..., shape_anchor=...)``), vì ở
    chế độ nhóm "A tăng dần trong khi B dao động" là câu hợp lệ.
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

    for reason, evidence in validate_claims(text, claims or ()):
        violations.append(TrendExplanationViolation(reason, evidence))
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


def _matched_reference_bounds_for_report(
    db: Session,
    trend: TrendResponse,
    *,
    report_id: int,
) -> tuple[float | None, float | None]:
    gender, age = get_report_patient_snapshot(db, report_id=report_id)
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
    return _matched_reference_bounds_for_report(db, trend, report_id=trend.points[-1].report_id)


def build_point_reference_facts(db: Session, trend: TrendResponse) -> list[TrendPointReferenceFact]:
    """Classify each trend point against its own sex/age-matched reference range."""
    facts: list[TrendPointReferenceFact] = []
    for point in trend.points:
        lower, upper = _matched_reference_bounds_for_report(db, trend, report_id=point.report_id)
        facts.append(
            TrendPointReferenceFact(
                report_id=point.report_id,
                test_date=point.test_date.isoformat(),
                value=point.value,
                lower=lower,
                upper=upper,
                relation=classify_reference_position(point.value, lower, upper),
            )
        )
    return facts


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


def _trend_prompt(
    trend: TrendResponse,
    *,
    claim_sentences: tuple[str, ...] | list[str],
    point_reference_facts: list[TrendPointReferenceFact] | None = None,
    critical_bounds: tuple[float | None, float | None] = (None, None),
) -> str:
    """Prompt "chỉ diễn đạt lại".

    Trước đây prompt cấp dữ liệu thô rồi liệt kê 4 *dạng câu* và để model tự chọn
    nhãn cho từng dạng — nghĩa là chính model quyết định "tăng hay giảm", "trong hay
    ngoài khoảng tham chiếu", "tăng dần hay dao động". Ba lỗi trong ca WBC đều sinh
    ra ở bước đó. Giờ backend chốt sẵn từng câu, model chỉ còn việc viết lại cho mượt.

    ``point_lines`` cũng bỏ trường ``assessment`` của từng phiếu: nó là nguồn nhãn
    HIGH/LOW/NORMAL thứ hai (do OCR/analyzer gán) đặt cạnh nhãn tính từ khoảng tham
    chiếu, và khi hai nguồn lệch nhau model chọn tùy ý.
    """
    point_lines = "\n".join(
        f"- {point.test_date.isoformat()}: {point.value} {trend.canonical_unit}" for point in trend.points
    )
    point_reference_section = format_point_reference_facts(point_reference_facts or [], trend.canonical_unit)

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
        Bạn là trợ lý diễn đạt lại kết quả phân tích xu hướng xét nghiệm cho bệnh nhân đọc.

        Chỉ số: {trend.display_name}
        Đơn vị: {trend.canonical_unit}
        Số điểm: {len(trend.points)}
        Các điểm theo thời gian:
        {point_lines}

        Phân loại từng điểm so với khoảng tham chiếu đã khớp theo giới tính/độ tuổi bệnh nhân:
        {point_reference_section}{critical_section}

        NHẬN ĐỊNH ĐÃ CHỐT — backend đã tính và kiểm chứng, đây là toàn bộ nội dung bạn được nói:
        {format_claims_for_prompt(claim_sentences)}

        Nhiệm vụ: viết lại CHÍNH XÁC các nhận định trên thành một đoạn tiếng Việt liền mạch, dễ
        hiểu cho bệnh nhân. Bạn chỉ được đổi cách hành văn.
        Quy tắc bắt buộc:
        - Giữ nguyên mọi nhận định: không bỏ bớt, không thêm nhận định mới, không đảo ý.
        - Hướng biến động (tăng/giảm/không đổi) và vị trí so với khoảng tham chiếu (trong khoảng /
          vượt cận trên / dưới cận dưới) phải giữ ĐÚNG như đã chốt ở trên. Đây là lỗi bị chặn
          thường xuyên nhất — đọc kỹ lại trước khi viết.
        - Không tự phân loại lại hình dạng chuỗi. Nếu ở trên ghi "dao động" thì không được viết
          "tăng dần" hay "giảm dần", và ngược lại.
        - Không tạo số, ngày hoặc đơn vị ngoài các nhận định đã chốt và bảng dữ liệu ở trên.
        - Không chẩn đoán bệnh, không kết luận tình trạng sức khỏe, không suy đoán nguyên nhân.
        - Không suy diễn mức độ nguy cơ hay ý nghĩa lâm sàng ngoài dữ kiện đã cho.
        - Không khuyến nghị thuốc, điều trị, xét nghiệm thêm hoặc hành động y khoa.
        - Không dự đoán giá trị tương lai.
        - Có thể gọi các ngày vượt/dưới/gần cận là "điểm cần chú ý trên biểu đồ", nhưng không tự
          suy ra bệnh, nguy cơ, nguyên nhân hoặc hướng xử trí.
        - Không thêm từ nối số đếm/khoảng thời gian tự đặt như "1 tháng", "1 ngày", "2 lần đo",
          "khoảng 3 tuần" — chỉ nói đến dữ liệu các lần đo, không đo khoảng cách thời gian.
        - Không viết disclaimer.
        Chỉ trả về 2 đến 4 câu văn liền mạch, không bullet list.
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
        raise TrendExplanationUnavailableError("Trend chưa đủ dữ liệu để tạo giải thích.")

    escalate = bool(trend.critical_status or trend.approaching_critical)
    range_lower, range_upper = matched_reference_bounds(db, trend)
    point_reference_facts = build_point_reference_facts(db, trend)
    pct_change, _pct_direction = percent_change(trend)
    critical_low, critical_high = critical_threshold_bounds(trend)
    extra_allowed = [
        range_lower,
        range_upper,
        pct_change,
        critical_low,
        critical_high,
        *point_reference_extra_numbers(point_reference_facts),
    ]

    # Backend chốt toàn bộ nhận định TRƯỚC khi gọi model: cùng một bộ câu vừa dựng
    # prompt, vừa làm chuẩn đối chiếu output, vừa làm nội dung dự phòng.
    claim_set = build_claim_set(trend, point_reference_facts)
    deterministic = compose_deterministic_explanation(claim_set.sentences)

    def _fallback(reason: str) -> TrendExplanationResponse:
        """Dự phòng bằng chính câu backend đã soạn, không phải câu 'không khả dụng'.

        Không đi qua ``validate_trend_explanation``: đây không phải nội dung model
        sinh ra, cùng nguyên tắc với ``CONTACT_DOCTOR_NOTICE``.
        """
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(deterministic or TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason=reason,
        )

    try:
        llm = get_llm()
    except Exception as exc:
        logger.error("Trend explanation LLM unavailable: %s", exc)
        return _fallback("PROVIDER_UNAVAILABLE")

    prompt = _trend_prompt(
        trend,
        claim_sentences=claim_set.sentences,
        point_reference_facts=point_reference_facts,
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
        return _fallback("PROVIDER_ERROR")

    add_timing_event(
        "trend-explanation-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target=analyte_canonical,
    )
    if not text:
        return _fallback("EMPTY_OUTPUT")

    violations = validate_trend_explanation(
        text,
        trend,
        extra_allowed_numbers=extra_allowed,
        claims=claim_set.claims,
    )
    if violations:
        logger.warning("Trend explanation blocked: %s\nBlocked text: %s", violations, text)
        return _fallback("GUARDRAIL_BLOCKED")

    return TrendExplanationResponse(
        explanation=_with_escalation_notice(text, escalate=escalate),
        fallback=False,
    )
