from __future__ import annotations

import csv
import json
from pathlib import Path

from src.scripts.build_reference_config import (
    BUILD_REPORT_JSON,
    QUARANTINE_CSV,
    RUNTIME_CSV,
    RUNTIME_JSON,
    build_reference_config,
    normalize_null,
    normalize_unit,
    rule_id_for,
    sha256_file,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE = REPO_ROOT / "data/reference/source/adult_outpatient_laboratory_reference_map.csv"
PROTECTED_REFERENCE_FILES = [
    REPO_ROOT / "data/reference/reference_ranges.csv",
    REPO_ROOT / "data/reference/reference_ranges.json",
    REPO_ROOT / "data/reference/explanations.json",
    REPO_ROOT / "data/reference/critical_thresholds.json",
    REPO_ROOT / "data/reference/units_metric.csv",
]

HEADER = [
    "section",
    "analyte_canonical",
    "specimen",
    "fasting_required",
    "sex",
    "age_scope",
    "pregnancy_scope",
    "method_or_formula",
    "unit_machine",
    "unit_display_vn",
    "unit_alt_ifcc",
    "value_type",
    "range_lower",
    "range_upper",
    "reference_type",
    "source_priority_tier",
    "source_type",
    "source_url",
    "evidence_location",
    "population_note",
    "instrument_note",
    "conversion_formula",
    "conversion_formula_source",
    "biological_variation_note",
    "cv_or_uncertainty",
    "comorbidity_caveat",
    "normalization_note",
    "vn_unit_verified",
    "confidence",
    "range_notes",
]


def make_row(**overrides: str) -> dict[str, str]:
    row = {field: "" for field in HEADER}
    row.update(
        {
            "section": "fixture",
            "analyte_canonical": "WBC",
            "specimen": "Whole blood",
            "fasting_required": "NO",
            "sex": "A",
            "age_scope": "Adult",
            "unit_machine": "10^9/L",
            "unit_display_vn": "G/L",
            "value_type": "absolute",
            "range_lower": "4.0",
            "range_upper": "10.0",
            "reference_type": "RI",
            "source_priority_tier": "T1",
            "source_type": "fixture",
            "source_url": "https://example.test/reference",
            "evidence_location": "fixture table",
            "confidence": "HIGH",
        }
    )
    row.update(overrides)
    return row


def write_source(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=HEADER, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def test_actual_source_dry_run(tmp_path: Path) -> None:
    before = sha256_file(SOURCE)

    result = build_reference_config(SOURCE, tmp_path)
    report = result.report

    assert report["input_rows"] == 80
    assert report["structurally_eligible_rows"] == 80
    assert report["structurally_rejected_rows"] == 0

    accepted_analytes = set(report["accepted_analytes"])
    for analyte in {"HbA1c", "LDL-C", "Potassium"}:
        assert analyte in accepted_analytes

    assert sha256_file(SOURCE) == before


def test_metadata_does_not_reject_canonical_record(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            make_row(
                analyte_canonical="CanonicalRecord",
                confidence="LOW",
                source_priority_tier="T3",
            )
        ],
    )

    build_reference_config(source, tmp_path / "out")
    runtime = read_csv(tmp_path / "out" / RUNTIME_CSV)
    quarantine = read_csv(tmp_path / "out" / QUARANTINE_CSV)

    assert [row["analyte_canonical"] for row in runtime] == ["CanonicalRecord"]
    assert quarantine == []


def test_structural_rejection(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            make_row(analyte_canonical=""),
            make_row(analyte_canonical="BadSex", sex="unknown"),
            make_row(analyte_canonical="MissingBounds", range_lower="", range_upper="NA"),
            make_row(analyte_canonical="InvalidLower", range_lower="abc"),
            make_row(analyte_canonical="InvalidUpper", range_upper="abc"),
            make_row(analyte_canonical="BadOrder", range_lower="10", range_upper="4"),
        ],
    )

    build_reference_config(source, tmp_path / "out")
    quarantine = read_csv(tmp_path / "out" / QUARANTINE_CSV)
    reasons_by_analyte = {row["analyte_canonical"]: row["rejection_reasons"] for row in quarantine}

    assert "missing_analyte" in quarantine[0]["rejection_reasons"]
    assert reasons_by_analyte["BadSex"] == "invalid_sex"
    assert reasons_by_analyte["MissingBounds"] == "missing_range_bounds"
    assert reasons_by_analyte["InvalidLower"] == "invalid_lower_bound"
    assert reasons_by_analyte["InvalidUpper"] == "invalid_upper_bound"
    assert reasons_by_analyte["BadOrder"] == "lower_greater_than_upper"


def test_null_handling(tmp_path: Path) -> None:
    assert normalize_null("") is None
    assert normalize_null("NA") is None
    assert normalize_null("N/A") is None
    assert normalize_null("NULL") is None
    assert normalize_null("NONE") is None
    assert normalize_null("0") == "0"

    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            make_row(
                analyte_canonical="ZeroLower",
                specimen="NA",
                fasting_required="N/A",
                range_lower="0",
                range_upper="5.0",
            )
        ],
    )

    build_reference_config(source, tmp_path / "out")
    data = json.loads((tmp_path / "out" / RUNTIME_JSON).read_text(encoding="utf-8"))

    assert data[0]["specimen"] is None
    assert data[0]["fasting_required"] is None
    assert data[0]["range_lower"] == 0


