from __future__ import annotations

from decimal import Decimal

import pytest

from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.reference_range_checker_node import (
    get_reference_repository,
    reference_range_checker_node,
)
from src.agents.state import AgentState
from src.services.measurement_conversion import glucose_mmol_l_to_mg_dl


async def run_reference_pipeline(
    raw_indicators: list[dict],
    *,
    patient_age: int | None = 30,
    patient_gender: str = "male",
) -> tuple[dict, dict]:
    get_reference_repository.cache_clear()
    initial_state: AgentState = {
        "patient_age": patient_age,
        "patient_gender": patient_gender,
        "raw_indicators": raw_indicators,
    }
    checker_result = await reference_range_checker_node(initial_state)
    critical_result = await detect_critical_values_node({**initial_state, **checker_result})
    return checker_result, critical_result


def only_indicator(result: dict) -> dict:
    assert len(result["indicators"]) == 1
    return result["indicators"][0]


def assert_unknown(indicator: dict) -> None:
    assert indicator["status"] == "unknown"
    assert indicator["reference_low"] is None
    assert indicator["reference_high"] is None
    assert indicator["is_abnormal"] is False
    assert indicator["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_01_wbc_normal_legacy_unit():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "WBC", "value": 7.0, "unit": "10^3/uL"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "normal"
    assert checked["reference_low"] == 4.72
    assert checked["reference_high"] == 11.3
    assert checked["is_abnormal"] is False
    assert checked["value"] == 7.0

    critical = only_indicator(critical_result)
    assert critical["status"] == "normal"
    assert critical["is_critical"] is False
    assert critical_result["has_critical_values"] is False


@pytest.mark.asyncio
async def test_e2e_02_rbc_male_sex_specific_rule():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "RBC", "value": 4.2, "unit": "10^12/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["reference_low"] == 4.45
    assert checked["reference_high"] == 6.19
    assert checked["status"] == "low"
    assert checked["is_abnormal"] is True
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_03_rbc_female_sex_specific_rule():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "RBC", "value": 4.2, "unit": "10^12/L"}],
        patient_age=30,
        patient_gender="female",
    )

    checked = only_indicator(checker_result)
    assert checked["reference_low"] == 4.01
    assert checked["reference_high"] == 5.48
    assert checked["status"] == "normal"
    assert checked["is_abnormal"] is False
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_04_fasting_plasma_glucose_uses_cdl():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Fasting plasma glucose", "value": 6.5, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 5.6
    assert checked["status"] == "high"
    assert only_indicator(critical_result)["status"] == "high"


@pytest.mark.asyncio
async def test_e2e_04b_ocr_vietnamese_labels_use_the_same_reference_rules():
    checker_result, critical_result = await run_reference_pipeline(
        [
            {"name": "Bạch cầu (WBC)", "value": 6.5, "unit": "10^9/L"},
            {"name": "Hồng cầu (RBC)", "value": 4.5, "unit": "10^12/L"},
            {"name": "Đường huyết lúc đói", "value": 5.2, "unit": "mmol/L"},
            {"name": "Creatinine", "value": 75, "unit": "µmol/L"},
        ],
        patient_age=30,
        patient_gender="male",
    )

    assert [indicator["status"] for indicator in checker_result["indicators"]] == [
        "normal",
        "normal",
        "normal",
        "normal",
    ]
    assert [indicator["status"] for indicator in critical_result["indicators"]] == [
        "normal",
        "normal",
        "normal",
        "normal",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("generic_name", ["Glucose", "Đường huyết"])
async def test_e2e_04c_generic_glucose_does_not_receive_fasting_ri(generic_name):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": generic_name, "value": 5.2, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    assert_unknown(only_indicator(checker_result))
    assert_unknown(only_indicator(critical_result))
    assert critical_result["critical_alerts"] == []
    assert critical_result["has_critical_values"] is False


@pytest.mark.asyncio
async def test_e2e_04d_generic_glucose_low_value_preserves_unknown_status():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Glucose", "value": 3.0, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    assert_unknown(only_indicator(checker_result))
    assert_unknown(only_indicator(critical_result))
    assert critical_result["critical_alerts"] == []
    assert critical_result["has_critical_values"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "explicit_fasting_name",
    ["Fasting plasma glucose", "Đường huyết lúc đói"],
)
async def test_e2e_04e_explicit_fasting_glucose_reaches_arup_critical_low(
    explicit_fasting_name,
):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": explicit_fasting_name, "value": 3.0, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "normal"
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 5.6
    assert glucose_mmol_l_to_mg_dl(Decimal("3.0")) == Decimal("54.04677")

    critical = only_indicator(critical_result)
    assert critical["status"] == "normal"
    assert critical["critical_status"] == "critical_low"
    assert critical["is_critical"] is True
    assert critical_result["has_critical_values"] is True
    assert len(critical_result["critical_alerts"]) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("patient_age", "expected_status", "expected_low", "expected_high"),
    [
        (18, "normal", 59, 104),
        (60, "normal", 59, 104),
        (17, "unknown", None, None),
        (61, "unknown", None, None),
    ],
)
async def test_e2e_05_creatinine_adult_boundaries(patient_age, expected_status, expected_low, expected_high):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Creatinine", "value": 80, "unit": "µmol/L"}],
        patient_age=patient_age,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == expected_low
    assert checked["reference_high"] == expected_high
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_06_wrong_wbc_unit_remains_unknown():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "WBC", "value": 7.0, "unit": "g/L"}],
        patient_age=30,
        patient_gender="male",
    )

    assert_unknown(only_indicator(checker_result))
    assert_unknown(only_indicator(critical_result))


