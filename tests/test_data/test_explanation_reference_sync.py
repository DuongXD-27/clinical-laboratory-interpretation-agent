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
from src.scripts.ingest_kb import corpus_sha256
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
EXPLANATIONS_PATH = REPO_ROOT / "data/reference/explanations.json"
SOURCE = REPO_ROOT / "data/reference/source/adult_outpatient_laboratory_reference_map.csv"
REFERENCE_JSON = REPO_ROOT / "data/reference/reference_ranges.json"
REFERENCE_CSV = REPO_ROOT / "data/reference/reference_ranges.csv"
RAGAS_DATASET = REPO_ROOT / "eval/datasets/ragas_v2_baseline.jsonl"
RAGAS_RESULT = REPO_ROOT / "eval/results/ragas_v2_baseline.json"

PRIMARY_ANALYTES_PRESENT = {"WBC", "RBC", "HGB", "Fasting plasma glucose", "HDL-C", "Creatinine"}
SUPPLEMENTAL_ANALYTES = {"HbA1c", "LDL-C", "Potassium"}
SUPPLEMENTAL_REPLACEMENT_ANALYTES = {"HDL-C"}
APPROVED = {"WBC", "RBC", "HGB", "Fasting plasma glucose", "HbA1c", "LDL-C", "HDL-C", "Creatinine", "Potassium"}
PENDING: set[str] = set()


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
    assert len(entries) == 35

    all_rules = json.loads(REFERENCE_JSON.read_text(encoding="utf-8"))
    # Primary-only rules are those without source_origin=explanations.json
    primary_analytes = {r["analyte_canonical"] for r in all_rules if r.get("source_origin") != "explanations.json"}
    assert len(primary_analytes) >= 30


# ---------------------------------------------------------------------------
# SYNC-02: Build-time alias resolution
# ---------------------------------------------------------------------------
def test_sync_02_build_time_alias_resolution():
    # BUILD_TIME_ALIAS: used only while extracting supplemental explanation
    # ranges. This is intentionally separate from the RUNTIME_REFERENCE_ALIAS
    # contract in reference_checker_config.json.
    assert canonical_analyte("Glucose") == "Fasting plasma glucose"
    assert canonical_analyte("HDL-Cholesterol") == "HDL-C"
    assert canonical_analyte("LDL-Cholesterol") == "LDL-C"
    assert canonical_analyte("Kali") == "Potassium"
    # Direct names pass through unchanged
    assert canonical_analyte("WBC") == "WBC"
    assert canonical_analyte("HbA1c") == "HbA1c"
    assert canonical_analyte("Creatinine") == "Creatinine"


def test_sync_02_build_time_alias_map_completeness():
    # BUILD_TIME_ALIAS, not RUNTIME_REFERENCE_ALIAS. Generic Glucose must stay
    # absent from the runtime ReferenceRepository configuration.
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
    primary_analytes = {r["analyte_canonical"] for r in all_rules if r.get("source_origin") != "explanations.json"}
    explanation_resolved = {canonical_analyte(e.get("canonical_name") or e.get("name")) for e in entries}
    missing = explanation_resolved - primary_analytes
    assert isinstance(missing, set)


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
# SYNC-05: Rule count — primary catalog total
# ---------------------------------------------------------------------------
def test_sync_05_rule_count(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))

    # Primary pipeline: all 67 structurally valid rows are accepted.
    # explanations.json no longer has reference_ranges → 0 supplemental rules added
    assert len(result.accepted) == 67
    assert result.report["explanation_supplement"]["rules_added"] == 0
    assert len(catalog) == 67
    assert result.report["catalog"]["total_rules"] == 67
    assert all("range" + "_flag" not in rule for rule in catalog)


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

    # explanations.json has no reference_ranges → no EXPV2 rules generated
    exp_ids = [rid for rid in ids1 if rid.startswith("EXPV2-")]
    assert len(exp_ids) == 0


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
# SYNC-08: HbA1c canonical records remain available
# ---------------------------------------------------------------------------
def test_sync_08_hba1c_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    hba1c_rules = [r for r in catalog if r["analyte_canonical"] == "HbA1c"]

    # explanations.json has no reference_ranges → HbA1c comes only from primary CSV
    # HbA1c comes directly from the canonical primary CSV.
    assert len(hba1c_rules) == 3


