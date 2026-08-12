"""
Data quality tests for the new reference data files.

CRIT-01: No duplicate `name` within explanation_new.json
CRIT-02: Alias value consistency within critical_thresholds.json
CRIT-03: All 9 approved analytes present in all 3 files (coverage + case consistency)
CRIT-04: Metric/unit match with units_metric.csv
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

CRITICAL_PATH      = REPO_ROOT / "data/reference/critical_thresholds.json"
EXPLANATION_PATH   = REPO_ROOT / "data/reference/explanation_new.json"
REFERENCE_JSON_PATH = REPO_ROOT / "data/reference/reference_ranges_v2.json"
UNITS_CSV_PATH     = REPO_ROOT / "data/reference/units_metric.csv"

# Canonical names as defined in reference_checker_v2_config.json
APPROVED_ANALYTES = frozenset({
    "WBC", "RBC", "HGB", "Fasting plasma glucose",
    "HbA1c", "LDL-C", "HDL-C", "Creatinine", "Potassium",
})

# Aliases present as keys in critical_thresholds.json → canonical name
_CRITICAL_ALIASES: dict[str, str] = {
    "Kali":                  "Potassium",
    "Glucose":               "Fasting plasma glucose",
    "Fasting Plasma Glucose": "Fasting plasma glucose",
    "Hemoglobin":            "HGB",
}

# Canonical analyte → test_name in units_metric.csv (from unit_map_aliases in config)
_CANONICAL_TO_CSV_NAME: dict[str, str] = {
    "Fasting plasma glucose": "Fasting Blood Glucose",
    "LDL-C":                  "LDL-Cholesterol",
    "HDL-C":                  "HDL-Cholesterol",
    "Potassium":              "Potassium (K+)",
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

def _canonical(key: str) -> str:
    """Resolve a critical_thresholds key to its canonical analyte name."""
    return _CRITICAL_ALIASES.get(key, key)

def _normalize_unit(unit: str) -> str:
    """Normalize µ/μ → u so µmol/L and umol/L compare equal."""
    return unit.replace("µ", "u").replace("μ", "u").strip()

def _csv_units_by_canonical(units_csv: dict[str, str]) -> dict[str, str]:
    """Build {canonical_lower: normalized_unit} from units_metric.csv."""
    result: dict[str, str] = {}
    for test_name, unit in units_csv.items():
        canonical = next(
            (c for c, t in _CANONICAL_TO_CSV_NAME.items() if t == test_name),
            test_name,
        )
        result[canonical.lower()] = _normalize_unit(unit)
    return result


# ── CRIT-01 ──────────────────────────────────────────────────────────────────

def test_crit_01_no_duplicate_names_in_explanation_new():
    """Each analyte name must appear exactly once in explanation_new.json."""
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
        "Duplicate names in explanation_new.json:\n" + "\n".join(duplicates)
    )


# ── CRIT-02 ──────────────────────────────────────────────────────────────────

def test_crit_02_alias_values_consistent_in_critical_thresholds():
    """
    Alias pairs (e.g. Kali/Potassium) must have identical low, high, and unit.
    A value mismatch means one alias was updated without updating the other.
    """
    critical = _load_critical()

    by_canonical: dict[str, list[str]] = {}
    for key in critical:
        by_canonical.setdefault(_canonical(key), []).append(key)

    mismatches: list[str] = []
    for canonical_name, keys in by_canonical.items():
        if len(keys) < 2:
            continue
        ref_key = keys[0]
        ref_val = critical[ref_key]
        for other_key in keys[1:]:
            other_val = critical[other_key]
            diffs = [
                f"{field}: '{ref_key}'={ref_val[field]!r} vs '{other_key}'={other_val[field]!r}"
                for field in ("low", "high", "unit")
                if ref_val[field] != other_val[field]
            ]
            if diffs:
                mismatches.append(
                    f"Alias mismatch for '{canonical_name}': " + ", ".join(diffs)
                )

    assert not mismatches, (
        "Alias value mismatches in critical_thresholds.json:\n" + "\n".join(mismatches)
    )


# ── CRIT-03 ──────────────────────────────────────────────────────────────────

def test_crit_03a_approved_analytes_in_explanation_new():
    """All 9 approved analytes must be present in explanation_new.json (case-insensitive)."""
    names_lower = {e["name"].lower() for e in _load_explanation()}
    missing = [a for a in sorted(APPROVED_ANALYTES) if a.lower() not in names_lower]
    assert not missing, f"Missing from explanation_new.json: {missing}"


def test_crit_03b_approved_analytes_in_critical_thresholds():
    """All 9 approved analytes must be present in critical_thresholds.json (case-insensitive, via aliases)."""
    covered_lower = {_canonical(k).lower() for k in _load_critical()}
    missing = [a for a in sorted(APPROVED_ANALYTES) if a.lower() not in covered_lower]
    assert not missing, f"Missing from critical_thresholds.json: {missing}"


def test_crit_03c_approved_analytes_in_reference_ranges():
    """All 9 approved analytes must be present in reference_ranges_v2.json (case-insensitive)."""
    canonical_lower = {r["analyte_canonical"].lower() for r in _load_reference()}
    missing = [a for a in sorted(APPROVED_ANALYTES) if a.lower() not in canonical_lower]
    assert not missing, f"Missing from reference_ranges_v2.json: {missing}"


def test_crit_03d_name_case_consistency_across_files():
    """
    For each approved analyte, the exact casing must be identical across all 3 files.
    Reports all mismatches so they can be reviewed together before any fix.
    """
    exp_names      = {e["name"].lower(): e["name"] for e in _load_explanation()}
    crit_canonicals = {_canonical(k).lower(): _canonical(k) for k in _load_critical()}
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
    Each analyte's `metric` in explanation_new.json must match the
    standardized_unit in units_metric.csv (after alias resolution and µ normalization).
    """
    entries   = _load_explanation()
    csv_units = _csv_units_by_canonical(_load_units_csv())

    not_in_csv: list[str] = []
    mismatches: list[str] = []

    for entry in entries:
        name = entry["name"]
        metric = entry.get("metric", "")
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
        "Metric issues between explanation_new.json and units_metric.csv:\n"
        + "\n".join(errors)
    )


def test_crit_04b_critical_thresholds_unit_vs_units_csv():
    """
    Each canonical analyte's `unit` in critical_thresholds.json must match
    the standardized_unit in units_metric.csv (after µ normalization).
    Alias duplicates are checked once per canonical.
    """
    critical  = _load_critical()
    csv_units = _csv_units_by_canonical(_load_units_csv())

    not_in_csv: list[str] = []
    mismatches: list[str] = []
    seen: set[str] = set()

    for key, values in critical.items():
        canonical       = _canonical(key)
        canonical_lower = canonical.lower()
        if canonical_lower in seen:
            continue
        seen.add(canonical_lower)

        if canonical_lower not in csv_units:
            not_in_csv.append(
                f"  '{key}' (canonical='{canonical}'): not found in units_metric.csv"
            )
            continue

        expected = csv_units[canonical_lower]
        actual   = _normalize_unit(values["unit"])
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