@pytest.mark.asyncio
async def test_e2e_07_hgb_approved():
    # After BONUS-TIP-010: HGB is approved; 140 g/L is within male normal range (128–183)
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HGB", "value": 140, "unit": "g/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "normal"
    assert checked["reference_low"] == 128
    assert checked["reference_high"] == 183
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_08_hdl_c_approved():
    # HDL-C approved; 1.2 mmol/L is within intermediate band (1.04–1.55)
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HDL-Cholesterol", "value": 1.2, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "normal"
    assert checked["reference_low"] == 1.04
    assert checked["reference_high"] == 1.55
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_09_hba1c_approved():
    # HbA1c approved; 5.5 % is within normal CDL (<5.7)
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HbA1c", "value": 5.5, "unit": "%"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "normal"
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 5.7
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_10_ldl_c_approved_high_value():
    # LDL-C approved; 3.0 mmol/L exceeds optimal CDL (<2.59) → high
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "LDL-C", "value": 3.0, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "high"
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 2.59
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
async def test_e2e_11_potassium_critical_high():
    # Potassium approved; 6.5 mmol/L > RI upper 5.3 → high, then critical_high
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Potassium", "value": 6.5, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "high"
    assert checked["reference_low"] == 3.5
    assert checked["reference_high"] == 5.3
    assert checked["is_critical"] is False

    critical = only_indicator(critical_result)
    assert critical["status"] == "high"
    assert critical["critical_status"] == "critical_high"
    assert critical["is_critical"] is True
    assert critical_result["has_critical_values"] is True


@pytest.mark.asyncio
async def test_e2e_12_kali_critical_low_alias_boundary():
    # Kali alias resolves to Potassium; 2.99 satisfies the strict ARUP <3.0 rule.
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Kali", "value": 2.99, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == "low"
    assert checked["reference_low"] == 3.5
    assert checked["reference_high"] == 5.3
    critical = only_indicator(critical_result)
    assert critical["status"] == "low"
    assert critical["critical_status"] == "critical_low"
    assert critical["is_critical"] is True


@pytest.mark.asyncio
async def test_e2e_13_multiple_indicator_order():
    raw_indicators = [
        {"name": "WBC", "value": 7.0, "unit": "10^3/uL"},
        {"name": "HGB", "value": 140, "unit": "g/L"},
        {"name": "Potassium", "value": 6.5, "unit": "mmol/L"},
        {"name": "Creatinine", "value": 80, "unit": "µmol/L"},
    ]

    checker_result, critical_result = await run_reference_pipeline(raw_indicators, patient_age=30, patient_gender="male")

    assert [indicator["name"] for indicator in checker_result["indicators"]] == [
        "WBC",
        "HGB",
        "Potassium",
        "Creatinine",
    ]
    assert [indicator["name"] for indicator in critical_result["indicators"]] == [
        "WBC",
        "HGB",
        "Potassium",
        "Creatinine",
    ]
    # After BONUS-TIP-010: HGB approved (140 g/L male → normal); Potassium approved (6.5 → high + critical_high)
    assert [indicator["status"] for indicator in critical_result["indicators"]] == [
        "normal",
        "normal",
        "high",
        "normal",
    ]
    assert [indicator.get("critical_status") for indicator in critical_result["indicators"]] == [
        None,
        None,
        "critical_high",
        None,
    ]
    assert critical_result["has_critical_values"] is True