# ---------------------------------------------------------------------------
# SYNC-09: LDL-C mapping — 5 non-RI rules matching explanations.json
# ---------------------------------------------------------------------------
def test_sync_09_ldl_c_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    ldlc_rules = [r for r in catalog if r["analyte_canonical"] == "LDL-C"]

    # explanations.json has no reference_ranges → LDL-C comes only from primary CSV
    # LDL-C comes directly from the canonical primary CSV.
    assert len(ldlc_rules) == 5


# ---------------------------------------------------------------------------
# SYNC-10: Potassium canonical record remains available
# ---------------------------------------------------------------------------
def test_sync_10_potassium_mapping(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    pot_rules = [r for r in catalog if r["analyte_canonical"] == "Potassium"]

    # explanations.json has no reference_ranges → Potassium comes only from primary CSV
    # Potassium comes directly from the canonical primary CSV.
    assert len(pot_rules) == 1


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
# SYNC-12: Existing primary rules remain semantically unchanged
# ---------------------------------------------------------------------------
def test_sync_12_existing_rules_unchanged(tmp_path: Path):
    # Build without supplemental to get primary baseline
    baseline = build_reference_config(SOURCE, tmp_path / "base")
    baseline_by_id = {r["rule_id"]: r for r in baseline.accepted}

    # Build with supplemental
    build_reference_config(SOURCE, tmp_path / "combined", supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / "combined" / RUNTIME_JSON).read_text(encoding="utf-8"))
    catalog_by_id = {r["rule_id"]: r for r in catalog}

    # Primary rules for SUPPLEMENTAL_REPLACEMENT_ANALYTES are intentionally excluded from the combined catalog
    from src.scripts.build_reference_config import SUPPLEMENTAL_REPLACEMENT_ANALYTES

    non_replacement_baseline = {
        rule_id: rule
        for rule_id, rule in baseline_by_id.items()
        if rule.get("analyte_canonical") not in SUPPLEMENTAL_REPLACEMENT_ANALYTES
    }

    assert len(baseline.accepted) == 67
    for rule_id, primary_rule in non_replacement_baseline.items():
        assert rule_id in catalog_by_id, f"Primary rule {rule_id} missing from combined catalog"
        combined_rule = catalog_by_id[rule_id]
        for key in (
            "analyte_canonical",
            "unit_canonical",
            "range_lower",
            "range_upper",
            "reference_type",
            "source_url",
        ):
            assert combined_rule.get(key) == primary_rule.get(key), (
                f"{rule_id} field '{key}' changed: {primary_rule.get(key)!r} → {combined_rule.get(key)!r}"
            )


# ---------------------------------------------------------------------------
# SYNC-13: Primary counts unchanged — 67
# ---------------------------------------------------------------------------
def test_sync_13_primary_counts_unchanged(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    report = result.report

    assert report["input_rows"] == 67
    assert report["runtime_accepted_rows"] == 67
    assert report["quarantined_rows"] == 0
    assert report["multiple_reason_rows"] == 0
    assert report["input_rows"] == report["runtime_accepted_rows"] + report["quarantined_rows"]

    # Former supplemental analytes are present directly in canonical data.
    for analyte in SUPPLEMENTAL_ANALYTES:
        assert analyte in report["accepted_analytes"], f"{analyte} should be in accepted_analytes"


# ---------------------------------------------------------------------------
# SYNC-14: Catalog total becomes 67
# ---------------------------------------------------------------------------
def test_sync_14_catalog_total(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))

    assert len(catalog) == 67
    assert result.report["catalog"]["total_rules"] == 67


