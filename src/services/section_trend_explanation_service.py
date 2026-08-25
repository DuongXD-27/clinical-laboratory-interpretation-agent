"""Group-level trend explanation for a functional section (ADR-010 CRIT-TREND-07).

One section explanation covers every ``trend_available`` analyte of one functional
section so the patient can read the indicators **together** (e.g. the lipid/HbA1c
group) and learn the factual relationships between them — never a combined clinical
conclusion. This service reuses the single-analyte fact helpers so the two flows
cannot diverge, and validates the output with the union allowed-number set.
"""

from __future__ import annotations

import logging
import textwrap
import time

from langchain_core.messages import HumanMessage
from sqlalchemy.orm import Session

from src.models.schemas import TrendExplanationResponse, TrendFilter
from src.services.analyte_sections import CHEMISTRY, HEMATOLOGY, LIPIDS, section_label
from src.services.llm import get_llm
from src.services.request_timing import add_timing_event
from src.services.trend_explanation_service import (
    CONTACT_DOCTOR_NOTICE,
    TREND_EXPLANATION_FALLBACK,
    TrendExplanationUnavailableError,
    _extract_text_content,
    _percent_change,
    critical_threshold_bounds,
    matched_reference_bounds,
    validate_section_explanation,
)
from src.services.trend_service import get_patient_trend, get_patient_trend_analytes

logger = logging.getLogger(__name__)

SECTION_KEYS = frozenset({HEMATOLOGY, CHEMISTRY, LIPIDS})


def _fact_block(trend) -> str:
    """Block dữ kiện của một chỉ số, giống dữ liệu đơn chỉ số (CRIT-TREND-02/04/05)."""
    point_lines = "\n".join(
        f"- {point.test_date.isoformat()}: {point.value} {trend.canonical_unit}, trạng thái {point.assessment}"
        for point in trend.points
    )
    values = [point.value for point in trend.points]
    latest = trend.points[-1]
    previous = trend.points[-2]

    lines = [
        f"Chỉ số: {trend.display_name}",
        f"Đơn vị: {trend.canonical_unit}",
        f"Số điểm: {len(trend.points)}",
        f"Giá trị đầu tiên: {trend.points[0].value}",
        f"Giá trị gần nhất: {latest.value}",
        f"Giá trị ngay trước đó: {previous.value}",
        f"Giá trị thấp nhất: {min(values)}",
        f"Giá trị cao nhất: {max(values)}",
        "Các điểm theo thời gian:",
        point_lines,
    ]
    return "\n".join(lines)


