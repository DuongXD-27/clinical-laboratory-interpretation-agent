"""Contract tests for the unified indicator configuration facade."""

import json
from pathlib import Path

from src.services.indicator_catalog_service import get_indicator_configuration_service
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_approved_analyte_has_complete_configured_metadata():
    service = get_indicator_configuration_service()
    repository = ReferenceRepository.from_default_files()

    for analyte in repository.approved_analytes:
        entry = service.get(analyte)
        assert entry is not None
        assert entry.canonical_unit
        assert entry.section
        assert entry.max_gap_days is None or entry.max_gap_days > 0
        assert analyte in entry.aliases


def test_alias_resolution_uses_the_same_catalog_entry_as_the_canonical_name():
    service = get_indicator_configuration_service()

    assert service.resolve("Kali") == service.get("Potassium")
    assert service.resolve("Creatinin") == service.get("Creatinine")


def test_all_approved_analytes_have_an_adult_rule_for_both_recorded_sexes():
    """Close the previous coverage-audit gap for the current adult-only scope."""
    repository = ReferenceRepository.from_default_files()
    for analyte in repository.approved_analytes:
        entry = get_indicator_configuration_service().get(analyte)
        assert entry is not None
        for sex in ("male", "female"):
            result = repository.select_rule(
                analyte=analyte,
                unit=entry.canonical_unit,
                patient_gender=sex,
                patient_age=35,
            )
            assert result.matched, f"{analyte} lacks adult {sex} coverage: {result.reason}"


def test_gap_policy_declares_exactly_the_approved_catalog():
    config = json.loads(
        (REPO_ROOT / "data/reference/reference_checker_config.json").read_text(encoding="utf-8")
    )
    assert set(config["trend_max_gap_days"]) == set(config["approved_analytes"])
