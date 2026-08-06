from __future__ import annotations

import csv
import json
from pathlib import Path

from src.services.reference_repository import ReferenceRepository


MANIFEST_PATH = Path("docs/version-handoff/v2_analyte_manifest.json")
CONFIG_PATH = Path("data/reference/reference_checker_v2_config.json")
RUNTIME_PATH = Path("data/reference/reference_ranges_v2.json")
QUARANTINE_PATH = Path("data/reference/quarantine_v2.csv")
EXPLANATIONS_PATH = Path("data/reference/explanations.json")
CRITICAL_PATH = Path("data/reference/critical_thresholds.json")
RAGAS_DATASET_PATH = Path("eval/datasets/ragas_v2_baseline.jsonl")

INTENDED_ORDER = [
    "WBC",
    "RBC",
    "HGB",
    "Fasting plasma glucose",
    "HbA1c",
    "LDL-C",
    "HDL-C",
    "Creatinine",
    "Potassium",
]
APPROVED = {"WBC", "RBC", "Fasting plasma glucose", "Creatinine"}
PENDING = {"HGB", "HDL-C", "HbA1c", "LDL-C", "Potassium"}


def load_manifest() -> list[dict]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def load_ragas_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in RAGAS_DATASET_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def by_analyte() -> dict[str, dict]:
    return {record["analyte"]: record for record in load_manifest()}


def aliases_by_canonical() -> dict[str, set[str]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    aliases = {analyte: {analyte} for analyte in INTENDED_ORDER}
    for alias, canonical in config["analyte_aliases"].items():
        if canonical in aliases:
            aliases[canonical].add(alias)
    return aliases


def explanation_source_flags() -> dict[str, tuple[bool, bool]]:
    aliases = aliases_by_canonical()
    explanations = json.loads(EXPLANATIONS_PATH.read_text(encoding="utf-8"))
    explanation_by_key = {item["indicator"].casefold(): item for item in explanations}
    flags: dict[str, tuple[bool, bool]] = {}
    for analyte, names in aliases.items():
        matched = [explanation_by_key[name.casefold()] for name in names if name.casefold() in explanation_by_key]
        flags[analyte] = (
            bool(matched),
            any(bool(item.get("sources")) for item in matched),
        )
    return flags


def reference_source_flags() -> dict[str, bool]:
    runtime_rows = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    with QUARANTINE_PATH.open(encoding="utf-8-sig", newline="") as file:
        quarantine_rows = list(csv.DictReader(file))
    flags = {analyte: False for analyte in INTENDED_ORDER}
    for row in [*runtime_rows, *quarantine_rows]:
        analyte = row.get("analyte_canonical")
        if analyte in flags and row.get("source_url"):
            flags[analyte] = True
    return flags


def critical_flags() -> dict[str, bool]:
    aliases = aliases_by_canonical()
    critical_keys = {key.casefold() for key in json.loads(CRITICAL_PATH.read_text(encoding="utf-8"))}
    return {
        analyte: any(alias.casefold() in critical_keys for alias in names)
        for analyte, names in aliases.items()
    }


def test_m01_exact_analyte_inventory():
    manifest = load_manifest()
    analytes = [record["analyte"] for record in manifest]

    assert len(manifest) == 9
    assert len(set(analytes)) == 9
    assert set(analytes) == set(INTENDED_ORDER)


def test_m02_approved_normal_list():
    manifest = by_analyte()
    approved = {
        analyte
        for analyte, record in manifest.items()
        if record["normal_reference_supported"] is True and record["approval_status"] == "approved"
    }

    assert approved == APPROVED


def test_m03_pending_list():
    manifest = by_analyte()

    assert {analyte for analyte, record in manifest.items() if record["approval_status"] == "pending"} == PENDING


def test_m04_hgb_blocker():
    # After BONUS-TIP-008: technical unit conflict resolved; HGB pending awaiting medical approval
    assert "awaiting_medical_approval" in by_analyte()["HGB"]["blockers"]
    assert "unit_data_conflict" not in by_analyte()["HGB"]["blockers"]


def test_m05_hdl_c_blockers():
    hdl = by_analyte()["HDL-C"]

    assert hdl["normal_reference_supported"] is False
    assert "cdl_only" in hdl["blockers"]


def test_m06_md_analytes():
    manifest = by_analyte()

    assert "md_not_approved" in manifest["HbA1c"]["blockers"]
    assert "md_not_approved" in manifest["LDL-C"]["blockers"]


def test_m07_potassium_separation():
    potassium = by_analyte()["Potassium"]

    assert potassium["normal_reference_supported"] is False
    assert potassium["critical_rule_available"] == critical_flags()["Potassium"]


def test_m08_ragas_coverage_limited_to_approved_analytes():
    manifest = by_analyte()

    assert {analyte for analyte, record in manifest.items() if record["ragas_case_available"]} == APPROVED
    assert all(manifest[analyte]["ragas_case_available"] is False for analyte in PENDING)


def test_m09_source_and_explanation_evidence():
    manifest = by_analyte()
    explanation_flags = explanation_source_flags()
    reference_flags = reference_source_flags()

    for analyte, record in manifest.items():
        explanation_available, explanation_source_available = explanation_flags[analyte]
        assert record["explanation_available"] is explanation_available
        assert record["source_available"] is (explanation_source_available or reference_flags[analyte])


def test_m10_deterministic_structure():
    assert [record["analyte"] for record in load_manifest()] == INTENDED_ORDER


def test_manifest_matches_effective_repository_policy():
    manifest = by_analyte()
    repository = ReferenceRepository.from_default_files()

    assert repository.approved_analytes == APPROVED
    assert repository.pending_analytes == PENDING
    assert {
        analyte for analyte, record in manifest.items() if record["unit_validated"] and record["approval_status"] == "approved"
    } == repository.approved_analytes


def test_manifest_ragas_flags_agree_with_jsonl_dataset():
    manifest = by_analyte()
    dataset_analytes = {case["analyte"] for case in load_ragas_cases()}

    assert dataset_analytes == APPROVED
    assert {analyte for analyte, record in manifest.items() if record["ragas_case_available"]} == dataset_analytes


def test_every_dataset_analyte_maps_to_approved_manifest_entry():
    manifest = by_analyte()

    for case in load_ragas_cases():
        record = manifest[case["analyte"]]
        assert record["approval_status"] == "approved"
        assert record["normal_reference_supported"] is True
        assert record["ragas_case_available"] is True