def _group_prompt(
    section: str,
    trends: list,
    *,
    facts: list[dict],
) -> str:
    """Prompt giải thích nhóm: block dữ kiện từng chỉ số + dạng câu liên chỉ số.

    Các cận tham chiếu/% biến động/ngưỡng nguy kịch được thêm vào block của đúng
    chỉ số đó, và cũng được đưa vào hợp whitelist (CRIT-TREND-05 amendment).
    """
    blocks: list[str] = []
    for trend, fact in zip(trends, facts):
        block = _fact_block(trend)
        range_lower, range_upper = fact["range_lower"], fact["range_upper"]
        if range_lower is not None or range_upper is not None:
            block += (
                f"\nKhoảng tham chiếu khớp theo giới tính/độ tuổi tại lần đo gần nhất: "
                f"{range_lower if range_lower is not None else 'không giới hạn dưới'} - "
                f"{range_upper if range_upper is not None else 'không giới hạn trên'} {trend.canonical_unit}. "
                "Bạn ĐƯỢC PHÉP nói giá trị gần nhất nằm trong khoảng, đã vượt ngưỡng trên/dưới, hay đang "
                "tiến gần ngưỡng của khoảng này — chỉ dùng đúng hai số trên, không tự đổi số."
            )
        else:
            block += (
                "\nChưa khớp được khoảng tham chiếu theo giới tính/độ tuổi cho chỉ số này — "
                "TUYỆT ĐỐI KHÔNG được nói giá trị 'trong khoảng tham chiếu' hay 'đã vượt ngưỡng'."
            )

        pct_change, pct_direction = fact["pct_change"], fact["pct_direction"]
        if pct_change is not None and pct_direction is not None:
            change_phrase = (
                f"{pct_direction} {pct_change}%"
                if pct_direction != "không đổi"
                else f"không có biến động ({pct_change}%)"
            )
            block += (
                f"\nMức biến động giữa lần gần nhất và lần ngay trước: {change_phrase} "
                "(số do backend tính sẵn — chỉ được lặp lại nguyên số này, không được tự tính lại)."
            )

        critical_low, critical_high = fact["critical_low"], fact["critical_high"]
        if critical_low is not None or critical_high is not None:
            block += (
                f"\nNgưỡng nguy kịch của chỉ số này: thấp "
                f"{critical_low if critical_low is not None else 'không áp dụng'} / cao "
                f"{critical_high if critical_high is not None else 'không áp dụng'} {trend.canonical_unit}. "
                "Giá trị gần nhất đã đạt hoặc đang tiến gần một trong hai ngưỡng này — nêu đúng dữ kiện vị trí "
                "so với ngưỡng bằng các số đã cho. KHÔNG tự thêm mức độ nghiêm trọng, KHÔNG khuyến nghị hành "
                "động y tế."
            )

        blocks.append(block)

    return textwrap.dedent(
        f"""\
        Bạn là trợ lý giải thích xu hướng xét nghiệm theo nhóm chức năng cho mục đích giáo dục.

        Nhóm chức năng: {section_label(section)}

        Dữ liệu từng chỉ số dưới đây đã được backend xác thực. KHÔNG được sửa, không được thêm số/ngày mới.
        Mọi số trong câu của một chỉ số phải lấy từ đúng block của chỉ số đó:

        {chr(10).join(blocks)}

        Nhiệm vụ: viết MỘT đoạn ngắn tiếng Việt, dễ hiểu cho bệnh nhân, giúp đọc các chỉ số trong nhóm
        CÙNG NHAU. Chỉ được ghép các dạng câu sau (bỏ dạng nào không có dữ liệu tương ứng ở trên):
        1. Quan hệ cùng chiều giữa các chỉ số: "[Chỉ số A] và [Chỉ số B] cùng tăng/giảm/ổn định qua các lần đo."
        2. Vị trí chung so với khoảng tham chiếu: "Cả [A] và [B] trong nhóm đều vượt ngưỡng trên của khoảng tham chiếu."
           hoặc "...đều nằm trong khoảng tham chiếu."
        3. Quan hệ trái chiều: "[A] tăng trong khi [B] giảm."
        4. Mức biến động của từng chỉ số giữa hai lần đo gần nhất, chỉ dùng số phần trăm đã cho của đúng chỉ số đó.
        Quy tắc bắt buộc:
        - Mọi số phải lấy từ block của đúng chỉ số mà câu đang nói đến; KHÔNG gộp số của hai chỉ số thành một phép tính.
        - Không kết luận tình trạng sức khỏe hay bệnh từ tổ hợp chỉ số. Không dùng: "sự kết hợp này cho thấy",
          "nhóm chỉ số này nghĩa là", "nguy cơ tim mạch", "hội chứng chuyển hóa".
        - Không chẩn đoán, không suy đoán nguyên nhân, không dự đoán giá trị tương lai.
        - Không khuyến nghị thuốc, điều trị, xét nghiệm thêm hoặc hành động y khoa.
        - Không tạo số, ngày hoặc đơn vị ngoài dữ liệu đã cung cấp.
        - Không thêm từ nối số đếm/khoảng thời gian tự đặt như "1 tháng", "1 ngày", "2 lần đo",
          "khoảng 3 tuần" — chỉ nói đến dữ liệu các lần đo, không đo khoảng cách thời gian.
        - Không viết disclaimer, không liệt kê theo bullet.
        Chỉ trả về đoạn giải thích.
        """
    )


