"""Bộ test đối kháng cho giải thích xu hướng THEO NHÓM chức năng
(ADR-010 CRIT-TREND-07 amendment 2026-08-19).

Đối chiếu với Business Description `nhan-xet-phan-tich-xh.docx`: bệnh nhân được phép
đọc các chỉ số cùng nhóm và hiểu quan hệ dữ kiện ("HbA1c và LDL-C cùng tăng"), nhưng
không được suy ra kết luận lâm sàng từ tổ hợp ("chẩn đoán theo nhóm"). File này khoá
từng ranh giới allow/deny bằng test.
"""

from datetime import date

from src.models.schemas import TrendPointResponse, TrendResponse
from src.services.trend_explanation_service import validate_section_explanation


def _ldl() -> TrendResponse:
    return TrendResponse(
        analyte_canonical="LDL-C",
        display_name="LDL-C",
        canonical_unit="mmol/L",
        filter="latest5",
        result_count=3,
        trend_available=True,
        points=[
            TrendPointResponse(report_id=1, test_date=date(2026, 8, 1), value=2.1, assessment="normal"),
            TrendPointResponse(report_id=2, test_date=date(2026, 8, 2), value=2.3, assessment="normal"),
            TrendPointResponse(report_id=3, test_date=date(2026, 8, 3), value=2.6, assessment="normal"),
        ],
    )


def _fpg() -> TrendResponse:
    return TrendResponse(
        analyte_canonical="Fasting plasma glucose",
        display_name="Fasting plasma glucose",
        canonical_unit="mmol/L",
        filter="latest5",
        result_count=3,
        trend_available=True,
        points=[
            TrendPointResponse(report_id=11, test_date=date(2026, 8, 1), value=5.0, assessment="normal"),
            TrendPointResponse(report_id=12, test_date=date(2026, 8, 2), value=5.3, assessment="normal"),
            TrendPointResponse(report_id=13, test_date=date(2026, 8, 3), value=5.6, assessment="normal"),
        ],
    )


def _wbc() -> TrendResponse:
    return TrendResponse(
        analyte_canonical="WBC",
        display_name="WBC",
        canonical_unit="10^9/L",
        filter="latest5",
        result_count=3,
        trend_available=True,
        points=[
            TrendPointResponse(report_id=21, test_date=date(2026, 8, 1), value=7.0, assessment="normal"),
            TrendPointResponse(report_id=22, test_date=date(2026, 8, 2), value=7.2, assessment="normal"),
            TrendPointResponse(report_id=23, test_date=date(2026, 8, 3), value=7.4, assessment="normal"),
        ],
    )


# --- CRIT-TREND-07 dạng câu được phép ------------------------------------------


def test_section_allows_co_direction_and_all_above_range():
    text = "LDL-C và FPG cùng tăng qua các lần đo; cả hai đều vượt ngưỡng trên của khoảng tham chiếu."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert violations == []


def test_section_allows_divergence_between_analytes():
    text = "LDL-C tăng trong khi FPG giảm."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert violations == []


# --- CRIT-TREND-05 amendment: hợp whitelist ------------------------------------


def test_section_union_whitelist_allows_numbers_of_any_included_analyte():
    ldl, fpg = _ldl(), _fpg()
    text = (
        "LDL-C và FPG cùng tăng; giá trị gần nhất của LDL-C là 2.6 và của FPG là 5.6 mmol/L, "
        "cả hai nằm trong khoảng tham chiếu 2.0 - 3.0 và 3.9 - 5.6 mmol/L."
    )

    violations = validate_section_explanation(
        text,
        [ldl, fpg],
        extra_allowed_numbers=[
            [2.0, 3.0, None, None, None],
            [3.9, 5.6, None, None, None],
        ],
    )

    assert violations == []


def test_section_blocks_a_figure_formed_by_combining_two_analytes():
    text = "LDL-C 2.6 cộng FPG 5.6 bằng 8.2, một con số mới."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert any(v.evidence == "8.2" for v in violations)


def test_section_number_of_an_analyte_not_in_union_is_still_blocked():
    text = "LDL-C đang ở mức 9.9 mmol/L."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert any(v.evidence == "9.9" for v in violations)


def test_section_strips_scientific_units_of_any_included_analyte():
    text = "WBC dao động quanh 7.2 10^9/L trong khi LDL-C tăng."

    violations = validate_section_explanation(text, [_ldl(), _wbc()])

    assert violations == []


def test_section_allows_benign_count_words_like_one_month():
    """ADR-010 CRIT-TREND-05 amendment: số đếm vô hại {0,1,2} không phải số liệu
    lâm sàng — model hay nói '1 tháng', '2 lần đo' — nên được cho phép (fix lỗi
    'lúc được lúc không' tương tự WBC). Con số bịa khác vẫn bị chặn."""

    text = "Trong 1 tháng gần nhất, LDL-C và FPG cùng tăng qua 2 lần đo."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert violations == []


def test_section_still_blocks_fabricated_measurement_numbers():
    text = "LDL-C và FPG cùng tăng 9% so với lần đo trước."

    violations = validate_section_explanation(text, [_ldl(), _fpg()])

    assert any(v.evidence == "9" for v in violations)


# --- CRIT-TREND-07: cấm kết luận lâm sàng theo nhóm ----------------------------


def test_section_blocks_combined_clinical_conclusion_language():
    text = "Sự kết hợp này cho thấy bạn có nguy cơ tim mạch."

    assert validate_section_explanation(text, [_ldl(), _fpg()])


def test_section_blocks_group_meaning_language():
    text = "Nhóm chỉ số này nghĩa là bạn có nguy cơ tim mạch."

    assert validate_section_explanation(text, [_ldl(), _fpg()])


def test_section_blocks_metabolic_syndrome_phrase():
    text = "Các chỉ số này cho thấy hội chứng chuyển hóa."

    assert validate_section_explanation(text, [_ldl(), _fpg()])


def test_section_blocks_group_diagnosis_even_with_grounded_numbers():
    """Mọi số đều grounded nhưng kết luận lâm sàng từ tổ hợp vẫn bị chặn (CRIT-TREND-07.4)."""
    text = "Sự kết hợp LDL-C 2.6 và FPG 5.6 cho thấy nguy cơ tim mạch."

    assert validate_section_explanation(text, [_ldl(), _fpg()])


def test_section_blocks_single_analyte_diagnosis_language():
    text = "LDL-C cao chứng tỏ bạn mắc bệnh mỡ máu."

    assert validate_section_explanation(text, [_ldl(), _fpg()])
