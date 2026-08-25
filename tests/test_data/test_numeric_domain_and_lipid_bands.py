import json
import math
import pytest
from decimal import Decimal
from pathlib import Path

from src.services.analyte_resolver import LOCKED_35_ANALYTES, ANALYTE_RULE_TYPES, FROZEN_CLINICAL_RULE_BANDS
from src.services.reference_repository import ReferenceRepository
from src.services.measurement_conversion import (
    validate_numeric_measurement,
    is_valid_numeric_measurement,
    classify_lipid_band,
    cholesterol_mg_dl_to_mmol_l,
    cholesterol_mmol_l_to_mg_dl,
    triglyceride_mg_dl_to_mmol_l,
    triglyceride_mmol_l_to_mg_dl,
    glucose_mmol_l_to_mg_dl,
    bilirubin_umol_l_to_mg_dl,
)
from src.agents.nodes.reference_range_checker_node import (
    _classify,
    _parse_value,
    reference_range_checker_node,
)
from src.agents.nodes.critical_detector_node import detect_critical_values_node


def test_numeric_domain_validator_valid_inputs():
    assert validate_numeric_measurement(0) == Decimal("0")
    assert validate_numeric_measurement(5.5) == Decimal("5.5")
    assert validate_numeric_measurement("12.34") == Decimal("12.34")
    assert validate_numeric_measurement(Decimal("100")) == Decimal("100")


@pytest.mark.parametrize(
    "invalid_input",
    [
        -1,
        -0.0001,
        "-5.6",
        float("nan"),
        float("inf"),
        float("-inf"),
        "NaN",
        "Infinity",
        "-Infinity",
        None,
        "",
        "abc",
    ],
)
def test_numeric_domain_validator_rejects_invalid(invalid_input):
    with pytest.raises(ValueError):
        validate_numeric_measurement(invalid_input)
    assert is_valid_numeric_measurement(invalid_input) is False


@pytest.mark.asyncio
async def test_negative_and_nonfinite_fail_closed_in_pipeline():
    test_cases = [
        ("Fasting plasma glucose", -1.0, "mmol/L"),
        ("HbA1c", -1.0, "%"),
        ("Total cholesterol", -1.0, "mmol/L"),
        ("Triglyceride", -1.0, "mmol/L"),
        ("HDL-C", -1.0, "mmol/L"),
        ("LDL-C", -1.0, "mmol/L"),
        ("AST", -1.0, "U/L"),
        ("ALT", -1.0, "U/L"),
        ("GGT", -1.0, "U/L"),
        ("Total bilirubin", -1.0, "µmol/L"),
        ("Sodium", -0.0001, "mmol/L"),
        ("Potassium", float("nan"), "mmol/L"),
        ("Potassium", float("inf"), "mmol/L"),
        ("Potassium", float("-inf"), "mmol/L"),
    ]

    for analyte, val, unit in test_cases:
        state = {
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-08-18",
            "raw_indicators": [{"name": analyte, "value": val, "unit": unit}],
        }
        res_state = await reference_range_checker_node(state)
        crit_state = await detect_critical_values_node({**state, **res_state})
        ind = crit_state["indicators"][0]

        assert ind["status"] == "unknown"
        assert ind["is_abnormal"] is False
        assert ind["is_critical"] is False
        assert ind.get("critical_status") is None
        assert crit_state["critical_alerts"] == []


@pytest.mark.parametrize(
    ("analyte", "threshold_mg_dl"),
    [
        ("Total cholesterol", Decimal("200")),
        ("Total cholesterol", Decimal("240")),
        ("Triglyceride", Decimal("150")),
        ("Triglyceride", Decimal("200")),
        ("Triglyceride", Decimal("500")),
        ("HDL-C", Decimal("40")),
        ("HDL-C", Decimal("60")),
        ("LDL-C", Decimal("100")),
        ("LDL-C", Decimal("130")),
        ("LDL-C", Decimal("160")),
        ("LDL-C", Decimal("190")),
    ],
)
def test_lipid_native_canonical_equivalence(analyte, threshold_mg_dl):
    epsilon = Decimal("0.0001")
    for delta in (-epsilon, Decimal("0"), epsilon):
        native_val = threshold_mg_dl + delta
        native_cls = classify_lipid_band(analyte, native_val, "mg/dL")

        if analyte == "Triglyceride":
            canonical_val = triglyceride_mg_dl_to_mmol_l(native_val)
        else:
            canonical_val = cholesterol_mg_dl_to_mmol_l(native_val)

        canonical_cls = classify_lipid_band(analyte, canonical_val, "mmol/L")
        assert native_cls == canonical_cls


def test_reference_scope_and_contract_counts():
    repo_root = Path(__file__).resolve().parents[2]
    with open(repo_root / "data/reference/reference_ranges.json", encoding="utf-8") as f:
        rr = json.load(f)

    unique_analytes = sorted(list(set(r["analyte_canonical"] for r in rr)))
    assert len(unique_analytes) == 35
    assert set(unique_analytes) == set(LOCKED_35_ANALYTES)

    # Rule type verification
    rule_types_by_analyte = {}
    for r in rr:
        rule_types_by_analyte.setdefault(r["analyte_canonical"], set()).add(r["reference_type"])

    assert rule_types_by_analyte["Total cholesterol"] == {"BAND"}
    assert rule_types_by_analyte["Triglyceride"] == {"BAND"}
    assert rule_types_by_analyte["HDL-C"] == {"BAND"}
    assert rule_types_by_analyte["LDL-C"] == {"BAND"}
    assert rule_types_by_analyte["Fasting plasma glucose"] == {"CDL"}
    assert rule_types_by_analyte["HbA1c"] == {"CDL"}
    assert rule_types_by_analyte["AST"] == {"ONE_SIDED_LIMIT"}
    assert rule_types_by_analyte["ALT"] == {"ONE_SIDED_LIMIT"}
    assert rule_types_by_analyte["GGT"] == {"ONE_SIDED_LIMIT"}
    assert rule_types_by_analyte["Total bilirubin"] == {"ONE_SIDED_LIMIT"}

    # Count unique operational types
    operational_counts = {"RI": 0, "BAND": 0, "CDL": 0, "ONE_SIDED_LIMIT": 0}
    for name, types in rule_types_by_analyte.items():
        t = list(types)[0]
        operational_counts[t] += 1

    assert operational_counts == {"RI": 25, "BAND": 4, "CDL": 2, "ONE_SIDED_LIMIT": 4}
    assert len(rr) == 67
