from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path

import pytest

from src.services.analyte_catalog import get_analyte_catalog_contract
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_RANGES = REPO_ROOT / "data/reference/reference_ranges.json"

PHASE_A_ANALYTES = {
    "MCV",
    "MCH",
    "MCHC",
    "PLT",
    "Neutrophils %",
    "Neutrophils abs",
    "Lymphocytes %",
    "Lymphocytes abs",
    "Monocytes %",
    "Monocytes abs",
    "Eosinophils %",
    "Eosinophils abs",
    "Sodium",
    "Chloride",
    "Urea",
    "AST",
    "ALT",
    "GGT",
    "Total bilirubin",
    "Total protein",
    "Albumin",
}

PHASE_B_ANALYTES = {
    "HCT",
    "RDW-CV",
    "Total cholesterol",
    "Triglyceride",
}

PHASE_C_ANALYTES = {
    "Uric acid",
}

RUNTIME_EXPANSION_ANALYTES = PHASE_A_ANALYTES | PHASE_B_ANALYTES | PHASE_C_ANALYTES
DIRECT_CLASSIFICATION_ANALYTES = PHASE_A_ANALYTES | {"HCT", "RDW-CV"} | PHASE_C_ANALYTES


def _rules_by_analyte() -> dict[str, list[dict]]:
    rules = json.loads(REFERENCE_RANGES.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = {}
    for rule in rules:
        grouped.setdefault(rule["analyte_canonical"], []).append(rule)
    return grouped


def _decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value))


def _input_for(rule: dict, expected_status: str, *, offset: Decimal = Decimal("0.1")) -> Decimal:
    lower = _decimal(rule.get("range_lower"))
    upper = _decimal(rule.get("range_upper"))
    if expected_status == "low":
        assert lower is not None
        if lower > 0:
            return lower / 2
        return lower - offset
    if expected_status == "high":
        assert upper is not None
        return upper + offset
    if lower is not None and upper is not None:
        return (lower + upper) / 2
    if upper is not None:
        return upper - offset
    assert lower is not None
    return lower + offset


def _assert_status(analyte: str, value: Decimal, unit: str, gender: str, age: int, expected: str) -> None:
    result = ReferenceRepository.from_default_files().select_rule(
        analyte=analyte,
        unit=unit,
        patient_gender=gender,
        patient_age=age,
    )
    assert result.matched is True
    assert result.canonical_analyte == analyte
    assert result.rule is not None
    from src.agents.nodes.reference_range_checker_node import _classify

    status = _classify(
        value,
        _decimal(result.rule.get("range_lower")),
        _decimal(result.rule.get("range_upper")),
        rule_type=result.rule.get("reference_type"),
        upper_operator=result.rule.get("upper_operator"),
    )
    assert status == expected


@pytest.mark.parametrize("analyte", sorted(RUNTIME_EXPANSION_ANALYTES))
def test_runtime_expansion_newly_approved_analytes_are_runtime_approved(analyte: str) -> None:
    repository = ReferenceRepository.from_default_files()

    assert analyte in repository.approved_analytes


@pytest.mark.parametrize("analyte", sorted(RUNTIME_EXPANSION_ANALYTES))
def test_runtime_expansion_newly_approved_analyte_aliases_resolve(analyte: str) -> None:
    repository = ReferenceRepository.from_default_files()
    entry = get_analyte_catalog_contract().resolve(analyte)
    assert entry is not None

    assert repository.resolve_analyte(entry.canonical_name) == analyte
    if entry.aliases:
        assert repository.resolve_analyte(entry.aliases[0]) == analyte


