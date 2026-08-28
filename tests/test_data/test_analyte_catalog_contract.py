from __future__ import annotations

import csv
import json
import unicodedata
from pathlib import Path

from src.services.analyte_catalog import (
    VALID_RUNTIME_STATUSES,
    get_analyte_catalog_contract,
)
from src.services.analyte_resolver import LOCKED_35_ANALYTES, canonical_analyte_id
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_CONFIG = REPO_ROOT / "data/reference/reference_checker_config.json"
REFERENCE_RANGES = REPO_ROOT / "data/reference/reference_ranges.json"
EXPLANATIONS = REPO_ROOT / "data/reference/explanations.json"
CRITICAL_THRESHOLDS = REPO_ROOT / "data/reference/critical_thresholds.json"
QUESTION_TEMPLATES = REPO_ROOT / "data/reference/question_templates.json"
UNITS_CSV = REPO_ROOT / "data/reference/units_metric.csv"

APPROVED_EXACT_SET = {
    "WBC",
    "RBC",
    "HGB",
    "HCT",
    "MCV",
    "MCH",
    "MCHC",
    "RDW-CV",
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
    "Fasting plasma glucose",
    "HbA1c",
    "Creatinine",
    "Urea",
    "Uric acid",
    "AST",
    "ALT",
    "GGT",
    "Total bilirubin",
    "Total protein",
    "Albumin",
    "Total cholesterol",
    "Triglyceride",
    "LDL-C",
    "HDL-C",
    "Potassium",
}


def _json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _lookup_key(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(
        part for part in "".join(character if character.isalnum() else " " for character in without_accents).split()
    )


def _units_by_name() -> dict[str, str]:
    with UNITS_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            row["test_name"]: ReferenceRepository.normalize_unit(row["standardized_unit"])
            for row in csv.DictReader(file)
        }


def test_cat_001_analyte_ids_are_unique_and_stable() -> None:
    entries = get_analyte_catalog_contract().entries
    ids = [entry.analyte_id for entry in entries]

    assert len(ids) == len(set(ids))
    for entry in entries:
        assert entry.analyte_id == canonical_analyte_id(entry.canonical_name)


def test_cat_002_canonical_names_are_unique_and_cover_locked_catalog() -> None:
    entries = get_analyte_catalog_contract().entries
    names = [entry.canonical_name for entry in entries]

    assert len(names) == len(set(names))
    assert set(LOCKED_35_ANALYTES) <= set(names)
    assert get_analyte_catalog_contract().resolve("eGFR") is not None


def test_cat_003_aliases_are_unambiguous_under_current_normalization() -> None:
    by_key: dict[str, set[str]] = {}
    for entry in get_analyte_catalog_contract().entries:
        for value in (entry.analyte_id, entry.canonical_name, *entry.aliases):
            by_key.setdefault(_lookup_key(value), set()).add(entry.canonical_name)

    ambiguous = {key: sorted(values) for key, values in by_key.items() if len(values) > 1}
    assert ambiguous == {}


def test_cat_004_approved_set_matches_reference_checker_config_exactly() -> None:
    catalog_approved = {
        entry.canonical_name for entry in get_analyte_catalog_contract().entries if entry.runtime_status == "APPROVED"
    }
    config_approved = set(_json(REFERENCE_CONFIG)["approved_analytes"])

    assert catalog_approved == APPROVED_EXACT_SET
    assert config_approved == APPROVED_EXACT_SET


def test_cat_005_approved_entries_have_runtime_required_artifacts() -> None:
    repository = ReferenceRepository.from_default_files()
    reference_names = {row["analyte_canonical"] for row in _json(REFERENCE_RANGES)}
    explanation_names = {row["canonical_name"] for row in _json(EXPLANATIONS)}
    critical_names = set(_json(CRITICAL_THRESHOLDS))
    question_ids = set(_json(QUESTION_TEMPLATES)["analytes"])

    missing: dict[str, list[str]] = {}
    for entry in get_analyte_catalog_contract().approved_entries:
        problems: list[str] = []
        if entry.canonical_name not in reference_names:
            problems.append("reference_range")
        if entry.canonical_name not in explanation_names:
            problems.append("explanation")
        if entry.canonical_name not in critical_names:
            problems.append("critical_record")
        if entry.analyte_id not in question_ids:
            problems.append("question_template")
        if entry.canonical_name not in repository.approved_analytes:
            problems.append("runtime_repository")
        if repository.canonical_unit_for(entry.canonical_name) != entry.canonical_unit:
            problems.append("runtime_unit")
        if problems:
            missing[entry.canonical_name] = problems

    assert missing == {}


def test_cat_006_canonical_units_are_declared_in_unit_registry() -> None:
    units = _units_by_name()
    missing_or_mismatch: dict[str, str] = {}
    for entry in get_analyte_catalog_contract().entries:
        expected = ReferenceRepository.normalize_unit(entry.canonical_unit)
        actual = units.get(entry.canonical_name)
        if actual != expected:
            missing_or_mismatch[entry.canonical_name] = f"expected {expected}, got {actual}"

    assert missing_or_mismatch == {}


def test_cat_007_uric_acid_policy_is_approved_by_tip_data_008() -> None:
    entry = get_analyte_catalog_contract().resolve("Uric acid")

    assert entry is not None
    assert entry.runtime_status == "APPROVED"


def test_cat_008_egfr_policy_is_unsupported_not_approved() -> None:
    entry = get_analyte_catalog_contract().resolve("eGFR")

    assert entry is not None
    assert entry.runtime_status == "UNSUPPORTED"
    assert entry.runtime_status != "APPROVED"


def test_catalog_uses_only_declared_runtime_statuses() -> None:
    statuses = {entry.runtime_status for entry in get_analyte_catalog_contract().entries}

    assert statuses <= VALID_RUNTIME_STATUSES
