import pytest

from src.agents.nodes import reference_range_checker_node as checker_module
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node


NORMAL_GROUP = "normal"
ADULT_GROUP = "adult"


@pytest.fixture
def controlled_reference_db(monkeypatch):
    db = {
        "synthetic-wbc": {
            "indicator": "Synthetic-WBC",
            "reference_ranges": [
                {"gender": "A", "group": NORMAL_GROUP, "low": 4, "high": 10, "unit": "10^9/L", "age_scope": "adult"}
            ],
        },
        "synthetic-rbc": {
            "indicator": "Synthetic-RBC",
            "reference_ranges": [
                {"gender": "M", "group": ADULT_GROUP, "low": 4.5, "high": 6.2, "unit": "10^12/L", "age_scope": "adult"},
                {"gender": "F", "group": ADULT_GROUP, "low": 4.0, "high": 5.5, "unit": "10^12/L", "age_scope": "adult"},
            ],
        },
        "synthetic-upper-only": {
            "indicator": "Synthetic-Upper-Only",
            "reference_ranges": [
                {"gender": "A", "group": NORMAL_GROUP, "low": None, "high": 5, "unit": "mg/dL", "age_scope": "adult"}
            ],
        },
        "synthetic-lower-only": {
            "indicator": "Synthetic-Lower-Only",
            "reference_ranges": [
                {"gender": "A", "group": NORMAL_GROUP, "low": 3, "high": None, "unit": "mg/dL", "age_scope": "adult"}
            ],
        },
        "synthetic-ambiguous": {
            "indicator": "Synthetic-Ambiguous",
            "reference_ranges": [
                {"gender": "A", "group": NORMAL_GROUP, "low": 1, "high": 2, "unit": "mg/dL", "age_scope": "adult"},
                {"gender": "A", "group": NORMAL_GROUP, "low": 10, "high": 20, "unit": "mg/dL", "age_scope": "adult"},
            ],
        },
        "synthetic-sex-with-fallback": {
            "indicator": "Synthetic-Sex-With-Fallback",
            "reference_ranges": [
                {"gender": "A", "group": NORMAL_GROUP, "low": 1, "high": 2, "unit": "mg/dL", "age_scope": "adult"},
                {"gender": "M", "group": NORMAL_GROUP, "low": 10, "high": 20, "unit": "mg/dL", "age_scope": "adult"},
            ],
        },
    }
    monkeypatch.setattr(checker_module, "EXPLANATIONS_DB", db)
    return db


async def run_checker(raw_indicators, patient_gender="male", patient_age=35):
    return await reference_range_checker_node(
        {
            "patient_age": patient_age,
            "patient_gender": patient_gender,
            "raw_indicators": raw_indicators,
        }
    )


def only_indicator(result):
    indicators = result["indicators"]
    assert len(indicators) == 1
    return indicators[0]


def assert_contract_shape(assessment):
    assert isinstance(assessment["name"], str)
    assert isinstance(assessment["unit"], str)
    assert "value" in assessment
    assert "reference_low" in assessment
    assert "reference_high" in assessment
    assert isinstance(assessment["status"], str)
    assert isinstance(assessment["is_abnormal"], bool)
    assert isinstance(assessment["is_critical"], bool)
    assert isinstance(assessment["explanation"], str)
    assert isinstance(assessment["sources"], list)
    # Current checker output does not populate the optional state `category` field.
    assert "category" not in assessment


@pytest.mark.asyncio
async def test_c01_empty_input_returns_empty_indicators(controlled_reference_db):
    result = await run_checker([])

    assert "indicators" in result
    assert result["indicators"] == []


@pytest.mark.asyncio
async def test_c02_supported_two_sided_normal(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "normal"
    assert assessment["is_abnormal"] is False
    assert assessment["reference_low"] == 4
    assert assessment["reference_high"] == 10


@pytest.mark.asyncio
async def test_c03_value_below_lower_bound_is_low(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 3.9, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "low"
    assert assessment["is_abnormal"] is True


@pytest.mark.asyncio
async def test_c04_value_above_upper_bound_is_high(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 10.1, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "high"
    assert assessment["is_abnormal"] is True


@pytest.mark.asyncio
async def test_c05_inclusive_lower_boundary_is_normal(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 4, "unit": "10^9/L"}])

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c06_inclusive_upper_boundary_is_normal(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 10, "unit": "10^9/L"}])

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c07_exact_male_rule_is_selected(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}], patient_gender="male")
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 4.5
    assert assessment["reference_high"] == 6.2
    assert assessment["status"] == "low"


@pytest.mark.asyncio
async def test_c08_exact_female_rule_is_selected(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}], patient_gender="female")
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 4.0
    assert assessment["reference_high"] == 5.5
    assert assessment["status"] == "normal"


