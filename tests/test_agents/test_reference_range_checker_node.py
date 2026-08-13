import pytest

from src.agents.nodes import reference_range_checker_node as checker_module
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.services.analyte_catalog import AnalyteCatalog, AnalyteDefinition
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError


def make_rule(
    analyte,
    *,
    sex="A",
    age_scope="18-60",
    unit="mg/dL",
    lower=4,
    upper=10,
    reference_type="RI",
    source_url="https://example.test/source",
):
    return {
        "rule_id": f"RULE-{analyte}-{sex}-{lower}-{upper}",
        "source_row_number": 2,
        "analyte_canonical": analyte,
        "specimen": "Synthetic",
        "fasting_required": "NO",
        "sex": sex,
        "age_scope": age_scope,
        "unit_machine": unit,
        "unit_display_vn": unit,
        "unit_raw": unit,
        "unit_canonical": unit,
        "value_type": "absolute",
        "range_lower": lower,
        "range_upper": upper,
        "reference_type": reference_type,
        "source_priority_tier": "T1",
        "source_url": source_url,
        "confidence": "HIGH",
    }


@pytest.fixture
def controlled_repository(monkeypatch):
    config = {
        "config_version": "v2",
        "allowed_reference_types": ["RI"],
        "approved_analytes": [
            "Synthetic-WBC",
            "Synthetic-RBC",
            "Synthetic-Upper-Only",
            "Synthetic-Lower-Only",
            "Synthetic-Ambiguous",
            "Synthetic-Sex-With-Fallback",
            "WBC",
        ],
        "pending_analytes": ["HbA1c", "LDL-C", "Potassium"],
        "analyte_aliases": {
            "Synthetic-WBC": "Synthetic-WBC",
            "Synthetic-RBC": "Synthetic-RBC",
            "Synthetic-Upper-Only": "Synthetic-Upper-Only",
            "Synthetic-Lower-Only": "Synthetic-Lower-Only",
            "Synthetic-Ambiguous": "Synthetic-Ambiguous",
            "Synthetic-Sex-With-Fallback": "Synthetic-Sex-With-Fallback",
            "WBC": "WBC",
            "HbA1c": "HbA1c",
            "LDL-C": "LDL-C",
            "LDL-Cholesterol": "LDL-C",
            "Potassium": "Potassium",
            "Kali": "Potassium",
        },
        "age_scope_aliases": {"Adult": {"min_age": 18, "max_age": 60}},
    }
    rules = [
        make_rule("Synthetic-WBC", unit="10^9/L"),
        make_rule("Synthetic-RBC", sex="M", unit="10^12/L", lower=4.5, upper=6.2),
        make_rule("Synthetic-RBC", sex="F", unit="10^12/L", lower=4.0, upper=5.5),
        make_rule("Synthetic-Upper-Only", lower=None, upper=5),
        make_rule("Synthetic-Lower-Only", lower=3, upper=None),
        make_rule("Synthetic-Ambiguous", lower=1, upper=2),
        make_rule("Synthetic-Ambiguous", lower=1, upper=2),
        make_rule("Synthetic-Sex-With-Fallback", sex="A", lower=1, upper=2),
        make_rule("Synthetic-Sex-With-Fallback", sex="M", lower=10, upper=20),
        make_rule("WBC", unit="10^9/L"),
    ]
    repository = ReferenceRepository(config=config, rules=rules)
    monkeypatch.setattr(checker_module, "get_reference_repository", lambda: repository)
    catalog = AnalyteCatalog(
        definitions=[
            AnalyteDefinition(
                analyte_id="synthetic-wbc",
                indicator="Synthetic-WBC",
                display_name="Synthetic WBC",
                vietnamese_name="",
                curated_explanation="Synthetic WBC explanation",
                sources=("https://example.test/explanation",),
            )
        ],
        aliases={"Synthetic-WBC": "Synthetic-WBC"},
    )
    monkeypatch.setattr(checker_module, "get_analyte_catalog", lambda: catalog)
    return repository


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


def assert_unknown(assessment):
    assert assessment["status"] == "unknown"
    assert assessment["reference_low"] is None
    assert assessment["reference_high"] is None
    assert assessment["is_abnormal"] is False
    assert assessment["is_critical"] is False


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
    assert "category" not in assessment
    assert "range" + "_flag" not in assessment


@pytest.mark.asyncio
async def test_c01_empty_input_returns_empty_indicators(controlled_repository):
    result = await run_checker([])

    assert "indicators" in result
    assert result["indicators"] == []


@pytest.mark.asyncio
async def test_c02_supported_two_sided_normal(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "normal"
    assert assessment["is_abnormal"] is False
    assert assessment["reference_low"] == 4
    assert assessment["reference_high"] == 10


@pytest.mark.asyncio
async def test_c03_value_below_lower_bound_is_low(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 3.9, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "low"
    assert assessment["is_abnormal"] is True


@pytest.mark.asyncio
async def test_c04_value_above_upper_bound_is_high(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 10.1, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["status"] == "high"
    assert assessment["is_abnormal"] is True


@pytest.mark.asyncio
async def test_c05_inclusive_lower_boundary_is_normal(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 4, "unit": "10^9/L"}])

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c06_inclusive_upper_boundary_is_normal(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 10, "unit": "10^9/L"}])

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c07_exact_male_rule_is_selected(controlled_repository):
    result = await run_checker([{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}], patient_gender="male")
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 4.5
    assert assessment["reference_high"] == 6.2
    assert assessment["status"] == "low"


