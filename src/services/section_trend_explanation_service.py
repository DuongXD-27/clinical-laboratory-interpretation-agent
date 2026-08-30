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
from src.services.trend_claims import (
    build_claim_set,
    compose_deterministic_explanation,
    format_claims_for_prompt,
    format_point_reference_facts,
    merge_claims,
    percent_change,
    point_reference_extra_numbers,
)
from src.services.trend_explanation_service import (
    CONTACT_DOCTOR_NOTICE,
    TREND_EXPLANATION_FALLBACK,
    TrendExplanationUnavailableError,
    build_point_reference_facts,
    _extract_text_content,
    critical_threshold_bounds,
    matched_reference_bounds,
    validate_section_explanation,
)
from src.services.trend_service import get_patient_trend, get_patient_trend_analytes

logger = logging.getLogger(__name__)

SECTION_KEYS = frozenset({HEMATOLOGY, CHEMISTRY, LIPIDS})


def _fact_block(trend) -> str:
    """Block dữ kiện của một chỉ số, giống dữ liệu đơn chỉ số (CRIT-TREND-02/04/05).

    Bỏ ``assessment`` của từng phiếu vì lý do như ở luồng đơn chỉ số: đó là nguồn nhãn
    HIGH/LOW/NORMAL thứ hai đặt cạnh nhãn tính từ khoảng tham chiếu, và khi hai nguồn
    lệch nhau model chọn tùy ý.
    """
    point_lines = "\n".join(
        f"- {point.test_date.isoformat()}: {point.value} {trend.canonical_unit}" for point in trend.points
    )

    lines = [
        f"Chỉ số: {trend.display_name}",
        f"Đơn vị: {trend.canonical_unit}",
        f"Số điểm: {len(trend.points)}",
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

        point_reference_facts = fact["point_reference_facts"]
        block += (
            "\nPhân loại từng điểm so với khoảng tham chiếu đã khớp theo từng ngày:\n"
            f"{format_point_reference_facts(point_reference_facts, trend.canonical_unit)}"
        )

        block += (
            f"\nNHẬN ĐỊNH ĐÃ CHỐT cho {trend.display_name} — đây là toàn bộ nội dung bạn được nói "
            "về chỉ số này:\n"
            f"{format_claims_for_prompt(fact['claim_set'].sentences)}"
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
        Bạn là trợ lý diễn đạt lại kết quả phân tích xu hướng xét nghiệm theo nhóm chức năng.

        Nhóm chức năng: {section_label(section)}

        Dữ liệu và nhận định từng chỉ số dưới đây đã được backend tính và kiểm chứng. KHÔNG được
        sửa, không được thêm số/ngày mới. Mọi câu về một chỉ số phải lấy nội dung từ đúng block
        của chỉ số đó:

        {chr(10).join(blocks)}

        Nhiệm vụ: viết lại các nhận định đã chốt ở trên thành MỘT đoạn ngắn tiếng Việt liền mạch,
        giúp bệnh nhân đọc các chỉ số trong nhóm CÙNG NHAU. Bạn chỉ được đổi cách hành văn và
        được nối các chỉ số lại bằng những câu quan hệ sau:
        1. Cùng chiều: "[A] và [B] cùng tăng/giảm/ổn định qua các lần đo."
        2. Vị trí chung: "Cả [A] và [B] đều nằm trong khoảng tham chiếu." / "...đều vượt cận trên."
        3. Trái chiều: "[A] tăng trong khi [B] giảm."
        Câu quan hệ chỉ được nói lại đúng những gì các nhận định đã chốt nói; không được suy ra
        quan hệ mới.
        Quy tắc bắt buộc:
        - Giữ nguyên mọi nhận định đã chốt: không bỏ bớt, không thêm nhận định mới, không đảo ý.
        - Hướng biến động (tăng/giảm/không đổi) và vị trí so với khoảng tham chiếu của TỪNG chỉ số
          phải giữ ĐÚNG như đã chốt. Không tự phân loại lại hình dạng chuỗi của bất kỳ chỉ số nào.
        - Mọi số phải lấy từ block của đúng chỉ số mà câu đang nói đến; KHÔNG gộp số của hai chỉ số
          thành một phép tính.
        - Không kết luận tình trạng sức khỏe hay bệnh từ tổ hợp chỉ số. Không dùng: "sự kết hợp này cho thấy",
          "nhóm chỉ số này nghĩa là", "nguy cơ tim mạch", "hội chứng chuyển hóa".
        - Không chẩn đoán, không suy đoán nguyên nhân, không dự đoán giá trị tương lai.
        - Không khuyến nghị thuốc, điều trị, xét nghiệm thêm hoặc hành động y khoa.
        - Có thể gọi các ngày vượt/dưới/gần cận là "điểm cần chú ý trên biểu đồ", nhưng không tự
          suy ra bệnh, nguy cơ, nguyên nhân hoặc hướng xử trí.
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
    claim_groups: list[tuple] = []
    deterministic_parts: list[str] = []
    for trend in trends:
        range_lower, range_upper = matched_reference_bounds(db, trend)
        point_reference_facts = build_point_reference_facts(db, trend)
        pct_change, _pct_direction = percent_change(trend)
        critical_low, critical_high = critical_threshold_bounds(trend)
        # Neo nhãn hình dạng chuỗi theo tên chỉ số: ở chế độ nhóm, "A tăng dần trong
        # khi B dao động" là câu hợp lệ, nên không thể soi toàn đoạn như luồng đơn
        # chỉ số — chỉ những câu có nhắc tên chỉ số mới bị đối chiếu.
        claim_set = build_claim_set(trend, point_reference_facts, shape_anchor=trend.display_name)
        claim_groups.append(claim_set.claims)
        deterministic_parts.append(f"{trend.display_name}: {compose_deterministic_explanation(claim_set.sentences)}")
        facts.append(
            {
                "point_reference_facts": point_reference_facts,
                "claim_set": claim_set,
                "critical_low": critical_low,
                "critical_high": critical_high,
            }
        )
        extra_allowed.append(
            [
                range_lower,
                range_upper,
                pct_change,
                critical_low,
                critical_high,
                *point_reference_extra_numbers(point_reference_facts),
            ]
        )

    claims = merge_claims(claim_groups)
    deterministic = " ".join(deterministic_parts).strip()

    def _fallback(reason: str) -> TrendExplanationResponse:
        """Dự phòng bằng chính câu backend đã soạn cho từng chỉ số trong nhóm."""
        return TrendExplanationResponse(
            explanation=_with_escalation_notice(deterministic or TREND_EXPLANATION_FALLBACK, escalate=escalate),
            fallback=True,
            reason=reason,
        )

    prompt = _group_prompt(section, trends, facts=facts)

    try:
        llm = get_llm()
    except Exception as exc:
        logger.error("Section trend explanation LLM unavailable: %s", exc)
        return _fallback("PROVIDER_UNAVAILABLE")

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
        return _fallback("PROVIDER_ERROR")

    add_timing_event(
        "section-trend-explanation-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target=section,
    )
    if not text:
        return _fallback("EMPTY_OUTPUT")

    violations = validate_section_explanation(
        text,
        trends,
        extra_allowed_numbers=extra_allowed,
        claims=claims,
    )
    if violations:
        logger.warning("Section trend explanation blocked: %s\nBlocked text: %s", violations, text)
        return _fallback("GUARDRAIL_BLOCKED")

    return TrendExplanationResponse(
        explanation=_with_escalation_notice(text, escalate=escalate),
        fallback=False,
    )