@pytest.mark.asyncio
@pytest.mark.parametrize("patient_gender", ["male", "female", "other"])
async def test_c09_all_sex_rule_is_used_for_supported_api_genders(controlled_reference_db, patient_gender):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_gender=patient_gender,
    )

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c10_no_matching_sex_rule_remains_unknown(controlled_reference_db):
    result = await run_checker(
        [{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}],
        patient_gender="other",
    )
    assessment = only_indicator(result)

    assert assessment["status"] == "unknown"
    assert assessment["reference_low"] is None
    assert assessment["reference_high"] is None
    assert assessment["is_abnormal"] is False


@pytest.mark.asyncio
async def test_c11_unsupported_analyte_uses_unknown_contract(controlled_reference_db):
    result = await run_checker([{"name": "Not-In-Controlled-DB", "value": 5, "unit": "x"}])
    assessment = only_indicator(result)

    assert assessment["name"] == "Not-In-Controlled-DB"
    assert assessment["status"] == "unknown"
    assert assessment["reference_low"] is None
    assert assessment["reference_high"] is None
    assert assessment["is_abnormal"] is False


@pytest.mark.asyncio
async def test_c12_missing_value_uses_unknown_contract(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": None, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "unknown"
    assert assessment["reference_low"] is None
    assert assessment["reference_high"] is None
    assert assessment["is_abnormal"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status", "expected_abnormal"),
    [(5, "normal", False), (4.9, "normal", False), (5.1, "high", True)],
)
async def test_c13_upper_only_range_behavior(controlled_reference_db, value, expected_status, expected_abnormal):
    result = await run_checker([{"name": "Synthetic-Upper-Only", "value": value, "unit": "mg/dL"}])
    assessment = only_indicator(result)

    assert assessment["status"] == expected_status
    assert assessment["is_abnormal"] is expected_abnormal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status", "expected_abnormal"),
    [(3, "normal", False), (3.1, "normal", False), (2.9, "low", True)],
)
async def test_c14_lower_only_range_behavior(controlled_reference_db, value, expected_status, expected_abnormal):
    result = await run_checker([{"name": "Synthetic-Lower-Only", "value": value, "unit": "mg/dL"}])
    assessment = only_indicator(result)

    assert assessment["status"] == expected_status
    assert assessment["is_abnormal"] is expected_abnormal


@pytest.mark.asyncio
async def test_c15_output_contract_shape_for_downstream_nodes(controlled_reference_db):
    result = await run_checker(
        [
            {"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"},
            {"name": "Not-In-Controlled-DB", "value": 5, "unit": "x"},
            {"name": "Synthetic-WBC", "value": None, "unit": "10^9/L"},
        ]
    )

    for assessment in result["indicators"]:
        assert_contract_shape(assessment)


@pytest.mark.asyncio
async def test_c16_input_order_is_preserved(controlled_reference_db):
    raw_indicators = [
        {"name": "Not-In-Controlled-DB", "value": 5, "unit": "x"},
        {"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"},
        {"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"},
    ]

    result = await run_checker(raw_indicators)

    assert [indicator["name"] for indicator in result["indicators"]] == [
        "Not-In-Controlled-DB",
        "Synthetic-RBC",
        "Synthetic-WBC",
    ]


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="V2 contract pending TIP-002B: wrong unit must not classify")
async def test_v2_01_wrong_unit_must_not_classify_unit_not_supported(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "mg/dL"}])

    assert only_indicator(result)["status"] not in {"normal", "low", "high"}


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="V2 contract pending TIP-002B: age scope must be enforced")
async def test_v2_02_age_outside_scope_must_not_classify(controlled_reference_db):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_age=7,
    )

    assert only_indicator(result)["status"] not in {"normal", "low", "high"}


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="V2 contract pending TIP-002B: ambiguous rules need explicit rejection")
async def test_v2_03_ambiguous_equal_priority_rules_must_not_use_first_match(controlled_reference_db):
    result = await run_checker([{"name": "Synthetic-Ambiguous", "value": 1.5, "unit": "mg/dL"}])

    assert only_indicator(result)["status"] not in {"normal", "low", "high"}


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="V2 contract pending TIP-002B: exact sex must beat fallback A regardless of order")
async def test_v2_04_exact_sex_rule_must_beat_all_sex_fallback(controlled_reference_db):
    result = await run_checker(
        [{"name": "Synthetic-Sex-With-Fallback", "value": 15, "unit": "mg/dL"}],
        patient_gender="male",
    )
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 10
    assert assessment["reference_high"] == 20
    assert assessment["status"] == "normal"


@pytest.mark.asyncio
@pytest.mark.xfail(strict=True, reason="V2 contract pending TIP-002B: unexpected internal gender must not silently become A")
async def test_v2_05_unknown_internal_gender_must_not_silently_select_all_sex_rule(controlled_reference_db):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_gender="unexpected-internal-value",
    )

    assert only_indicator(result)["status"] not in {"normal", "low", "high"}