def test_unit_aliases() -> None:
    assert normalize_unit("×10^9/L") == "10^9/L"
    assert normalize_unit("×10^12/L") == "10^12/L"
    assert normalize_unit("µmol/L") == "umol/L"
    assert normalize_unit("μmol/L") == "umol/L"
    assert normalize_unit("G/L") == "10^9/L"
    assert normalize_unit("T/L") == "10^12/L"
    assert normalize_unit("mg/dL") == "mg/dL"
    assert normalize_unit("mmol/L") == "mmol/L"
    assert normalize_unit("mg/dL") != normalize_unit("mmol/L")


def test_unit_g_l_case_sensitive() -> None:
    # lowercase g/L must never map to the count unit 10^9/L
    assert normalize_unit("g/L") == "g/L"
    assert normalize_unit("g/L") != "10^9/L"
    # uppercase G/L retains its intended alias to count unit
    assert normalize_unit("G/L") == "10^9/L"


def test_unit_t_l_case_sensitive() -> None:
    assert normalize_unit("T/L") == "10^12/L"


def test_unit_source_analytes_regenerate_with_g_l_canonical(tmp_path: Path) -> None:
    # After the fix, affected RI rules must store unit_canonical=g/L not 10^9/L
    result = build_reference_config(SOURCE, tmp_path)
    accepted = result.accepted
    affected_ids = {"RRV2-0005", "RRV2-0006", "RRV2-0013", "RRV2-0014", "RRV2-0052", "RRV2-0053"}
    found = {r["rule_id"]: r["unit_canonical"] for r in accepted if r.get("rule_id") in affected_ids}
    assert set(found.keys()) == affected_ids, f"Missing rule IDs: {affected_ids - set(found.keys())}"
    for rule_id, canon in found.items():
        assert canon == "g/L", f"{rule_id}: expected unit_canonical=g/L, got {repr(canon)}"


def test_unit_wbc_rbc_canonical_unaffected_by_fix(tmp_path: Path) -> None:
    result = build_reference_config(SOURCE, tmp_path)
    accepted = result.accepted
    wbc = [r for r in accepted if r.get("analyte_canonical") == "WBC"]
    rbc = [r for r in accepted if r.get("analyte_canonical") == "RBC"]
    assert wbc, "WBC records missing"
    assert rbc, "RBC records missing"
    assert all(r["unit_canonical"] == "10^9/L" for r in wbc), "WBC canonical changed"
    assert all(r["unit_canonical"] == "10^12/L" for r in rbc), "RBC canonical changed"


def test_deterministic_output(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            make_row(analyte_canonical="B", sex="F", range_lower="1.0", range_upper="2.0"),
            make_row(analyte_canonical="A", sex="M", range_lower="3.0", range_upper="4.0"),
            make_row(analyte_canonical="Q"),
        ],
    )
    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    build_reference_config(source, out1)
    build_reference_config(source, out2)

    assert (out1 / RUNTIME_CSV).read_bytes() == (out2 / RUNTIME_CSV).read_bytes()
    assert (out1 / RUNTIME_JSON).read_bytes() == (out2 / RUNTIME_JSON).read_bytes()
    assert (out1 / QUARANTINE_CSV).read_bytes() == (out2 / QUARANTINE_CSV).read_bytes()

    report1 = json.loads((out1 / BUILD_REPORT_JSON).read_text(encoding="utf-8"))
    report2 = json.loads((out2 / BUILD_REPORT_JSON).read_text(encoding="utf-8"))
    report1.pop("generated_at")
    report2.pop("generated_at")
    assert report1 != {}
    assert report1["input_sha256"] == report2["input_sha256"]


def test_source_integrity(tmp_path: Path) -> None:
    before = sha256_file(SOURCE)
    build_reference_config(SOURCE, tmp_path)
    assert sha256_file(SOURCE) == before


def test_count_invariants(tmp_path: Path) -> None:
    result = build_reference_config(SOURCE, tmp_path)
    report = result.report

    assert report["input_rows"] == report["runtime_accepted_rows"] + report["quarantined_rows"]
    assert report["runtime_accepted_rows"] == report["structurally_eligible_rows"]


def test_stable_traceability(tmp_path: Path) -> None:
    source = tmp_path / "source.csv"
    write_source(
        source,
        [
            make_row(analyte_canonical="Zed"),
            make_row(analyte_canonical="Alpha"),
        ],
    )

    build_reference_config(source, tmp_path / "out")
    runtime = read_csv(tmp_path / "out" / RUNTIME_CSV)

    assert rule_id_for(2) == "RRV2-0002"
    by_source_row = {row["source_row_number"]: row for row in runtime}
    assert by_source_row["2"]["rule_id"] == "RRV2-0002"
    assert by_source_row["3"]["rule_id"] == "RRV2-0003"
    assert runtime[0]["analyte_canonical"] == "Alpha"
    assert runtime[1]["analyte_canonical"] == "Zed"


def test_protected_existing_outputs_unchanged(tmp_path: Path) -> None:
    before = {path: sha256_file(path) for path in PROTECTED_REFERENCE_FILES}

    build_reference_config(SOURCE, tmp_path)

    after = {path: sha256_file(path) for path in PROTECTED_REFERENCE_FILES}
    assert after == before
