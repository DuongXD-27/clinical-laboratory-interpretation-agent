"""Bộ test đối kháng cho ranh giới "diễn giải dữ kiện" vs "nhận định y khoa"
(ADR-010 CRIT-TREND-01), viết trước khi mở rộng prompt/guardrail — theo mẫu
`docs/audit/evidence/retrieval-min-score-evidence.md`.

Nhận xét gốc của nhóm trưởng: ranh giới này "chỉ có ví dụ minh họa, chưa có quy tắc
cụ thể". ADR-010 định nghĩa 4 dạng câu được phép và một danh sách từ vựng cấm tuyệt
đối — file này khoá lại từng câu allow/deny bằng test thay vì để lại làm ví dụ suông.
"""

from datetime import date

from src.models.schemas import TrendPointResponse, TrendResponse
from src.services.trend_explanation_service import validate_trend_explanation


def _trend(unit: str = "mmol/L", values=(2.1, 2.3, 2.6)) -> TrendResponse:
    return TrendResponse(
        analyte_canonical="LDL-C",
        display_name="LDL-C",
        canonical_unit=unit,
        filter="latest5",
        result_count=len(values),
        trend_available=True,
        points=[
            TrendPointResponse(
                report_id=index,
                test_date=date(2026, 8, index),
                value=value,
                assessment="normal",
            )
            for index, value in enumerate(values, start=1)
        ],
    )


# --- CRIT-TREND-01 dạng câu 1: vị trí so với khoảng tham chiếu -----------------


def test_allows_stating_position_within_reference_range():
    trend = _trend()
    extra = [2.0, 3.5]  # cận khoảng tham chiếu đã khớp

    violations = validate_trend_explanation(
        "LDL-C của bạn nằm trong khoảng tham chiếu 2.0 - 3.5 mmol/L.",
        trend,
        extra_allowed_numbers=extra,
    )

    assert violations == []


def test_allows_stating_value_above_reference_range_bound():
    trend = _trend()
    extra = [None, 2.58]

    violations = validate_trend_explanation(
        "LDL-C đã vượt ngưỡng trên của khoảng tham chiếu (2.58 mmol/L).",
        trend,
        extra_allowed_numbers=extra,
    )

    assert violations == []


def test_reference_range_bound_not_in_extra_is_still_blocked():
    """Nếu backend không truyền cận khoảng tham chiếu vào allowlist, model không
    được tự bịa ra một con số ngưỡng nào — kể cả khi nó nghe hợp lý."""

    trend = _trend()

    violations = validate_trend_explanation(
        "LDL-C đã vượt ngưỡng trên của khoảng tham chiếu (3.9 mmol/L).",
        trend,
    )

    assert any(v.evidence == "3.9" for v in violations)


# --- CRIT-TREND-01 dạng câu 2: % biến động giữa hai lần đo gần nhất ------------


def test_allows_stating_backend_computed_percent_change():
    trend = _trend()

    violations = validate_trend_explanation(
        "LDL-C tăng 13% so với lần xét nghiệm trước.",
        trend,
        extra_allowed_numbers=[13.0],
    )

    assert violations == []


def test_a_percent_change_the_model_computed_itself_is_blocked():
    """Model không được tự tính % — chỉ được lặp lại số backend đã cấp."""

    trend = _trend()

    violations = validate_trend_explanation(
        "LDL-C tăng 42% so với lần xét nghiệm trước.",
        trend,
        extra_allowed_numbers=[13.0],
    )

    assert any(v.evidence == "42" for v in violations)


def test_allows_stating_backend_computed_zero_percent_change():
    """Hai lần đo bằng nhau: backend tính ra 0% thật nên model được lặp lại.

    Trước đây ``_percent_change`` trả ``None`` cho case không đổi, nên model
    viết "0%" (số đúng nhưng không nằm trong whitelist) bị chặn → luôn fallback
    ở case phổ biến nhất (chỉ số ổn định).
    """

    trend = _trend()

    violations = validate_trend_explanation(
        "LDL-C không có biến động (0%) so với lần xét nghiệm trước.",
        trend,
        extra_allowed_numbers=[0.0],
    )

    assert violations == []


# --- CRIT-TREND-01 dạng câu 3: hướng đi tổng thể --------------------------------


def test_allows_overall_direction_description():
    trend = _trend()

    violations = validate_trend_explanation(
        "LDL-C có xu hướng tăng dần qua 3 lần đo.",
        trend,
    )

    assert violations == []


# --- Từ vựng cấm tuyệt đối (ADR-010 CRIT-TREND-01) -----------------------------


def test_blocks_diagnosis_language():
    trend = _trend()
    assert validate_trend_explanation("Bạn mắc bệnh mỡ máu cao.", trend)


def test_blocks_causation_inference():
    trend = _trend()
    assert validate_trend_explanation("Nguyên nhân là do ăn nhiều chất béo.", trend)


def test_blocks_risk_interpretation():
    trend = _trend()
    assert validate_trend_explanation("Điều này cho thấy nguy cơ tim mạch của bạn.", trend)
    assert validate_trend_explanation("Đây có thể là dấu hiệu của một vấn đề sức khỏe.", trend)


def test_blocks_treatment_and_lab_referral_recommendation():
    trend = _trend()
    assert validate_trend_explanation("Bạn nên dùng thuốc để hạ chỉ số này.", trend)
    assert validate_trend_explanation("Bạn nên đi khám thêm vì chỉ số này bất thường.", trend)
    assert validate_trend_explanation("Bạn cần xét nghiệm thêm để xác nhận.", trend)


def test_blocks_future_prediction():
    trend = _trend()
    assert validate_trend_explanation("Dự đoán lần xét nghiệm tới sẽ đạt mức cao hơn.", trend)


def test_blocks_any_number_outside_data_and_extra_allowlist():
    trend = _trend()
    violations = validate_trend_explanation("LDL-C của bạn khoảng 9.9 mmol/L trong tương lai gần.", trend)
    assert any(v.evidence == "9.9" for v in violations)


# --- Kết hợp nhiều dạng câu được phép cùng lúc vẫn phải sạch -------------------


def test_combination_of_allowed_sentence_shapes_passes_clean():
    trend = _trend()

    text = (
        "LDL-C của bạn nằm trong khoảng tham chiếu 2.0 - 3.5 mmol/L, "
        "tăng 13% so với lần xét nghiệm trước, và có xu hướng tăng dần qua 3 lần đo."
    )

    violations = validate_trend_explanation(text, trend, extra_allowed_numbers=[2.0, 3.5, 13.0])

    assert violations == []
