import json
from pathlib import Path

import pytest

from src.services.analyte_name_resolution import (
    AMBIGUOUS_LABELS,
    OCR_RUNTIME_ALIAS_GROUPS,
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
        (Path(__file__).parents[2] / "data/reference/analyte_catalog.json").read_text(encoding="utf-8")
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


def test_ocr_runtime_alias_groups_cover_every_locked_approved_analyte(repository):
    assert set(OCR_RUNTIME_ALIAS_GROUPS) == set(repository.approved_analytes)
    assert all(8 <= len(aliases) <= 12 for aliases in OCR_RUNTIME_ALIAS_GROUPS.values())


@pytest.mark.parametrize(
    ("raw_name", "canonical"),
    [
        ("Số lượng bạch cầu (WBC)", "WBC"),
        ("Bạch cầu(WBC)", "WBC"),
        ("Tỷ lệ bạch cầu trung tính (NEUT%)", "Neutrophils %"),
        ("Số lượng bạch cầu trung tính (NEUT#)", "Neutrophils abs"),
        ("Tỷ lệ bạch cầu lympho (LYMPH%)", "Lymphocytes %"),
        ("Số lượng bạch cầu lympho (LYMPH#)", "Lymphocytes abs"),
        ("Tỷ lệ bạch cầu mono (MONO%)", "Monocytes %"),
        ("Số lượng bạch cầu mono (MONO#)", "Monocytes abs"),
        ("Tỷ lệ bạch cầu ái toan (EO%)", "Eosinophils %"),
        ("Số lượng bạch cầu ái toan (EO#)", "Eosinophils abs"),
        ("Số lượng hồng cầu (RBC)", "RBC"),
        ("Nồng độ huyết sắc tố (HGB)", "HGB"),
        ("Thể tích khối hồng cầu trong máu toàn phần (HCT)", "HCT"),
        ("Thể tích trung bình hồng cầu (MCV)", "MCV"),
        ("Lượng huyết sắc tố trung bình hồng cầu (MCH)", "MCH"),
        ("Nồng độ huyết sắc tố trung bình hồng cầu (MCHC)", "MCHC"),
        ("Độ phân bố hồng cầu (RDW-CV)", "RDW-CV"),
        ("Số lượng tiểu cầu (PLT)", "PLT"),
        ("Glucose máu lúc đói", "Fasting plasma glucose"),
        ("Creatinin máu", "Creatinine"),
        ("Cholesterol toàn phần (TC)", "Total cholesterol"),
        ("Kali máu (K+)", "Potassium"),
    ],
)
def test_ocr_observed_labels_resolve_to_canonical_names(raw_name, canonical, repository):
    resolution = repository.resolve_analyte_result(raw_name)

    assert resolution.status == "RESOLVED"
    assert resolution.canonical_name == canonical


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
