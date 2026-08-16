"""Đơn vị có chứa chữ số không được coi là số bịa.

Lỗi thật, nhóm trưởng báo 16/08: phần giải thích xu hướng "lúc gọi được api key
lúc không" trên production. Không phải chuyện API key — mọi lần gọi đều tới LLM
trong ~2 giây. Thực tế là `validate_trend_explanation()` chặn câu trả lời, và log
production nói rõ token bị chặn là `10`.

Nguyên nhân: validator whitelist mọi con số được phép rồi quét mọi token số trong
câu trả lời, để model không bịa ra số liệu. Nhưng đơn vị của WBC là `10^9/L` và
của RBC là `10^12/L`. Model viết "dao động quanh 7.2 10^9/L" — hoàn toàn đúng —
thì `10` bị coi là số bịa.

Đo trên production trước khi sửa:

    Fasting plasma glucose (mmol/L)   6/6 chạy
    RBC                    (10^12/L)  1/6 bị chặn
    WBC                    (10^9/L)   6/6 bị chặn

Đúng kiểu "lúc được lúc không": nó phụ thuộc model có tình cờ nhắc đơn vị hay
không. Đơn vị `mmol/L` không có chữ số nên không bao giờ vướng.
"""

from datetime import date

import pytest

from src.models.schemas import TrendPointResponse, TrendResponse
from src.services.trend_explanation_service import (
    _strip_unit_mentions,
    validate_trend_explanation,
)


def make_trend(unit: str, values=((1, 7.2), (2, 8.1))) -> TrendResponse:
    return TrendResponse(
        analyte_canonical="WBC",
        display_name="WBC",
        canonical_unit=unit,
        filter="latest5",
        result_count=len(values),
        trend_available=True,
        points=[
            TrendPointResponse(
                report_id=index,
                test_date=date(2026, 8, day),
                value=value,
                assessment="normal",
            )
            for index, (day, value) in enumerate(values, start=1)
        ],
    )


# --- Đơn vị có chữ số phải đi qua được ---------------------------------------


@pytest.mark.parametrize(
    "unit,text",
    [
        ("10^9/L", "Ba lần đo lần lượt 7.2 và 8.1 10^9/L, dao động trong khoảng bình thường."),
        ("10^9/L", "Giá trị 7.2 x10^9/L rồi 8.1 x10^9/L."),
        ("10^9/L", "Giá trị 7.2 × 10 ^ 9 / L."),
        ("10^12/L", "Chỉ số lần lượt 7.2 và 8.1 10^12/L."),
    ],
)
def test_scientific_unit_is_not_treated_as_a_fabricated_number(unit, text):
    """Đây là ca đã làm hỏng production."""

    assert validate_trend_explanation(text, make_trend(unit)) == []


def test_unit_without_digits_behaves_as_before():
    """`mmol/L` chưa bao giờ vướng; sửa xong vẫn không được đổi hành vi."""

    trend = make_trend("mmol/L")

    assert validate_trend_explanation("Hai lần đo 7.2 và 8.1 mmol/L.", trend) == []


# --- Nhưng số bịa vẫn phải bị chặn -------------------------------------------


def test_a_number_the_model_invented_is_still_blocked():
    """Điểm quan trọng: nới cho đơn vị không được nới cho số liệu.

    Nếu chỉ thêm "10" vào whitelist thì model bịa "tăng 10%" cũng lọt. Ở đây chỉ
    chỗ nào đúng là đơn vị mới được miễn.
    """

    trend = make_trend("10^9/L")

    violations = validate_trend_explanation("Chỉ số tăng 99 phần trăm so với lần trước.", trend)

    assert [violation.evidence for violation in violations] == ["99"]


def test_a_fabricated_value_next_to_a_real_unit_is_still_blocked():
    trend = make_trend("10^9/L")

    violations = validate_trend_explanation("Giá trị đạt 12.5 10^9/L.", trend)

    assert [violation.evidence for violation in violations] == ["12.5"]


def test_real_values_and_dates_stay_allowed():
    trend = make_trend("10^9/L")

    assert validate_trend_explanation(
        "Ngày 01/08/2026 đo 7.2, ngày 02/08/2026 đo 8.1.", trend
    ) == []


# --- Hàm bỏ đơn vị -----------------------------------------------------------


def test_strip_removes_the_unit_but_keeps_the_values():
    stripped = _strip_unit_mentions("Chỉ số 7.2 và 8.1 10^9/L, ổn định.", "10^9/L")

    assert "10^9/L" not in stripped
    assert "7.2" in stripped
    assert "8.1" in stripped


def test_strip_handles_a_missing_unit():
    """`canonical_unit` rỗng không được làm hàm nổ."""

    assert _strip_unit_mentions("Chỉ số 7.2.", "") == "Chỉ số 7.2."


def test_strip_does_not_remove_a_bare_ten():
    """Chỉ bỏ đúng dạng đơn vị, không bỏ mọi chữ "10" trong câu."""

    stripped = _strip_unit_mentions("Tăng 10 lần so với ngưỡng.", "10^9/L")

    assert "10" in stripped


# --- Guardrail nội dung không bị nới lỏng ------------------------------------


def test_content_guardrail_still_blocks_prediction():
    """Bỏ đơn vị không được ảnh hưởng các luật khác của validator."""

    trend = make_trend("10^9/L")

    violations = validate_trend_explanation(
        "Chỉ số 7.2 và 8.1 10^9/L, dự đoán lần tới sẽ đạt mức cao hơn.", trend
    )

    reasons = {violation.reason for violation in violations}

    assert "Dự đoán xu hướng" in reasons
