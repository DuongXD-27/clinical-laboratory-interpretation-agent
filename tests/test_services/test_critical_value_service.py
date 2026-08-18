"""Unit tests cho module ngưỡng nguy kịch dùng chung (ADR-010 CRIT-TREND-03).

`critical_detector_node.py` đã có bộ test riêng bao phủ hành vi pipeline (fail-closed,
canonicalization, alert message...) và không được đổi hành vi sau khi refactor sang
gọi `evaluate_critical`. File này test trực tiếp module chia sẻ — không qua
`AgentState`/pipeline — vì đây chính là điều kiện để `trend_service` dùng lại được nó
mà không cần LangGraph.
"""

from decimal import Decimal

from src.services.critical_value_service import (
    APPROACH_MARGIN,
    approaches_critical,
    evaluate_critical,
)
from src.services.measurement_conversion import glucose_mmol_l_to_mg_dl


def test_potassium_below_low_threshold_is_critical_low():
    evaluation = evaluate_critical("Potassium", 2.9, "mmol/L")

    assert evaluation.evaluated is True
    assert evaluation.is_critical is True
    assert evaluation.critical_status == "critical_low"
    assert evaluation.alert_message is not None


def test_potassium_above_high_threshold_is_critical_high():
    evaluation = evaluate_critical("Potassium", 6.2, "mmol/L")

    assert evaluation.is_critical is True
    assert evaluation.critical_status == "critical_high"


def test_potassium_within_range_is_evaluated_but_not_critical():
    evaluation = evaluate_critical("Potassium", 4.0, "mmol/L")

    assert evaluation.evaluated is True
    assert evaluation.is_critical is False
    assert evaluation.critical_status is None


def test_analyte_with_inactive_threshold_sides_is_evaluated_but_never_critical():
    """WBC có bản ghi trong critical_thresholds.json nhưng cả hai phía low/high đều
    null (ARUP Rev.46 inactive_reason) — vẫn ``evaluated=True`` (có chạy so sánh),
    chỉ là không phía nào active nên không bao giờ ra ``is_critical``."""

    evaluation = evaluate_critical("WBC", 999, "10^9/L")

    assert evaluation.evaluated is True
    assert evaluation.is_critical is False
    assert evaluation.active_low is None
    assert evaluation.active_high is None


def test_analyte_absent_from_registry_is_not_evaluated_at_all():
    """Chỉ số hoàn toàn không có trong critical_thresholds.json — fail closed ở mức
    "không có cấu hình để đánh giá", khác với "đã đánh giá và an toàn"."""

    evaluation = evaluate_critical("Not A Real Analyte", 1, "unit")

    assert evaluation.evaluated is False
    assert evaluation.is_critical is False


def test_unit_mismatch_without_approved_conversion_fails_closed():
    """Chỉ glucose có đường convert đơn vị được duyệt — potassium sai đơn vị phải
    fail-closed, không được âm thầm so sánh sai đơn vị."""

    evaluation = evaluate_critical("Potassium", 6.2, "mEq/L")

    assert evaluation.evaluated is False
    assert evaluation.is_critical is False


def test_glucose_mmol_l_input_converts_before_comparing_to_mg_dl_threshold():
    low_critical_mmol_l = 2.0  # ~36 mg/dL, dưới ngưỡng thấp 55 mg/dL
    evaluation = evaluate_critical("Fasting plasma glucose", low_critical_mmol_l, "mmol/L")

    assert evaluation.is_critical is True
    assert evaluation.critical_status == "critical_low"
    assert evaluation.comparison_value == glucose_mmol_l_to_mg_dl(low_critical_mmol_l)


def test_glucose_within_range_mmol_l_is_not_critical():
    evaluation = evaluate_critical("Fasting plasma glucose", 5.5, "mmol/L")

    assert evaluation.evaluated is True
    assert evaluation.is_critical is False


def test_approaches_critical_true_when_moving_toward_high_threshold_within_margin():
    """Ngưỡng cao potassium = 6.1; biên 10% => trong [5.49, 6.71]. Giá trị 5.8 nằm
    trong biên, chưa critical (< 6.1), và đang tăng từ 5.0 lên — đúng luật approach."""

    evaluation = evaluate_critical("Potassium", 5.8, "mmol/L")

    assert approaches_critical(evaluation, previous_value=5.0) is True


def test_approaches_critical_false_when_moving_away_from_threshold():
    """Cùng nằm trong biên margin nhưng đang giảm dần (rời xa ngưỡng cao) —
    không được coi là approaching."""

    evaluation = evaluate_critical("Potassium", 5.8, "mmol/L")

    assert approaches_critical(evaluation, previous_value=6.0) is False


def test_approaches_critical_false_when_already_critical():
    """Giá trị đã vượt ngưỡng thì dùng nhánh critical, không phải approaching —
    tránh hai template chồng nhau."""

    evaluation = evaluate_critical("Potassium", 6.2, "mmol/L")

    assert approaches_critical(evaluation, previous_value=5.0) is False


def test_approaches_critical_false_outside_margin():
    """Giá trị 4.0 còn cách ngưỡng cao 6.1 rất xa (ngoài 10%) dù đang tăng."""

    evaluation = evaluate_critical("Potassium", 4.0, "mmol/L")

    assert approaches_critical(evaluation, previous_value=3.5) is False


def test_approaches_critical_false_for_analyte_without_active_threshold():
    evaluation = evaluate_critical("WBC", 10.0, "10^9/L")

    assert approaches_critical(evaluation, previous_value=9.0) is False


def test_approach_margin_is_ten_percent():
    """Khoá số 0.10 lại bằng test — ADR-010 ghi rõ đây là quyết định sản phẩm,
    đổi số này phải là một thay đổi có chủ đích, không phải vô tình."""

    assert APPROACH_MARGIN == Decimal("0.10")
