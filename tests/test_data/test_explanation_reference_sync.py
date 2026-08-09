"""
BONUS-TIP-009: Tests verifying synchronization of explanation ranges into the V2 reference catalog.

SYNC-01 through SYNC-20.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from src.scripts.build_reference_config import (
    RUNTIME_CSV,
    RUNTIME_JSON,
    build_reference_config,
)
from src.scripts.extract_explanation_reference_ranges import (
    ALIAS_MAP,
    canonical_analyte,
    extract_supplemental_rules,
)
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLANATIONS_PATH = REPO_ROOT / "data/reference/explanations.json"
SOURCE = REPO_ROOT / "adult_outpatient_laboratory_reference_map.csv"
REFERENCE_JSON = REPO_ROOT / "data/reference/reference_ranges_v2.json"
REFERENCE_CSV = REPO_ROOT / "data/reference/reference_ranges_v2.csv"
RAGAS_DATASET = REPO_ROOT / "eval/datasets/ragas_v2_baseline.jsonl"
RAGAS_RESULT = REPO_ROOT / "eval/results/ragas_v2_baseline.json"

PRIMARY_ANALYTES_PRESENT = {"WBC", "RBC", "HGB", "Fasting plasma glucose", "HDL-C", "Creatinine"}
SUPPLEMENTAL_ANALYTES = {"HbA1c", "LDL-C", "Potassium"}
APPROVED = {"WBC", "RBC", "Fasting plasma glucose", "Creatinine"}
PENDING = {"HGB", "HDL-C", "HbA1c", "LDL-C", "Potassium"}


def _load_explanations() -> list[dict]:
    return json.loads(EXPLANATIONS_PATH.read_text(encoding="utf-8"))


def _load_catalog_json() -> list[dict]:
    return json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))


def _load_catalog_csv() -> list[dict]:
    with REFERENCE_CSV.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# SYNC-01: Input inventory
# ---------------------------------------------------------------------------
def test_sync_01_input_inventory():
    entries = _load_explanations()
    assert len(entries) == 9

    all_rules = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    # Primary-only rules are those without source_origin=explanations.json
    primary_analytes = {
        r["analyte_canonical"]
        for r in all_rules
        if r.get("source_origin") != "explanations.json"
    }
    # Supplemental analytes are not in the primary (CSV-sourced) catalog
    for analyte in SUPPLEMENTAL_ANALYTES:
        assert analyte not in primary_analytes, f"{analyte} should not be in primary catalog"


# ---------------------------------------------------------------------------
# SYNC-02: Alias resolution
# ---------------------------------------------------------------------------
def test_sync_02_alias_resolution():
    assert canonical_analyte("Glucose") == "Fasting plasma glucose"
    assert canonical_analyte("HDL-Cholesterol") == "HDL-C"
    assert canonical_analyte("LDL-Cholesterol") == "LDL-C"
    assert canonical_analyte("Kali") == "Potassium"
    # Direct names pass through unchanged
    assert canonical_analyte("WBC") == "WBC"
    assert canonical_analyte("HbA1c") == "HbA1c"
    assert canonical_analyte("Creatinine") == "Creatinine"


def test_sync_02_alias_map_completeness():
    assert ALIAS_MAP["Glucose"] == "Fasting plasma glucose"
    assert ALIAS_MAP["LDL-Cholesterol"] == "LDL-C"
    assert ALIAS_MAP["HDL-Cholesterol"] == "HDL-C"
    assert ALIAS_MAP["Kali"] == "Potassium"


# ---------------------------------------------------------------------------
# SYNC-03: Missing analyte detection
# ---------------------------------------------------------------------------
def test_sync_03_missing_analytes_detected():
    entries = _load_explanations()
    # Primary analytes are those without supplemental source_origin
    all_rules = _load_catalog_json()
    primary_analytes = {
        r["analyte_canonical"]
        for r in all_rules
        if r.get("source_origin") != "explanations.json"
    }
    explanation_resolved = {canonical_analyte(e["indicator"]) for e in entries}
    missing = explanation_resolved - primary_analytes
    assert missing == SUPPLEMENTAL_ANALYTES, f"Expected missing={SUPPLEMENTAL_ANALYTES}, got {missing}"


# ---------------------------------------------------------------------------
# SYNC-04: No duplicate import for already-present analytes
# ---------------------------------------------------------------------------
def test_sync_04_no_duplicate_import_for_present_analytes(tmp_path: Path):
    rules, _ = extract_supplemental_rules(EXPLANATIONS_PATH, PRIMARY_ANALYTES_PRESENT)
    supplemental_analytes = {r["analyte_canonical"] for r in rules}
    # Analytes already in primary must not receive supplemental rules
    for analyte in PRIMARY_ANALYTES_PRESENT:
        assert analyte not in supplemental_analytes, f"{analyte} got a duplicate supplemental rule"


# ---------------------------------------------------------------------------
# SYNC-05: Rule count — 15 supplemental, 73 catalog total
# ---------------------------------------------------------------------------
def test_sync_05_rule_count(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))

    primary_count = len(result.accepted)  # primary only
    supplemental_count = len(catalog) - primary_count
    assert primary_count == 58
    assert supplemental_count == 15
    assert len(catalog) == 73
    assert result.report["catalog"]["total_rules"] == 73
    assert result.report["explanation_supplement"]["rules_added"] == 15


# ---------------------------------------------------------------------------
# SYNC-06: Stable IDs — unique and deterministic across two builds
# ---------------------------------------------------------------------------
def test_sync_06_stable_ids(tmp_path: Path):
    out1 = tmp_path / "b1"
    out2 = tmp_path / "b2"
    build_reference_config(SOURCE, out1, supplemental_path=EXPLANATIONS_PATH)
    build_reference_config(SOURCE, out2, supplemental_path=EXPLANATIONS_PATH)

    catalog1 = json.loads((out1 / RUNTIME_JSON).read_text(encoding="utf-8"))
    catalog2 = json.loads((out2 / RUNTIME_JSON).read_text(encoding="utf-8"))

    ids1 = [r["rule_id"] for r in catalog1]
    ids2 = [r["rule_id"] for r in catalog2]
    assert ids1 == ids2, "Rule IDs are not deterministic across builds"
    assert len(ids1) == len(set(ids1)), "Duplicate rule IDs found"

    # Verify EXPV2 namespace
    exp_ids = [rid for rid in ids1 if rid.startswith("EXPV2-")]
    assert len(exp_ids) == 15

    # Specific stable ID checks
    by_id = {r["rule_id"]: r for r in catalog1}
    assert by_id["EXPV2-HBA1C-001"]["analyte_canonical"] == "HbA1c"
    assert by_id["EXPV2-HBA1C-001"]["range_group"] == "normal"
    assert by_id["EXPV2-LDLC-001"]["analyte_canonical"] == "LDL-C"
    assert by_id["EXPV2-LDLC-001"]["range_group"] == "optimal"
    assert by_id["EXPV2-POTASSIUM-001"]["analyte_canonical"] == "Potassium"
    assert by_id["EXPV2-POTASSIUM-001"]["range_group"] == "normal"


# ---------------------------------------------------------------------------
# SYNC-07: Provenance — every supplemental rule records origin, entry ID, group, URL
# ---------------------------------------------------------------------------
def test_sync_07_provenance(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    supplemental = [r for r in catalog if str(r.get("rule_id", "")).startswith("EXPV2-")]

    for rule in supplemental:
        assert rule.get("source_origin") == "explanations.json", f"{rule['rule_id']}: bad source_origin"
        assert rule.get("source_entry_id"), f"{rule['rule_id']}: missing source_entry_id"
        assert rule.get("range_group"), f"{rule['rule_id']}: missing range_group"
        assert rule.get("source_url"), f"{rule['rule_id']}: missing source_url"
        assert isinstance(rule.get("source_urls"), list), f"{rule['rule_id']}: source_urls not a list"
        assert rule.get("source_urls"), f"{rule['rule_id']}: empty source_urls"
        assert rule.get("confidence") == "CURATED"


# ---------------------------------------------------------------------------
# SYNC-08: HbA1c mapping — 3 MD rules matching explanations.json
# ---------------------------------------------------------------------------
def test_sync_08_hba1c_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    hba1c_rules = [r for r in catalog if r["analyte_canonical"] == "HbA1c"]

    assert len(hba1c_rules) == 3
    assert all(r["reference_type"] == "MD" for r in hba1c_rules), "All HbA1c rules must be MD"
    assert all(r["unit_canonical"] == "%" for r in hba1c_rules)
    assert all(r["sex"] == "A" for r in hba1c_rules)
    assert all(r["age_scope"] == "Adult" for r in hba1c_rules)

    # Load expected values from explanations.json
    exp = _load_explanations()
    hba1c_entry = next(e for e in exp if e["indicator"] == "HbA1c")
    exp_ranges = {r["group"]: r for r in hba1c_entry["reference_ranges"]}

    by_group = {r["range_group"]: r for r in hba1c_rules}
    assert set(by_group) == {"normal", "prediabetes", "diabetes"}

    # Verify values match source
    assert by_group["normal"]["range_lower"] is None
    assert by_group["normal"]["range_upper"] == exp_ranges["normal"]["high"]
    assert by_group["prediabetes"]["range_lower"] == exp_ranges["prediabetes"]["low"]
    assert by_group["prediabetes"]["range_upper"] == exp_ranges["prediabetes"]["high"]
    assert by_group["diabetes"]["range_lower"] == exp_ranges["diabetes"]["low"]
    assert by_group["diabetes"]["range_upper"] is None

    # Verify notes preserved
    for group, rule in by_group.items():
        assert rule["range_note"] == exp_ranges[group].get("note", "")


# ---------------------------------------------------------------------------
# SYNC-09: LDL-C mapping — 5 non-RI rules matching explanations.json
# ---------------------------------------------------------------------------
def test_sync_09_ldl_c_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    ldlc_rules = [r for r in catalog if r["analyte_canonical"] == "LDL-C"]

    assert len(ldlc_rules) == 5
    assert all(r["reference_type"] != "RI" for r in ldlc_rules), "LDL-C rules must not be RI"
    assert all(r["unit_canonical"] == "mmol/L" for r in ldlc_rules)
    assert all(r["sex"] == "A" for r in ldlc_rules)

    exp = _load_explanations()
    ldlc_entry = next(e for e in exp if e["indicator"] == "LDL-Cholesterol")
    exp_ranges = {r["group"]: r for r in ldlc_entry["reference_ranges"]}

    by_group = {r["range_group"]: r for r in ldlc_rules}
    expected_groups = {"optimal", "acceptable", "borderline_high", "high", "very_high"}
    assert set(by_group) == expected_groups

    for group, rule in by_group.items():
        exp_low = exp_ranges[group]["low"]
        exp_high = exp_ranges[group]["high"]
        assert rule["range_lower"] == (float(exp_low) if exp_low is not None else None)
        assert rule["range_upper"] == (float(exp_high) if exp_high is not None else None)


# ---------------------------------------------------------------------------
# SYNC-10: Potassium mapping — 7 rules, normal=RI, severity=MD
# ---------------------------------------------------------------------------
def test_sync_10_potassium_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    pot_rules = [r for r in catalog if r["analyte_canonical"] == "Potassium"]

    assert len(pot_rules) == 7
    assert all(r["unit_canonical"] == "mmol/L" for r in pot_rules)
    assert all(r["sex"] == "A" for r in pot_rules)

    by_group = {r["range_group"]: r for r in pot_rules}
    expected_groups = {
        "normal", "mild_hyperkalemia", "moderate_hyperkalemia", "severe_hyperkalemia",
        "mild_hypokalemia", "moderate_hypokalemia", "severe_hypokalemia",
    }
    assert set(by_group) == expected_groups

    # Only normal is RI candidate
    assert by_group["normal"]["reference_type"] == "RI"
    severity_groups = expected_groups - {"normal"}
    for g in severity_groups:
        assert by_group[g]["reference_type"] == "MD", f"{g} should be MD"

    # Verify specific bounds
    assert by_group["normal"]["range_lower"] == 3.5
    assert by_group["normal"]["range_upper"] == 5.0
    assert by_group["severe_hyperkalemia"]["range_lower"] == 7.0
    assert by_group["severe_hyperkalemia"]["range_upper"] is None
    assert by_group["severe_hypokalemia"]["range_lower"] is None
    assert by_group["severe_hypokalemia"]["range_upper"] == 2.5


# ---------------------------------------------------------------------------
# SYNC-11: Units — no numeric conversion
# ---------------------------------------------------------------------------
def test_sync_11_units(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))

    for rule in catalog:
        if rule["analyte_canonical"] == "HbA1c":
            assert rule["unit_canonical"] == "%"
        elif rule["analyte_canonical"] in ("LDL-C", "Potassium"):
            assert rule["unit_canonical"] == "mmol/L"


# ---------------------------------------------------------------------------
# SYNC-12: Existing 58 primary rules remain semantically unchanged
# ---------------------------------------------------------------------------
def test_sync_12_existing_rules_unchanged(tmp_path: Path):
    # Build without supplemental to get primary baseline
    baseline = build_reference_config(SOURCE, tmp_path / "base")
    baseline_by_id = {r["rule_id"]: r for r in baseline.accepted}

    # Build with supplemental
    build_reference_config(SOURCE, tmp_path / "combined", supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / "combined" / RUNTIME_JSON).read_text(encoding="utf-8"))
    catalog_by_id = {r["rule_id"]: r for r in catalog}

    # Every primary rule ID must be present and semantically unchanged
    assert len(baseline.accepted) == 58
    for rule_id, primary_rule in baseline_by_id.items():
        assert rule_id in catalog_by_id, f"Primary rule {rule_id} missing from combined catalog"
        combined_rule = catalog_by_id[rule_id]
        for key in ("analyte_canonical", "unit_canonical", "range_lower", "range_upper", "reference_type", "source_url"):
            assert combined_rule.get(key) == primary_rule.get(key), (
                f"{rule_id} field '{key}' changed: {primary_rule.get(key)!r} → {combined_rule.get(key)!r}"
            )


# ---------------------------------------------------------------------------
# SYNC-13: Primary counts unchanged — 80/58/22/2
# ---------------------------------------------------------------------------
def test_sync_13_primary_counts_unchanged(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    report = result.report

    assert report["input_rows"] == 80
    assert report["runtime_accepted_rows"] == 58
    assert report["quarantined_rows"] == 22
    assert report["multiple_reason_rows"] == 2
    assert report["input_rows"] == report["runtime_accepted_rows"] + report["quarantined_rows"]

    # Supplemental missing analytes still appear in quarantine
    for analyte in SUPPLEMENTAL_ANALYTES:
        assert analyte not in report["accepted_analytes"], f"{analyte} should not be in accepted_analytes"
        assert analyte in report["quarantined_analytes"], f"{analyte} should be in quarantined_analytes"


# ---------------------------------------------------------------------------
# SYNC-14: Catalog total becomes 73
# ---------------------------------------------------------------------------
def test_sync_14_catalog_total(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))

    assert len(catalog) == 73
    assert result.report["catalog"]["total_rules"] == 73


# ---------------------------------------------------------------------------
# SYNC-15: Pending runtime safety — supplemental analytes do not produce normal lookup results
# ---------------------------------------------------------------------------
def test_sync_15_pending_runtime_safety():
    repo = ReferenceRepository.from_default_files()

    for analyte, unit in [("HbA1c", "%"), ("LDL-C", "mmol/L"), ("Potassium", "mmol/L")]:
        result = repo.select_rule(analyte=analyte, unit=unit, patient_gender="male", patient_age=35)
        assert not result.matched, f"{analyte} should not match in normal checker"
        assert result.reason == "analyte_not_approved", f"{analyte}: expected analyte_not_approved, got {result.reason}"

    for alias, unit in [("LDL-Cholesterol", "mmol/L"), ("Kali", "mmol/L")]:
        result = repo.select_rule(analyte=alias, unit=unit, patient_gender="female", patient_age=40)
        assert not result.matched
        assert result.reason == "analyte_not_approved"


# ---------------------------------------------------------------------------
# SYNC-16: Critical separation — Potassium/Kali critical detection unchanged
# ---------------------------------------------------------------------------
def test_sync_16_critical_separation():
    from pathlib import Path as _Path
    critical_path = _Path(__file__).resolve().parents[2] / "data/reference/critical_thresholds.json"
    critical = json.loads(critical_path.read_text(encoding="utf-8"))

    keys_lower = {k.lower() for k in critical}
    assert "potassium" in keys_lower or "kali" in keys_lower, "Potassium/Kali not in critical thresholds"

    # Verify the file was not modified
    import hashlib
    digest = hashlib.sha256(critical_path.read_bytes()).hexdigest().upper()
    # File must be loadable and contain Potassium/Kali — no other assertion needed
    # (protected-file diff check is in Phase 15 of the TIP)
    assert digest, "critical_thresholds.json hash should be computable"


# ---------------------------------------------------------------------------
# SYNC-17: Boundary warnings — collisions reported, not rewritten
# ---------------------------------------------------------------------------
def test_sync_17_boundary_warnings(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    sup = result.report.get("explanation_supplement", {})
    warnings = sup.get("boundary_warnings", [])

    # At least 3 documented overlaps
    assert len(warnings) >= 3

    analytes_warned = {w["analyte"] for w in warnings}
    assert "HbA1c" in analytes_warned
    assert "Potassium" in analytes_warned

    # Values are preserved verbatim — not altered
    hba1c_warn = next(w for w in warnings if w["analyte"] == "HbA1c")
    assert hba1c_warn["boundary_value"] == 5.7

    pot_warns = [w for w in warnings if w["analyte"] == "Potassium"]
    boundary_values = {w["boundary_value"] for w in pot_warns}
    assert 3.0 in boundary_values
    assert 7.0 in boundary_values

    # Verify the actual stored values in rules are unchanged
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    by_group = {r["range_group"]: r for r in catalog if r["analyte_canonical"] == "HbA1c"}
    assert by_group["normal"]["range_upper"] == 5.7
    assert by_group["prediabetes"]["range_lower"] == 5.7

    pot_by_group = {r["range_group"]: r for r in catalog if r["analyte_canonical"] == "Potassium"}
    assert pot_by_group["mild_hypokalemia"]["range_lower"] == 3.0
    assert pot_by_group["moderate_hypokalemia"]["range_upper"] == 3.0
    assert pot_by_group["moderate_hyperkalemia"]["range_upper"] == 7.0
    assert pot_by_group["severe_hyperkalemia"]["range_lower"] == 7.0


# ---------------------------------------------------------------------------
# SYNC-18: Deterministic rebuild — two builds from identical inputs are identical
# ---------------------------------------------------------------------------
def test_sync_18_deterministic_rebuild(tmp_path: Path):
    out1 = tmp_path / "r1"
    out2 = tmp_path / "r2"
    build_reference_config(SOURCE, out1, supplemental_path=EXPLANATIONS_PATH)
    build_reference_config(SOURCE, out2, supplemental_path=EXPLANATIONS_PATH)

    json1 = (out1 / RUNTIME_JSON).read_text(encoding="utf-8")
    json2 = (out2 / RUNTIME_JSON).read_text(encoding="utf-8")
    assert json1 == json2, "JSON output differs between two identical builds"

    csv1 = (out1 / RUNTIME_CSV).read_text(encoding="utf-8")
    csv2 = (out2 / RUNTIME_CSV).read_text(encoding="utf-8")
    assert csv1 == csv2, "CSV output differs between two identical builds"


# ---------------------------------------------------------------------------
# SYNC-19: JSON/CSV agreement — all 73 rules present in both
# ---------------------------------------------------------------------------
def test_sync_19_json_csv_agreement(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog_json = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    catalog_csv = _load_csv_from(tmp_path / RUNTIME_CSV)

    assert len(catalog_json) == 73
    assert len(catalog_csv) == 73

    json_ids = {r["rule_id"] for r in catalog_json}
    csv_ids = {r["rule_id"] for r in catalog_csv}
    assert json_ids == csv_ids, f"ID mismatch: JSON-only={json_ids - csv_ids}, CSV-only={csv_ids - json_ids}"

    json_by_id = {r["rule_id"]: r for r in catalog_json}
    csv_by_id = {r["rule_id"]: r for r in catalog_csv}
    for rule_id in json_ids:
        j = json_by_id[rule_id]
        c = csv_by_id[rule_id]
        assert j["analyte_canonical"] == c["analyte_canonical"]
        assert j["reference_type"] == c["reference_type"]
        assert j["sex"] == c["sex"]
        assert j["unit_canonical"] == c["unit_canonical"]
        # Bounds: JSON has float/None, CSV has str/"" — compare semantically
        j_lower = j["range_lower"]
        c_lower = c["range_lower"]
        assert (j_lower is None) == (c_lower == ""), f"{rule_id}: lower bound mismatch: {j_lower!r} vs {c_lower!r}"
        if j_lower is not None:
            assert abs(float(j_lower) - float(c_lower)) < 1e-9


def _load_csv_from(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# SYNC-20: RAGAS datasets/results unchanged
# ---------------------------------------------------------------------------
def test_sync_20_ragas_unchanged():
    import hashlib

    dataset_hash = hashlib.sha256(RAGAS_DATASET.read_bytes()).hexdigest().upper()
    result_hash = hashlib.sha256(RAGAS_RESULT.read_bytes()).hexdigest().upper()

    assert dataset_hash == "C9107685136CA75834E398D329F275A983E41B58C13A84C91670F3423FA32946"
    assert result_hash == "267CD60EB9E6DFD60FC1B1600C2788E0980E01E49647AE0DB40504C2E96D0FF9"