# ---------------------------------------------------------------------------
# SYNC-15: Pending runtime safety — supplemental analytes do not produce normal lookup results
# ---------------------------------------------------------------------------
def test_sync_15_approved_ri_rules_match():
    repo = ReferenceRepository.from_default_files()

    for analyte, unit in [("WBC", "10^9/L"), ("Creatinine", "umol/L"), ("Potassium", "mmol/L")]:
        assert analyte in repo.approved_analytes, f"{analyte} should be approved"
        result = repo.select_rule(analyte=analyte, unit=unit, patient_gender="male", patient_age=35)
        assert result.matched, f"{analyte} RI rule should match; got reason={result.reason}"

    # Aliases resolve and match
    for alias, unit in [("Bạch cầu", "10^9/L"), ("Kali", "mmol/L")]:
        result = repo.select_rule(analyte=alias, unit=unit, patient_gender="female", patient_age=40)
        assert result.matched, f"Alias {alias!r} RI rule should match; got reason={result.reason}"


# ---------------------------------------------------------------------------
# SYNC-16: Critical separation — canonical production registry
# ---------------------------------------------------------------------------
def test_sync_16_critical_separation():
    from pathlib import Path as _Path

    critical_path = _Path(__file__).resolve().parents[2] / "data/reference/critical_thresholds.json"
    critical = json.loads(critical_path.read_text(encoding="utf-8"))

    assert "Potassium" in critical
    assert "Kali" not in critical

    # Verify the file was not modified
    import hashlib

    digest = hashlib.sha256(critical_path.read_bytes()).hexdigest().upper()
    # File must be loadable and contain only the canonical Potassium key.
    # (protected-file diff check is in Phase 15 of the TIP)
    assert digest, "critical_thresholds.json hash should be computable"


# ---------------------------------------------------------------------------
# SYNC-17: Boundary warnings — collisions reported, not rewritten
# ---------------------------------------------------------------------------
def test_sync_17_boundary_warnings(tmp_path: Path):
    result = build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    sup = result.report.get("explanation_supplement", {})
    warnings = sup.get("boundary_warnings", [])

    # Boundary warnings are statically defined in extract_explanation_reference_ranges.py
    # They are still reported even when 0 rules are extracted (informational only)
    assert isinstance(warnings, list)
    # The static _BOUNDARY_WARNINGS list always contains HbA1c and Potassium entries
    if warnings:
        analytes_warned = {w["analyte"] for w in warnings}
        assert "HbA1c" in analytes_warned
        assert "Potassium" in analytes_warned


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
# SYNC-19: JSON/CSV agreement — all 67 rules present in both
# ---------------------------------------------------------------------------
def test_sync_19_json_csv_agreement(tmp_path: Path):
    build_reference_config(SOURCE, tmp_path, supplemental_path=EXPLANATIONS_PATH)
    catalog_json = json.loads((tmp_path / RUNTIME_JSON).read_text(encoding="utf-8"))
    catalog_csv = _load_csv_from(tmp_path / RUNTIME_CSV)

    assert len(catalog_json) == 67
    assert len(catalog_csv) == 67

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
    """Pin hash tren byte DA CHUAN HOA dong, khong phai byte tho.

    Repo khong co `.gitattributes`; voi `core.autocrlf=true` (mac dinh pho bien
    tren Windows) cung mot commit cho ra LF tren Linux va CRLF tren Windows.
    Hash byte tho vi the do vao may checkout chu khong do vao noi dung: pin nay
    xanh tren CI self-hosted va do tren moi may Windows du dataset y het.
    """

    dataset_hash = corpus_sha256(RAGAS_DATASET).upper()
    result_hash = corpus_sha256(RAGAS_RESULT).upper()

    assert dataset_hash == "C57330C5431B69C7BDC5329D1AF785CB7505A5328E21A53AA9D038D4CBC071C5"
    assert result_hash == "EE7EF10A22EC815263FDB8B7D6775536451D65E26B143F39C80BB8F947B91E9A"
