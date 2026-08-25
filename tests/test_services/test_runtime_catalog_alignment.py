from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.services.analyte_catalog import get_analyte_catalog_contract
from src.services.analyte_sections import CHEMISTRY, HEMATOLOGY, LIPIDS, analyte_section
from src.services.indicator_catalog_service import get_indicator_configuration_service
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_CONFIG = REPO_ROOT / "data/reference/reference_checker_config.json"

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


def _reference_config() -> dict:
    return json.loads(REFERENCE_CONFIG.read_text(encoding="utf-8"))


def test_rt_cat_001_002_repository_approved_set_is_catalog_authoritative() -> None:
    catalog = get_analyte_catalog_contract()
    repository = ReferenceRepository.from_default_files()

    assert set(catalog.approved_names) == APPROVED_EXACT_SET
    assert repository.approved_analytes == APPROVED_EXACT_SET


def test_rt_cat_003_existing_runtime_alias_snapshot_is_unchanged() -> None:
    config_aliases = _reference_config()["analyte_aliases"]
    catalog_aliases = get_analyte_catalog_contract().runtime_alias_map()
    repository = ReferenceRepository.from_default_files()

    assert catalog_aliases == config_aliases
    for alias, canonical in config_aliases.items():
        assert repository.resolve_analyte(alias) == canonical
        assert repository.resolve_analyte(f"  {alias.lower()}  ") == canonical


@pytest.mark.parametrize(
    ("analyte", "expected_status"),
    [
        ("eGFR", "UNSUPPORTED"),
        ("Not A Real Analyte", None),
    ],
)
def test_rt_cat_004_005_006_non_approved_analytes_fail_closed(
    analyte: str,
    expected_status: str | None,
) -> None:
    repository = ReferenceRepository.from_default_files()

    assert repository.runtime_status_for(analyte) == expected_status
    assert repository.resolve_analyte(analyte) is None
    result = repository.select_rule(
        analyte=analyte,
        unit="mmol/L",
        patient_gender="male",
        patient_age=35,
    )
    assert result.matched is False
    assert result.reason == "analyte_not_supported"


@pytest.mark.parametrize(
    ("analyte", "unit", "canonical"),
    [
        ("Bạch cầu (WBC)", "10^9/L", "WBC"),
        ("Hồng cầu (RBC)", "10^12/L", "RBC"),
        ("Hemoglobin", "g/L", "HGB"),
        ("Hematocrit", "L/L", "HCT"),
        ("MCV", "fL", "MCV"),
        ("MCH", "pg", "MCH"),
        ("MCHC", "g/L", "MCHC"),
        ("RDW", "%CV", "RDW-CV"),
        ("Tiểu cầu", "10^9/L", "PLT"),
        ("NEU/NEUT (percentage)", "%", "Neutrophils %"),
        ("NEU/NEUT (absolute)", "10^9/L", "Neutrophils abs"),
        ("LYM (percentage)", "%", "Lymphocytes %"),
        ("LYM (absolute)", "10^9/L", "Lymphocytes abs"),
        ("MONO (percentage)", "%", "Monocytes %"),
        ("MONO (absolute)", "10^9/L", "Monocytes abs"),
        ("EOS (percentage)", "%", "Eosinophils %"),
        ("EOS (absolute)", "10^9/L", "Eosinophils abs"),
        ("Natri", "mmol/L", "Sodium"),
        ("Clor", "mmol/L", "Chloride"),
        ("Đường huyết lúc đói", "mmol/L", "Fasting plasma glucose"),
        ("HbA1c", "%", "HbA1c"),
        ("Urea", "mmol/L", "Urea"),
        ("AST (GOT)", "U/L", "AST"),
        ("ALT (GPT)", "U/L", "ALT"),
        ("GGT", "U/L", "GGT"),
        ("Bilirubin toàn phần", "umol/L", "Total bilirubin"),
        ("Protein toàn phần", "g/L", "Total protein"),
        ("Albumin", "g/L", "Albumin"),
        ("Total Cholesterol", "mg/dL", "Total cholesterol"),
        ("Triglycerides", "mg/dL", "Triglyceride"),
        ("LDL-Cholesterol", "mmol/L", "LDL-C"),
        ("HDL-cho.", "mmol/L", "HDL-C"),
        ("Creatinin", "umol/L", "Creatinine"),
        ("Uric Acid", "umol/L", "Uric acid"),
        ("K+", "mmol/L", "Potassium"),
    ],
)
def test_rt_cat_007_reference_lookup_for_existing_supported_aliases(
    analyte: str,
    unit: str,
    canonical: str,
) -> None:
    result = ReferenceRepository.from_default_files().select_rule(
        analyte=analyte,
        unit=unit,
        value=100,
        patient_gender="male",
        patient_age=35,
    )

    assert result.matched is True
    assert result.canonical_analyte == canonical


def test_rt_cat_008_indicator_catalog_public_semantics_remain_compatible() -> None:
    service = get_indicator_configuration_service()

    potassium = service.resolve("Kali")
    assert potassium == service.get("Potassium")
    assert potassium is not None
    assert potassium.canonical_unit == "mmol/L"
    assert "Kali" in potassium.aliases


def test_rt_cat_009_legacy_backend_grouping_is_preserved() -> None:
    assert analyte_section("WBC") == HEMATOLOGY
    assert analyte_section("Fasting plasma glucose") == LIPIDS
    assert analyte_section("Creatinine") == CHEMISTRY
    assert analyte_section("Potassium") == CHEMISTRY
    assert analyte_section("Uric acid") == CHEMISTRY
    assert analyte_section("eGFR") is None


def test_rt_cat_012_legacy_config_catalog_owned_fields_are_strictly_synced() -> None:
    config = _reference_config()
    catalog = get_analyte_catalog_contract()

    assert set(config["approved_analytes"]) == set(catalog.approved_names)
    assert config["analyte_aliases"] == catalog.runtime_alias_map()
    assert set(config["hold_analytes"]) == {
        entry.canonical_name
        for entry in catalog.entries
        if entry.runtime_status == "HOLD"
    }
