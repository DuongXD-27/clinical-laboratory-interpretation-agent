"""
Data quality tests for the new reference data files.

CRIT-01: No duplicate `name` within explanations.json
CRIT-02: Canonical-only critical registry with no alias records
CRIT-03: All 9 approved analytes present in all 3 files (coverage + case consistency)
CRIT-04: Metric/unit match with units_metric.csv
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from src.services.analyte_resolver import LOCKED_35_ANALYTES

REPO_ROOT = Path(__file__).resolve().parents[2]

CRITICAL_PATH      = REPO_ROOT / "data/reference/critical_thresholds.json"
EXPLANATION_PATH   = REPO_ROOT / "data/reference/explanations.json"
REFERENCE_JSON_PATH = REPO_ROOT / "data/reference/reference_ranges.json"
UNITS_CSV_PATH     = REPO_ROOT / "data/reference/units_metric.csv"

# Canonical names as defined in reference_checker_config.json
APPROVED_ANALYTES = frozenset({
    "WBC", "RBC", "HGB", "HCT", "PLT", "Sodium", "Potassium",
    "Fasting plasma glucose", "Total bilirubin", "HbA1c", "LDL-C", "HDL-C", "Creatinine",
})

# Alias spellings forbidden as independent production registry records
_FORBIDDEN_CRITICAL_ALIASES = frozenset({
    "Kali",
    "Glucose",
    "Fasting Plasma Glucose",
    "Hemoglobin",
})

_CRITICAL_OPERATORS = frozenset({"<", "<=", ">", ">="})
_FINAL_PROVENANCE_KEYS = frozenset({
    "source_id",
    "source_title",
    "source_document_id",
    "source_revision",
    "source_date",
    "source_url",
    "source_page",
    "source_literal",
    "source_analyte_label",
    "population_context",
    "qualifier",
})
_INACTIVE_PROVENANCE_KEYS = frozenset({
    "source_id",
    "source_title",
    "source_document_id",
    "source_revision",
    "source_date",
    "source_url",
})
_ARUP_SOURCE_IDENTITY = {
    "source_id": "SRC-CRIT-ARUP-REV46",
    "source_title": "CRITICAL VALUES LIST",
    "source_document_id": "CORP-APPEND-0104A",
    "source_revision": "46",
    "source_date": "2026-04",
    "source_url": "https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf",
}
_EXPECTED_EXECUTION_MATRIX = {
    "WBC": (None, None, None, None, "10^9/L"),
    "RBC": (None, None, None, None, "10^12/L"),
    "HGB": (None, None, None, None, "g/L"),
    "HCT": (None, None, None, None, "L/L"),
    "MCV": (None, None, None, None, "fL"),
    "MCH": (None, None, None, None, "pg"),
    "MCHC": (None, None, None, None, "g/L"),
    "RDW-CV": (None, None, None, None, "%"),
    "PLT": (None, None, None, None, "10^9/L"),
    "Neutrophils %": (None, None, None, None, "%"),
    "Neutrophils abs": (None, None, None, None, "10^9/L"),
    "Lymphocytes %": (None, None, None, None, "%"),
    "Lymphocytes abs": (None, None, None, None, "10^9/L"),
    "Monocytes %": (None, None, None, None, "%"),
    "Monocytes abs": (None, None, None, None, "10^9/L"),
    "Eosinophils %": (None, None, None, None, "%"),
    "Eosinophils abs": (None, None, None, None, "10^9/L"),
    "Sodium": (120, "<", 160, ">", "mmol/L"),
    "Potassium": (3.0, "<", 6.1, ">", "mmol/L"),
    "Chloride": (None, None, None, None, "mmol/L"),
    "Fasting plasma glucose": (55, "<", 450, ">", "mg/dL"),
    "HbA1c": (None, None, None, None, "%"),
    "Creatinine": (None, None, None, None, "umol/L"),
    "Urea": (None, None, None, None, "mmol/L"),
    "Uric acid": (None, None, None, None, "umol/L"),
    "AST": (None, None, None, None, "U/L"),
    "ALT": (None, None, None, None, "U/L"),
    "GGT": (None, None, None, None, "U/L"),
    "Total bilirubin": (None, None, 15, ">", "mg/dL"),
    "Total protein": (None, None, None, None, "g/L"),
    "Albumin": (None, None, None, None, "g/L"),
    "Total cholesterol": (None, None, None, None, "mmol/L"),
    "Triglyceride": (None, None, None, None, "mmol/L"),
    "HDL-C": (None, None, None, None, "mmol/L"),
    "LDL-C": (None, None, None, None, "mmol/L"),
}
_EXPECTED_INACTIVE_REASONS = {
    "WBC": "SOURCE_ROW_RESTRICTED_U_OF_U_ONLY",
    "RBC": "NO_APPLICABLE_ARUP_REV46_RBC_COUNT_RULE",
    "HGB": "SOURCE_ROW_RESTRICTED_U_OF_U_ONLY",
    "HCT": "SOURCE_ROW_RESTRICTED_U_OF_U_ONLY",
    "MCV": "NO_APPLICABLE_ARUP_REV46_RULE",
    "MCH": "NO_APPLICABLE_ARUP_REV46_RULE",
    "MCHC": "NO_APPLICABLE_ARUP_REV46_RULE",
    "RDW-CV": "NO_APPLICABLE_ARUP_REV46_RULE",
    "PLT": "SOURCE_ROW_RESTRICTED_U_OF_U_ONLY",
    "Neutrophils %": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Neutrophils abs": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Lymphocytes %": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Lymphocytes abs": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Monocytes %": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Monocytes abs": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Eosinophils %": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Eosinophils abs": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Chloride": "NO_APPLICABLE_ARUP_REV46_RULE",
    "HbA1c": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Creatinine": "NO_APPLICABLE_ARUP_REV46_ADULT_RULE",
    "Urea": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Uric acid": "NO_APPLICABLE_ARUP_REV46_RULE",
    "AST": "NO_APPLICABLE_ARUP_REV46_RULE",
    "ALT": "NO_APPLICABLE_ARUP_REV46_RULE",
    "GGT": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Total protein": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Albumin": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Total cholesterol": "NO_APPLICABLE_ARUP_REV46_RULE",
    "Triglyceride": "NO_APPLICABLE_ARUP_REV46_RULE",
    "HDL-C": "NO_APPLICABLE_ARUP_REV46_RULE",
    "LDL-C": "NO_APPLICABLE_ARUP_REV46_RULE",
}


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_critical() -> dict:
    return json.loads(CRITICAL_PATH.read_text(encoding="utf-8"))

def _load_explanation() -> list[dict]:
    return json.loads(EXPLANATION_PATH.read_text(encoding="utf-8"))

def _load_reference() -> list[dict]:
    return json.loads(REFERENCE_JSON_PATH.read_text(encoding="utf-8"))

def _load_units_csv() -> dict[str, str]:
    """Return {test_name: standardized_unit}."""
    with UNITS_CSV_PATH.open(encoding="utf-8-sig", newline="") as f:
        return {row["test_name"]: row["standardized_unit"] for row in csv.DictReader(f)}

def _normalize_unit(unit: str) -> str:
    """Normalize µ/μ → u so µmol/L and umol/L compare equal."""
    return unit.replace("µ", "u").replace("μ", "u").strip()

def _csv_units_by_canonical(units_csv: dict[str, str]) -> dict[str, str]:
    """Build {canonical_lower: normalized_unit} from units_metric.csv."""
    return {test_name.lower(): _normalize_unit(unit) for test_name, unit in units_csv.items()}


def _validate_side_pair(
    record: dict,
    side: str,
    *,
    current_migration_compatibility: bool,
) -> list[str]:
    """Validate one threshold/operator pair for a staged schema mode."""
    errors: list[str] = []
    operator_key = f"{side}_operator"
    threshold = record.get(side)
    operator_present = operator_key in record
    operator = record.get(operator_key)

    if threshold is None:
        if not current_migration_compatibility and not operator_present:
            errors.append(f"{operator_key} must be explicit null for an inactive side")
        elif operator is not None:
            errors.append(f"{operator_key} must be null when {side} is null")
        return errors

    if isinstance(threshold, bool) or not isinstance(threshold, (int, float)):
        errors.append(f"{side} must be numeric or null")
        return errors

    if threshold < 0:
        if not current_migration_compatibility:
            errors.append(f"{side} cannot use a negative inactive sentinel")
        return errors

    if not operator_present:
        if not current_migration_compatibility:
            errors.append(f"{operator_key} is required for an active side")
    elif not isinstance(operator, str) or operator not in _CRITICAL_OPERATORS:
        errors.append(f"{operator_key} has invalid operator {operator!r}")

    return errors


def _validate_final_arup_record(record: dict) -> list[str]:
    """Validate the future final schema without applying it to current data."""
    errors = _validate_side_pair(
        record,
        "low",
        current_migration_compatibility=False,
    )
    errors.extend(_validate_side_pair(
        record,
        "high",
        current_migration_compatibility=False,
    ))

    has_active_side = any(
        isinstance(record.get(side), (int, float))
        and not isinstance(record.get(side), bool)
        and record[side] >= 0
        for side in ("low", "high")
    )
    if has_active_side:
        missing = sorted(key for key in _FINAL_PROVENANCE_KEYS if key not in record)
        if missing:
            errors.append(f"active rule missing provenance keys: {missing}")

    return errors


# ── CRIT-01 ──────────────────────────────────────────────────────────────────

def test_crit_01_no_duplicate_names_in_explanation_new():
    """Each analyte name must appear exactly once in explanations.json."""
    entries = _load_explanation()
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for i, entry in enumerate(entries):
        name = entry["name"]
        if name in seen:
            duplicates.append(f"'{name}' at index {seen[name]} and {i}")
        else:
            seen[name] = i
    assert not duplicates, (
        "Duplicate names in explanations.json:\n" + "\n".join(duplicates)
    )


# ── CRIT-02 ──────────────────────────────────────────────────────────────────

def test_crit_02_production_registry_is_canonical_only_without_alias_records():
    critical_keys = set(_load_critical())

    assert critical_keys == set(LOCKED_35_ANALYTES)
    assert critical_keys.isdisjoint(_FORBIDDEN_CRITICAL_ALIASES)
    assert len(critical_keys) == 35


# ── CRIT-03 ──────────────────────────────────────────────────────────────────

def test_crit_03a_approved_analytes_in_explanation_new():
    """All 9 approved analytes must be present in explanations.json (case-insensitive)."""
    names_lower = {e["name"].lower() for e in _load_explanation()}
    missing = [a for a in sorted(APPROVED_ANALYTES) if a.lower() not in names_lower]
    assert not missing, f"Missing from explanations.json: {missing}"


def test_crit_03b_approved_analytes_in_critical_thresholds():
    """Production critical registry contains exactly the 35 locked analytes."""
    assert set(_load_critical()) == set(LOCKED_35_ANALYTES)


def test_crit_03c_approved_analytes_in_reference_ranges():
    """All 9 approved analytes must be present in reference_ranges.json (case-insensitive)."""
    canonical_lower = {r["analyte_canonical"].lower() for r in _load_reference()}
    missing = [a for a in sorted(APPROVED_ANALYTES) if a.lower() not in canonical_lower]
    assert not missing, f"Missing from reference_ranges.json: {missing}"


def test_crit_03d_name_case_consistency_across_files():
    """
    For each approved analyte, the exact casing must be identical across all 3 files.
    Reports all mismatches so they can be reviewed together before any fix.
    """
    exp_names      = {e["name"].lower(): e["name"] for e in _load_explanation()}
    crit_canonicals = {key.lower(): key for key in _load_critical()}
    ref_names      = {r["analyte_canonical"].lower(): r["analyte_canonical"] for r in _load_reference()}

    mismatches: list[str] = []
    for analyte in sorted(APPROVED_ANALYTES):
        key = analyte.lower()
        exp_actual  = exp_names.get(key)
        crit_actual = crit_canonicals.get(key)
        ref_actual  = ref_names.get(key)

        all_actual = {n for n in (exp_actual, crit_actual, ref_actual) if n is not None}
        if len(all_actual) > 1:
            mismatches.append(
                f"  '{analyte}': "
                f"explanation_new={exp_actual!r}, "
                f"critical_thresholds={crit_actual!r}, "
                f"reference_ranges={ref_actual!r}"
            )

    assert not mismatches, (
        "Name case inconsistencies across files:\n" + "\n".join(mismatches)
    )


# ── CRIT-04 ──────────────────────────────────────────────────────────────────

def test_crit_04a_explanation_new_metric_vs_units_csv():
    """
    Each analyte's `metric` in explanations.json must match the
    standardized_unit in units_metric.csv (after alias resolution and µ normalization).
    """
    entries   = _load_explanation()
    csv_units = _csv_units_by_canonical(_load_units_csv())

    not_in_csv: list[str] = []
    mismatches: list[str] = []

    for entry in entries:
        name = entry["name"]
        if name not in APPROVED_ANALYTES:
            continue
        metric = entry.get("canonical_unit") or entry.get("metric", "")
        key = name.lower()

        if key not in csv_units:
            not_in_csv.append(f"  '{name}': not found in units_metric.csv")
            continue

        expected = csv_units[key]
        actual   = _normalize_unit(metric)
        if actual != expected:
            mismatches.append(
                f"  '{name}': metric='{metric}' (normalized='{actual}') "
                f"!= units_metric.csv='{expected}'"
            )

    errors = not_in_csv + mismatches
    assert not errors, (
        "Metric issues between explanations.json and units_metric.csv:\n"
        + "\n".join(errors)
    )


def test_crit_04b_critical_thresholds_unit_vs_units_csv():
    """Units match units_metric.csv except for the approved FPG conversion."""
    critical  = _load_critical()
    csv_units = _csv_units_by_canonical(_load_units_csv())

    not_in_csv: list[str] = []
    mismatches: list[str] = []
    for key, values in critical.items():
        canonical_lower = key.lower()

        if canonical_lower not in csv_units:
            not_in_csv.append(
                f"  '{key}': not found in units_metric.csv"
            )
            continue

        expected = csv_units[canonical_lower]
        actual   = _normalize_unit(values["unit"])
        approved_fpg_conversion = (
            key == "Fasting plasma glucose"
            and actual == "mg/dL"
            and expected == "mmol/L"
            and values.get("vmec_canonical_unit") == "mmol/L"
            and values.get("vmec_comparison_strategy") == "CONVERT_INPUT_TO_SOURCE_UNIT"
            and values.get("vmec_conversion_function") == "glucose_mmol_l_to_mg_dl"
            and values.get("vmec_conversion_authority") == "NIST-CAS-492-62-6-MW-180.1559"
            and values.get("vmec_conversion_scope") == "CRITICAL_LAYER_ONLY"
        )
        approved_bilirubin_conversion = (
            key == "Total bilirubin"
            and actual == "mg/dL"
            and expected == "umol/L"
            and values.get("vmec_canonical_unit") == "umol/L"
            and values.get("vmec_comparison_strategy") == "CONVERT_INPUT_TO_SOURCE_UNIT"
            and values.get("vmec_conversion_function") == "bilirubin_umol_l_to_mg_dl"
            and values.get("vmec_conversion_authority") == "NIST-CAS-635-65-4-MW-584.66"
            and values.get("vmec_conversion_scope") == "CRITICAL_LAYER_ONLY"
        )
        if approved_fpg_conversion or approved_bilirubin_conversion:
            continue
        if actual != expected:
            mismatches.append(
                f"  '{key}': unit='{values['unit']}' (normalized='{actual}') "
                f"!= units_metric.csv='{expected}'"
            )

    errors = not_in_csv + mismatches
    assert not errors, (
        "Unit issues between critical_thresholds.json and units_metric.csv:\n"
        + "\n".join(errors)
    )


# ── CRIT-05: FINAL PRODUCTION SCHEMA ────────────────────────────────────────

def test_crit_05_production_uses_final_operator_schema_not_legacy_compatibility():
    """Patch C production must never depend on LEGACY_OPERATOR_DEFAULT."""
    errors: list[str] = []
    for analyte, record in _load_critical().items():
        for side in ("low", "high"):
            side_errors = _validate_side_pair(
                record,
                side,
                current_migration_compatibility=False,
            )
            errors.extend(f"{analyte}.{side}: {error}" for error in side_errors)

    assert not errors, "Final production schema errors:\n" + "\n".join(errors)


# ── CRIT-06: FINAL_ARUP_SCHEMA_VALIDATION samples ──────────────────────────

@pytest.mark.parametrize(
    ("record", "expected_valid"),
    [
        ({"low": 3.0, "low_operator": "<"}, True),
        ({"low": 3.0, "low_operator": None}, False),
        ({"low": None, "low_operator": "<"}, False),
        ({"low": 3.0, "low_operator": "="}, False),
        ({"low": 3.0, "low_operator": ["<"]}, False),
        ({"low": None, "low_operator": None}, True),
    ],
)
def test_crit_06_final_side_operator_pair_validation(record, expected_valid):
    errors = _validate_side_pair(
        record,
        "low",
        current_migration_compatibility=False,
    )
    assert (not errors) is expected_valid


def test_crit_06_final_schema_rejects_negative_sentinel():
    errors = _validate_side_pair(
        {"low": -1.0, "low_operator": None},
        "low",
        current_migration_compatibility=False,
    )
    assert any("negative inactive sentinel" in error for error in errors)


def test_crit_06_final_active_record_requires_provenance():
    record = {
        "low": 3.0,
        "low_operator": "<",
        "high": 6.1,
        "high_operator": ">",
        "unit": "mmol/L",
    }
    errors = _validate_final_arup_record(record)
    assert any("missing provenance keys" in error for error in errors)


def test_crit_06_final_active_record_with_provenance_is_valid():
    record = {
        "low": 3.0,
        "low_operator": "<",
        "high": 6.1,
        "high_operator": ">",
        "unit": "mmol/L",
        "source_id": "SRC-CRIT-ARUP-REV46",
        "source_title": "CRITICAL VALUES LIST",
        "source_document_id": "CORP-APPEND-0104A",
        "source_revision": "46",
        "source_date": "2026-04",
        "source_url": "https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf",
        "source_page": 1,
        "source_literal": "<3.0 or >6.1 mmol/L",
        "source_analyte_label": "Potassium",
        "population_context": None,
        "qualifier": None,
    }
    assert _validate_final_arup_record(record) == []


# CRIT-07: PATCH C PRODUCTION ARUP REV.46 HARD GATES

def test_crit_07a_production_execution_matrix_is_exact():
    critical = _load_critical()
    actual = {
        analyte: (
            record.get("low"),
            record.get("low_operator"),
            record.get("high"),
            record.get("high_operator"),
            record.get("unit"),
        )
        for analyte, record in critical.items()
    }

    assert actual == _EXPECTED_EXECUTION_MATRIX


def test_crit_07b_all_production_records_use_arup_rev46_identity():
    errors = []
    for analyte, record in _load_critical().items():
        for field, expected in _ARUP_SOURCE_IDENTITY.items():
            if record.get(field) != expected:
                errors.append(f"{analyte}.{field}={record.get(field)!r}, expected {expected!r}")

    assert not errors, "ARUP source identity errors:\n" + "\n".join(errors)


def test_crit_07c_active_rules_have_complete_provenance_and_exact_source_literals():
    critical = _load_critical()
    active = {
        analyte: record
        for analyte, record in critical.items()
        if record["low"] is not None or record["high"] is not None
    }

    assert set(active) == {"Sodium", "Potassium", "Fasting plasma glucose", "Total bilirubin"}
    assert all(_validate_final_arup_record(record) == [] for record in active.values())
    assert active["Sodium"]["source_literal"] == "< 120 or > 160 mmol/L"
    assert active["Sodium"]["source_analyte_label"] == "Sodium"
    assert active["Sodium"]["source_page"] == 1
    assert active["Potassium"]["source_literal"] == "< 3.0 or > 6.1 mmol/L"
    assert active["Potassium"]["source_analyte_label"] == "Potassium"
    assert active["Potassium"]["source_page"] == 1
    assert active["Potassium"]["population_context"] is None
    assert active["Potassium"]["qualifier"] is None
    assert active["Fasting plasma glucose"]["source_literal"] == "< 55 or > 450 mg/dL"
    assert active["Fasting plasma glucose"]["source_analyte_label"] == "Glucose"
    assert active["Fasting plasma glucose"]["source_page"] == 1
    assert active["Fasting plasma glucose"]["population_context"] == ">30 days to adult"
    assert active["Fasting plasma glucose"]["qualifier"] is None
    assert active["Total bilirubin"]["source_literal"] == "> 15 mg/dL"
    assert active["Total bilirubin"]["source_analyte_label"] == "Bilirubin, Total"
    assert active["Total bilirubin"]["source_page"] == 1


def test_crit_07d_inactive_rules_are_explicit_and_auditable():
    critical = _load_critical()

    for analyte, expected_reason in _EXPECTED_INACTIVE_REASONS.items():
        record = critical[analyte]
        assert record["low"] is None
        assert record["low_operator"] is None
        assert record["high"] is None
        assert record["high_operator"] is None
        assert record["inactive_reason"] == expected_reason
        assert not (_INACTIVE_PROVENANCE_KEYS - set(record))

    restricted_qualifier = "Test performed for University of Utah Health System only"
    assert critical["WBC"]["source_analyte_label"] == "White Blood Cell Count"
    assert critical["WBC"]["qualifier"] == restricted_qualifier
    assert critical["HGB"]["source_analyte_label"] == "Hemoglobin"
    assert critical["HGB"]["qualifier"] == restricted_qualifier
    assert critical["HCT"]["source_analyte_label"] == "Hematocrit"
    assert critical["HCT"]["qualifier"] == restricted_qualifier
    assert critical["PLT"]["source_analyte_label"] == "Platelet Count"
    assert critical["PLT"]["qualifier"] == restricted_qualifier


def test_crit_07e_no_negative_sentinels_or_legacy_missing_operators():
    critical = _load_critical()
    sentinel_count = 0
    missing_operator_count = 0

    for record in critical.values():
        for side in ("low", "high"):
            threshold = record[side]
            if isinstance(threshold, (int, float)) and not isinstance(threshold, bool) and threshold < 0:
                sentinel_count += 1
            if threshold is not None and f"{side}_operator" not in record:
                missing_operator_count += 1

    assert sentinel_count == 0
    assert missing_operator_count == 0


def test_crit_07f_fpg_conversion_metadata_is_exact():
    record = _load_critical()["Fasting plasma glucose"]

    assert record["vmec_canonical_unit"] == "mmol/L"
    assert record["vmec_comparison_strategy"] == "CONVERT_INPUT_TO_SOURCE_UNIT"
    assert record["vmec_conversion_function"] == "glucose_mmol_l_to_mg_dl"
    assert record["vmec_conversion_authority"] == "NIST-CAS-492-62-6-MW-180.1559"
    assert record["vmec_conversion_scope"] == "CRITICAL_LAYER_ONLY"