def _with_escalation_notice(text: str, *, escalate: bool) -> str:
    if not escalate:
        return text
    return f"{CONTACT_DOCTOR_NOTICE} {text}".strip()


async def explain_section_trend(
    db: Session,
    *,
    username: str,
    section: str,
    trend_filter: TrendFilter,
) -> TrendExplanationResponse:
    """Sinh giải thích xu hướng theo nhóm chức năng (ADR-010 CRIT-TREND-07).

    - Section không hợp lệ hoặc không có chỉ số đủ điểm → lỗi/fallback (không bao giờ
      hiển thị màn hình lỗi cho phần diễn giải).
    - Đúng 1 chỉ số đủ điểm → tái dùng luồng đơn chỉ số để hành vi không lệch nhau.
    """
    if section not in SECTION_KEYS:
        raise TrendExplanationUnavailableError("Nhóm chức năng không hợp lệ.")

    analytes = get_patient_trend_analytes(db, username=username)
    eligible = [item for item in analytes if item.section == section and item.trend_available]

    if len(eligible) == 1:
        from src.services.trend_explanation_service import explain_patient_trend

        return await explain_patient_trend(
            db,
            username=username,
            analyte_canonical=eligible[0].analyte_canonical,
            trend_filter=trend_filter,
        )

    if not eligible:
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="INSUFFICIENT_DATA",
        )

    trends = [
        get_patient_trend(
            db,
            username=username,
            analyte_canonical=item.analyte_canonical,
            trend_filter=trend_filter,
        )
        for item in eligible
    ]
    trends = [trend for trend in trends if trend.trend_available]
    if not trends:
        return TrendExplanationResponse(
            explanation=TREND_EXPLANATION_FALLBACK,
            fallback=True,
            reason="INSUFFICIENT_DATA",
        )
    if len(trends) == 1:
        from src.services.trend_explanation_service import explain_patient_trend

        return await explain_patient_trend(
            db,
            username=username,
            analyte_canonical=trends[0].analyte_canonical,
            trend_filter=trend_filter,
        )

    escalate = any(trend.critical_status or trend.approaching_critical for trend in trends)

    facts: list[dict] = []
    extra_allowed: list[list[float | None]] = []
    for trend in trends:
        range_lower, range_upper = matched_reference_bounds(db, trend)
        pct_change, pct_direction = _percent_change(trend)
        critical_low, critical_high = critical_threshold_bounds(trend)
        facts.append(
            {
                "range_lower": range_lower,
                "range_upper": range_upper,
                "pct_change": pct_change,
                "pct_direction": pct_direction,
                "critical_low": critical_low,
                "critical_high": critical_high,
            }
        )
        extra_allowed.append([range_lower, range_upper, pct_change, critical_low, critical_high])

    prompt = _group_prompt(section, trends, facts=facts)

    try:
        llm = get_llm()
    except Exception as exc:
        logger.error("Section trend explanation LLM unavailable: %s", exc)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="PROVIDER_UNAVAILABLE",
        )

    started_at = time.perf_counter()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        text = _extract_text_content(response.content).strip()
    except Exception as exc:
        add_timing_event(
            "section-trend-explanation-call",
            (time.perf_counter() - started_at) * 1000,
            outcome="error",
            target=section,
        )
        logger.error("Section trend explanation failed for %s: %s", section, exc)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="PROVIDER_ERROR",
        )

    add_timing_event(
        "section-trend-explanation-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target=section,
    )
    if not text:
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="EMPTY_OUTPUT",
        )

    violations = validate_section_explanation(text, trends, extra_allowed_numbers=extra_allowed)
    if violations:
        logger.warning("Section trend explanation blocked: %s\nBlocked text: %s", violations, text)
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason="GUARDRAIL_BLOCKED",
        )

    return TrendExplanationResponse(
        explanation=_with_escalation_notice(text, escalate=escalate),
        fallback=False,
    )