@pytest.mark.asyncio
async def test_e2e_14_missing_value_safety():
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "WBC", "value": None, "unit": "10^9/L"}],
        patient_age=30,
        patient_gender="male",
    )

    assert_unknown(only_indicator(checker_result))
    assert_unknown(only_indicator(critical_result))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (3.4, "low"),    # below lower bound
        (3.5, "normal"), # = lower bound (inclusive)
        (4.2, "normal"), # mid range
        (5.3, "normal"), # = upper bound (inclusive)
        (5.4, "high"),   # above upper bound
    ],
)
async def test_e2e_15_potassium_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "Potassium", "value": value, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == 3.5
    assert checked["reference_high"] == 5.3
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (2.0,  "normal"), # within CDL < 2.59
        (2.59, "normal"), # = upper bound (inclusive)
        (2.60, "high"),   # just above upper bound
        (3.8,  "high"),   # clearly high
    ],
)
async def test_e2e_16_ldl_c_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "LDL-C", "value": value, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 2.59
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (4.5,  "normal"), # within normal < 5.7
        (5.5,  "normal"), # clearly within normal
        (5.6,  "normal"),
        (5.7,  "normal"), # = upper bound (inclusive)
        (5.71, "high"),   # prediabetes threshold (>5.7)
        (7.5,  "high"),   # clearly high
    ],
)
async def test_e2e_17_hba1c_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HbA1c", "value": value, "unit": "%"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] is None
    assert checked["reference_high"] == 5.7
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (127, "low"),    # below lower bound
        (128, "normal"), # = lower bound (inclusive)
        (155, "normal"), # mid range
        (183, "normal"), # = upper bound (inclusive)
        (184, "high"),   # above upper bound
    ],
)
async def test_e2e_18_hgb_male_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HGB", "value": value, "unit": "g/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == 128
    assert checked["reference_high"] == 183
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (109, "low"),    # below lower bound
        (110, "normal"), # = lower bound (inclusive)
        (130, "normal"), # mid range
        (150, "normal"), # = upper bound (inclusive)
        (151, "high"),   # above upper bound
    ],
)
async def test_e2e_19_hgb_female_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HGB", "value": value, "unit": "g/L"}],
        patient_age=30,
        patient_gender="female",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == 110
    assert checked["reference_high"] == 150
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (1.03, "low"),    # below lower bound
        (1.04, "normal"), # = lower bound (inclusive)
        (1.28, "normal"), # mid range
        (1.54, "normal"), # = upper bound (inclusive)
        (1.55, "normal"), # = upper bound (inclusive)
        (1.56, "high"),   # above upper bound
    ],
)
async def test_e2e_20_hdl_c_male_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HDL-Cholesterol", "value": value, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == 1.04
    assert checked["reference_high"] == 1.55
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (1.03, "low"),    # below lower bound
        (1.04, "normal"), # = lower bound (inclusive)
        (1.40, "normal"), # mid range
        (1.54, "normal"), # = upper bound (inclusive)
        (1.55, "normal"), # = upper bound (inclusive)
        (1.56, "high"),   # above upper bound
    ],
)
async def test_e2e_21_hdl_c_female_ri_boundaries(value, expected_status):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": "HDL-Cholesterol", "value": value, "unit": "mmol/L"}],
        patient_age=30,
        patient_gender="female",
    )

    checked = only_indicator(checker_result)
    assert checked["status"] == expected_status
    assert checked["reference_low"] == 1.04
    assert checked["reference_high"] == 1.55
    assert only_indicator(critical_result)["is_critical"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "value", "unit", "expected_ri_status"),
    [
        ("WBC", 35.0, "10^9/L", "high"),
        ("HGB", 200.0, "g/L", "high"),
        ("LDL-C", 5.3, "mmol/L", "high"),
        ("HbA1c", 10.0, "%", "high"),
        ("HDL-C", 0.5, "mmol/L", "low"),
        ("Creatinine", 400.0, "umol/L", "high"),
        ("RBC", 100.0, "10^12/L", "high"),
    ],
)
async def test_e2e_22_inactive_critical_rules_preserve_ri_status(
    name,
    value,
    unit,
    expected_ri_status,
):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": name, "value": value, "unit": unit}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    critical = only_indicator(critical_result)

    assert checked["status"] == expected_ri_status
    assert critical["status"] == expected_ri_status
    assert critical["is_critical"] is False
    assert critical_result["has_critical_values"] is False
    assert critical_result["critical_alerts"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("alias_name", "value", "unit", "expected_status", "expected_is_critical"),
    [
        ("K+", 4.2, "mmol/l", "normal", False),
        ("K+", 6.5, "mmol/L", "high", True),
        ("Creatinin", 80.0, "µmol/l", "normal", False),
        ("HDL-cho.", 1.4, "mmol/L", "normal", False),
        ("LDL-cho.", 2.0, "mmol/L", "normal", False),
        ("Glucose", 5.2, "mmol/L", "unknown", False),
    ],
)
async def test_e2e_23_verified_ocr_aliases_end_to_end(
    alias_name,
    value,
    unit,
    expected_status,
    expected_is_critical,
):
    checker_result, critical_result = await run_reference_pipeline(
        [{"name": alias_name, "value": value, "unit": unit}],
        patient_age=30,
        patient_gender="male",
    )

    checked = only_indicator(checker_result)
    critical = only_indicator(critical_result)

    assert checked["status"] == expected_status
    assert critical["is_critical"] == expected_is_critical