@pytest.mark.asyncio
async def test_c08_exact_female_rule_is_selected(controlled_repository):
    result = await run_checker(
        [{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}],
        patient_gender="female",
    )
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 4
    assert assessment["reference_high"] == 5.5
    assert assessment["status"] == "normal"


@pytest.mark.asyncio
@pytest.mark.parametrize("patient_gender", ["male", "female", "other"])
async def test_c09_all_sex_rule_is_used_for_supported_api_genders(controlled_repository, patient_gender):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_gender=patient_gender,
    )

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_c10_no_matching_sex_rule_remains_unknown(controlled_repository):
    result = await run_checker(
        [{"name": "Synthetic-RBC", "value": 4.3, "unit": "10^12/L"}],
        patient_gender="other",
    )

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_c11_unsupported_analyte_uses_unknown_contract(controlled_repository):
    result = await run_checker([{"name": "Not-In-Controlled-DB", "value": 5, "unit": "x"}])
    assessment = only_indicator(result)

    assert assessment["name"] == "Not-In-Controlled-DB"
    assert_unknown(assessment)


@pytest.mark.asyncio
async def test_c12_missing_value_uses_unknown_contract(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": None, "unit": "10^9/L"}])

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status", "expected_abnormal"),
    [(5, "normal", False), (4.9, "normal", False), (5.1, "high", True)],
)
async def test_c13_upper_only_range_behavior(controlled_repository, value, expected_status, expected_abnormal):
    result = await run_checker([{"name": "Synthetic-Upper-Only", "value": value, "unit": "mg/dL"}])
    assessment = only_indicator(result)

    assert assessment["status"] == expected_status
    assert assessment["is_abnormal"] is expected_abnormal


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status", "expected_abnormal"),
    [(3, "normal", False), (3.1, "normal", False), (2.9, "low", True)],
)
async def test_c14_lower_only_range_behavior(controlled_repository, value, expected_status, expected_abnormal):
    result = await run_checker([{"name": "Synthetic-Lower-Only", "value": value, "unit": "mg/dL"}])
    assessment = only_indicator(result)

    assert assessment["status"] == expected_status
    assert assessment["is_abnormal"] is expected_abnormal


@pytest.mark.asyncio
async def test_c15_output_contract_shape_for_downstream_nodes(controlled_repository):
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
async def test_c16_input_order_is_preserved(controlled_repository):
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
async def test_v2_01_wrong_unit_must_not_classify(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "mg/dL"}])

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_v2_02_age_outside_scope_must_not_classify(controlled_repository):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_age=7,
    )

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_v2_03_ambiguous_equal_priority_rules_must_not_use_first_match(controlled_repository):
    result = await run_checker([{"name": "Synthetic-Ambiguous", "value": 1.5, "unit": "mg/dL"}])

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_v2_04_exact_sex_rule_must_beat_all_sex_fallback(controlled_repository):
    result = await run_checker(
        [{"name": "Synthetic-Sex-With-Fallback", "value": 15, "unit": "mg/dL"}],
        patient_gender="male",
    )
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 10
    assert assessment["reference_high"] == 20
    assert assessment["status"] == "normal"


@pytest.mark.asyncio
async def test_v2_05_unknown_internal_gender_must_not_silently_select_all_sex_rule(controlled_repository):
    result = await run_checker(
        [{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}],
        patient_gender="unexpected-internal-value",
    )

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_approved_wbc_may_classify(controlled_repository):
    result = await run_checker([{"name": "WBC", "value": 7, "unit": "10^9/L"}])

    assert only_indicator(result)["status"] == "normal"


@pytest.mark.asyncio
async def test_wbc_legacy_10_3_ul_alias_classifies_without_rewriting_output_unit(controlled_repository):
    result = await run_checker([{"name": "WBC", "value": 7.2, "unit": "10^3/uL"}])

    assessment = only_indicator(result)
    assert assessment["status"] == "normal"
    assert assessment["value"] == 7.2
    assert assessment["unit"] == "10^3/uL"
    assert assessment["reference_low"] == 4
    assert assessment["reference_high"] == 10


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["HbA1c", "LDL-C", "LDL-Cholesterol", "Potassium", "Kali"])
async def test_pending_analytes_remain_unknown_in_normal_checker(controlled_repository, name):
    result = await run_checker([{"name": name, "value": 7, "unit": "mmol/L"}])

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_repository_load_failure_returns_unknown_without_fallback(monkeypatch):
    def raise_config_error():
        raise ReferenceRepositoryError("controlled failure")

    monkeypatch.setattr(checker_module, "get_reference_repository", raise_config_error)
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}])

    assert_unknown(only_indicator(result))


@pytest.mark.asyncio
async def test_explanation_and_sources_preserved_without_using_explanation_ranges(controlled_repository):
    result = await run_checker([{"name": "Synthetic-WBC", "value": 7, "unit": "10^9/L"}])
    assessment = only_indicator(result)

    assert assessment["reference_low"] == 4
    assert assessment["reference_high"] == 10
    assert assessment["explanation"] == "Synthetic WBC explanation"
    assert assessment["sources"] == ["https://example.test/explanation"]
