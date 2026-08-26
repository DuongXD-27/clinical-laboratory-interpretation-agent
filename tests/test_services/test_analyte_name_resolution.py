import json
from pathlib import Path

import pytest

from src.services.analyte_name_resolution import (
    AMBIGUOUS_LABELS,
    SAFE_RUNTIME_ALIASES,
    normalize_analyte_lookup_key,
)
from src.services.analyte_resolver import LOCKED_35_ANALYTES
from src.services.reference_repository import ReferenceRepository


@pytest.fixture(scope="module")
def repository():
    return ReferenceRepository.from_default_files()


@pytest.mark.parametrize("canonical", LOCKED_35_ANALYTES)
def test_all_locked_canonical_names_resolve(canonical, repository):
    assert repository.resolve_analyte(canonical) == canonical


@pytest.mark.parametrize("canonical", LOCKED_35_ANALYTES)
def test_all_locked_names_tolerate_safe_hospital_wrappers(canonical, repository):
    wrapped = f"Xét nghiệm {canonical} (máu)"

    resolution = repository.resolve_analyte_result(wrapped)

    assert resolution.status == "RESOLVED"
    assert resolution.canonical_name == canonical
    assert resolution.specimen_annotations == ("mau",)


@pytest.mark.parametrize("canonical", LOCKED_35_ANALYTES)
def test_all_locked_names_tolerate_case_and_spacing(canonical, repository):
    assert repository.resolve_analyte(f"  {canonical.swapcase()}  ") == canonical


@pytest.mark.parametrize("canonical", LOCKED_35_ANALYTES)
def test_all_locked_names_reject_unapproved_suffixes(canonical, repository):
    assert repository.resolve_analyte(f"{canonical} unrelated assay") is None


def test_every_catalog_alias_and_explicit_runtime_alias_resolves(repository):
    payload = json.loads(
        (Path(__file__).parents[2] / "data/reference/analyte_catalog.json").read_text(
            encoding="utf-8"
        )
    )
    aliases = [
        (alias, entry["canonical_name"])
        for entry in payload["entries"]
        if entry["runtime_status"] == "APPROVED"
        for alias in entry["aliases"]
    ]
    aliases.extend(SAFE_RUNTIME_ALIASES.items())

    for alias, canonical in aliases:
        assert repository.resolve_analyte(alias) == canonical


def test_normalized_deterministic_aliases_have_no_collisions(repository):
    seen: dict[str, str] = {}
    collisions: list[tuple[str, str, str]] = []
    for canonical, raw_aliases in repository._aliases_by_canonical.items():
        for raw_alias in raw_aliases:
            key = normalize_analyte_lookup_key(raw_alias)
            previous = seen.setdefault(key, canonical)
            if previous != canonical:
                collisions.append((key, previous, canonical))

    assert collisions == []


@pytest.mark.parametrize("label", AMBIGUOUS_LABELS)
def test_generic_glucose_labels_are_ambiguous_and_never_resolved(label, repository):
    resolution = repository.resolve_analyte_result(label)

    assert resolution.status == "AMBIGUOUS"
    assert resolution.canonical_name is None
    assert repository.resolve_analyte(label) is None


@pytest.mark.parametrize(
    "label",
    [
        "Neutrophils",
        "Lymphocytes",
        "Monocytes",
        "Eosinophils",
        "Bilirubin",
        "Protein",
        "Cholesterol",
        "LDL",
        "HDL",
        "W8C",
    ],
)
def test_semantically_incomplete_or_corrupt_labels_fail_closed(label, repository):
    resolution = repository.resolve_analyte_result(label)

    assert resolution.status == "UNSUPPORTED"
    assert resolution.canonical_name is None


@pytest.mark.parametrize(
    ("raw_name", "expected_status", "expected_canonical"),
    [
        (
            "Định lượng Cholesterol toàn phần (máu)",
            "RESOLVED",
            "Total cholesterol",
        ),
        (
            "Định lượng Triglycerid (máu) [Máu]",
            "RESOLVED",
            "Triglyceride",
        ),
        ("Định lượng Glucose [Máu]", "AMBIGUOUS", None),
    ],
)
def test_observed_hospital_labels(raw_name, expected_status, expected_canonical, repository):
    resolution = repository.resolve_analyte_result(raw_name)

    assert resolution.status == expected_status
    assert resolution.canonical_name == expected_canonical


@pytest.mark.parametrize(
    ("variant", "canonical"),
    [
        ("W.B.C", "WBC"),
        ("LDL C", "LDL-C"),
        ("HDL C", "HDL-C"),
        ("HDL-cho.", "HDL-C"),
        ("Potassium (K+)", "Potassium"),
    ],
)
def test_conventional_abbreviation_punctuation(variant, canonical, repository):
    assert repository.resolve_analyte(variant) == canonical