@pytest.mark.parametrize("analyte", sorted(DIRECT_CLASSIFICATION_ANALYTES))
def test_runtime_expansion_reference_rules_classify_representative_values(analyte: str) -> None:
    grouped = _rules_by_analyte()
    assert analyte in grouped

    for rule in grouped[analyte]:
        unit = rule["unit_canonical"]
        gender = "male" if rule["sex"] == "M" else "female" if rule["sex"] == "F" else "other"
        age = 35
        rule_type = rule["reference_type"]

        if rule_type == "ONE_SIDED_LIMIT":
            normal_value = _input_for(rule, "normal")
            high_value = _input_for(rule, "high")
            _assert_status(analyte, normal_value, unit, gender, age, "normal")
            _assert_status(analyte, high_value, unit, gender, age, "high")
            continue

        normal_value = _input_for(rule, "normal")
        _assert_status(analyte, normal_value, unit, gender, age, "normal")

        if rule.get("range_lower") is not None:
            low_value = _input_for(rule, "low")
            _assert_status(analyte, low_value, unit, gender, age, "low")
        if rule.get("range_upper") is not None:
            high_value = _input_for(rule, "high")
            _assert_status(analyte, high_value, unit, gender, age, "high")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("raw_name", "raw_value", "raw_unit", "expected_status"),
    [
        ("HCT", 0.45, "L/L", "normal"),
        ("RDW", 14.0, "%CV", "normal"),
        ("Total Cholesterol", 199, "mg/dL", "normal"),
        ("Total Cholesterol", 201, "mg/dL", "high"),
        ("Triglycerides", 149, "mg/dL", "normal"),
        ("Triglycerides", 151, "mg/dL", "high"),
        ("Uric Acid", 300, "µmol/L", "normal"),
    ],
)
async def test_phase_b_unit_remediation_classifies_without_rewriting_input_unit(
    raw_name: str,
    raw_value: float,
    raw_unit: str,
    expected_status: str,
) -> None:
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    result = await reference_range_checker_node(
        {
            "patient_age": 35,
            "patient_gender": "male",
            "raw_indicators": [{"name": raw_name, "value": raw_value, "unit": raw_unit}],
        }
    )

    assessment = result["indicators"][0]
    assert assessment["status"] == expected_status
    assert assessment["name"] == raw_name
    assert assessment["value"] == raw_value
    assert assessment["unit"] == raw_unit


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("gender", "value", "expected_status"),
    [
        ("female", 139, "low"),
        ("female", 140, "normal"),
        ("female", 250, "normal"),
        ("female", 360, "normal"),
        ("female", 361, "high"),
        ("male", 199, "low"),
        ("male", 200, "normal"),
        ("male", 300, "normal"),
        ("male", 430, "normal"),
        ("male", 431, "high"),
    ],
)
async def test_uric_acid_reference_interval_classifies_by_sex(gender: str, value: int, expected_status: str) -> None:
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    result = await reference_range_checker_node(
        {
            "patient_age": 35,
            "patient_gender": gender,
            "raw_indicators": [{"name": "Uric acid", "value": value, "unit": "umol/L"}],
        }
    )

    assessment = result["indicators"][0]
    assert assessment["status"] == expected_status
    assert assessment["name"] == "Uric acid"
    assert assessment["value"] == value
    assert assessment["unit"] == "umol/L"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("age", "expected_status", "expected_reason"),
    [
        (18, "unknown", "age_scope_not_supported"),
        (19, "normal", None),
        (90, "normal", None),
    ],
)
async def test_uric_acid_age_scope_is_age_19_and_older(age: int, expected_status: str, expected_reason: str | None) -> None:
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    result = await reference_range_checker_node(
        {
            "patient_age": age,
            "patient_gender": "male",
            "raw_indicators": [{"name": "Uric Acid", "value": 300, "unit": "µmol/L"}],
        }
    )

    assessment = result["indicators"][0]
    assert assessment["status"] == expected_status
    assert assessment.get("evaluation_reason") == expected_reason
    assert assessment["name"] == "Uric Acid"
    assert assessment["unit"] == "µmol/L"


@pytest.mark.asyncio
async def test_uric_acid_missing_age_fails_closed() -> None:
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    result = await reference_range_checker_node(
        {
            "patient_gender": "male",
            "raw_indicators": [{"name": "Uric acid", "value": 300, "unit": "umol/L"}],
        }
    )

    assessment = result["indicators"][0]
    assert assessment["status"] == "unknown"
    assert assessment.get("evaluation_reason") == "age_scope_not_supported"


@pytest.mark.asyncio
async def test_uric_acid_unsupported_unit_fails_closed() -> None:
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    result = await reference_range_checker_node(
        {
            "patient_age": 35,
            "patient_gender": "male",
            "raw_indicators": [{"name": "Acid Uric", "value": 5.0, "unit": "mg/dL"}],
        }
    )

    assessment = result["indicators"][0]
    assert assessment["status"] == "unknown"
    assert assessment.get("evaluation_reason") == "unit_not_supported"
    assert assessment["name"] == "Acid Uric"


@pytest.mark.asyncio
async def test_uric_acid_has_no_active_critical_rule() -> None:
    from src.agents.nodes.critical_detector_node import detect_critical_values_node
    from src.agents.nodes.reference_range_checker_node import reference_range_checker_node

    state = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [{"name": "Uric acid", "value": 10000, "unit": "umol/L"}],
    }
    reference_state = await reference_range_checker_node(state)
    critical_state = await detect_critical_values_node({**state, **reference_state})

    assessment = critical_state["indicators"][0]
    assert assessment["status"] == "high"
    assert assessment["is_critical"] is False
    assert assessment.get("critical_status") is None
    assert critical_state["critical_alerts"] == []
