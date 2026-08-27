from __future__ import annotations

import csv
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

from src.scripts.build_reference_config import RUNTIME_JSON, build_reference_config
from src.services.analyte_resolver import LOCKED_35_ANALYTES, canonical_analyte_id
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_RANGES = REPO_ROOT / "data/reference/reference_ranges.json"
EXPLANATIONS = REPO_ROOT / "data/reference/explanations.json"
CRITICAL_THRESHOLDS = REPO_ROOT / "data/reference/critical_thresholds.json"
REFERENCE_CONFIG = REPO_ROOT / "data/reference/reference_checker_config.json"
QUESTION_TEMPLATES = REPO_ROOT / "data/reference/question_templates.json"
UNITS_CSV = REPO_ROOT / "data/reference/units_metric.csv"
SOURCE_CSV = REPO_ROOT / "data/reference/source/adult_outpatient_laboratory_reference_map.csv"
MOCK_DIRS = (
    REPO_ROOT / "data/mock/templates",
    REPO_ROOT / "data/mock/generated",
)
MANUAL_ENTRY = REPO_ROOT / "frontend/src/generated/analyteCatalog.mjs"


# Known current mock spellings that do not resolve through the runtime reference
# alias contract. This is an audit guardrail only; it must not be treated as
# runtime support or medical approval.
ACKNOWLEDGED_MOCK_NAME_DRIFT = {
    "ALT (GPT)",
    "AST (GOT)",
    "BASO (absolute)",
    "BASO (percentage)",
    "Chloride (Cl-)",
    "EOS (absolute)",
    "EOS (percentage)",
    "eGFR",
    "LYM (absolute)",
    "LYM (percentage)",
    "MONO (absolute)",
    "MONO (percentage)",
    "MPV",
    "NEU/NEUT (absolute)",
    "NEU/NEUT (percentage)",
    "RDW",
    "Sodium (Na)",
    "Triglycerides",
}


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _lookup_key(value: Any) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    without_accents = without_accents.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _canonical_names_by_source() -> dict[str, set[str]]:
    ranges = _json(REFERENCE_RANGES)
    explanations = _json(EXPLANATIONS)
    critical = _json(CRITICAL_THRESHOLDS)
    config = _json(REFERENCE_CONFIG)

    return {
        "locked": set(LOCKED_35_ANALYTES),
        "reference_ranges": {row["analyte_canonical"] for row in ranges},
        "explanations": {row["canonical_name"] for row in explanations},
        "critical_thresholds": set(critical),
        "runtime_approved": set(config["approved_analytes"]),
    }


def _question_ids() -> set[str]:
    return set(_json(QUESTION_TEMPLATES)["analytes"])


def _units() -> dict[str, str]:
    with UNITS_CSV.open("r", encoding="utf-8-sig", newline="") as file:
        return {
            row["test_name"]: row["standardized_unit"]
            for row in csv.DictReader(file)
        }


def _manual_entries() -> list[dict[str, str]]:
    text = MANUAL_ENTRY.read_text(encoding="utf-8")
    pattern = re.compile(r'\{\s*name:\s*"(?P<name>[^"]+)"[^}]*\}')
    return [match.groupdict() for match in pattern.finditer(text)]


def _mock_names() -> set[str]:
    names: set[str] = set()
    for directory in MOCK_DIRS:
        for path in directory.glob("*.json"):
            payload = _json(path)
            reports = payload if isinstance(payload, list) else [payload]
            for report in reports:
                for indicator in report.get("indicators", []):
                    names.add(str(indicator.get("name") or "").strip())
    names.discard("")
    return names


def _runtime_alias_lookup() -> dict[str, str]:
    config = _json(REFERENCE_CONFIG)
    lookup = {
        _lookup_key(alias): canonical
        for alias, canonical in config["analyte_aliases"].items()
    }
    for canonical in LOCKED_35_ANALYTES:
        lookup.setdefault(_lookup_key(canonical), canonical)
    return lookup


def test_inv_001_canonical_names_are_unique_after_normalization() -> None:
    for source_name, names in _canonical_names_by_source().items():
        by_key: dict[str, set[str]] = {}
        for name in names:
            by_key.setdefault(_lookup_key(name), set()).add(name)

        duplicates = {
            key: sorted(values)
            for key, values in by_key.items()
            if len(values) > 1
        }
        assert duplicates == {}, f"{source_name} has normalized duplicates: {duplicates}"


def test_inv_002_runtime_approved_analytes_have_required_artifacts() -> None:
    sources = _canonical_names_by_source()
    config = _json(REFERENCE_CONFIG)
    repo = ReferenceRepository.from_default_files()
    question_ids = _question_ids()
    unit_names = set(_units())

    missing: dict[str, list[str]] = {}
    for analyte in config["approved_analytes"]:
        problems: list[str] = []
        if analyte not in sources["reference_ranges"]:
            problems.append("reference_range")
        if analyte not in sources["explanations"]:
            problems.append("explanation")
        if analyte not in sources["critical_thresholds"]:
            problems.append("critical_record")
        if canonical_analyte_id(analyte) not in question_ids:
            problems.append("question_template")
        if analyte not in unit_names:
            problems.append("unit_registry")
        if analyte not in repo.approved_analytes:
            problems.append("runtime_repository")
        if repo.canonical_unit_for(analyte) is None:
            problems.append("runtime_unit")
        if problems:
            missing[analyte] = problems

    assert missing == {}


def test_inv_003_alias_keys_are_unambiguous_and_target_runtime_approved_catalog() -> None:
    config = _json(REFERENCE_CONFIG)
    approved = set(config["approved_analytes"])
    by_key: dict[str, set[str]] = {}
    for alias, canonical in config["analyte_aliases"].items():
        by_key.setdefault(_lookup_key(alias), set()).add(canonical)

    ambiguous = {
        key: sorted(values)
        for key, values in by_key.items()
        if len(values) > 1
    }
    unknown_targets = {
        alias: canonical
        for alias, canonical in config["analyte_aliases"].items()
        if canonical not in approved
    }

    assert ambiguous == {}
    assert unknown_targets == {}


def test_inv_004_question_template_ids_match_locked_catalog() -> None:
    locked_ids = {canonical_analyte_id(analyte) for analyte in LOCKED_35_ANALYTES}
    assert _question_ids() == locked_ids


def test_inv_005_supported_units_are_runtime_known_or_explicitly_convertible() -> None:
    repo = ReferenceRepository.from_default_files()
    critical = _json(CRITICAL_THRESHOLDS)
    assert repo.unit_conflict_analytes == frozenset()

    for analyte in repo.approved_analytes:
        assert repo.canonical_unit_for(analyte) is not None

    fpg = critical["Fasting plasma glucose"]
    assert fpg["unit"] == "mg/dL"
    assert fpg["vmec_canonical_unit"] == "mmol/L"
    assert fpg["vmec_comparison_strategy"] == "CONVERT_INPUT_TO_SOURCE_UNIT"
    assert fpg["vmec_conversion_function"] == "glucose_mmol_l_to_mg_dl"
    assert fpg["vmec_conversion_scope"] == "CRITICAL_LAYER_ONLY"


def test_inv_006_mock_names_are_supported_or_explicitly_acknowledged_drift() -> None:
    lookup = _runtime_alias_lookup()
    mock_names = _mock_names()

    unclassified = sorted(
        name
        for name in mock_names
        if _lookup_key(name) not in lookup and name not in ACKNOWLEDGED_MOCK_NAME_DRIFT
    )
    assert unclassified == []


def test_inv_007_reference_build_outputs_current_catalog(tmp_path: Path) -> None:
    build_reference_config(SOURCE_CSV, tmp_path, supplemental_path=EXPLANATIONS)

    generated = _json(tmp_path / RUNTIME_JSON)
    committed = _json(REFERENCE_RANGES)
    assert generated == committed


def test_rag_sources_have_minimum_trace_metadata() -> None:
    missing: list[str] = []
    for entry in _json(EXPLANATIONS):
        analyte = entry["canonical_name"]
        for source in entry.get("sources", []):
            source_id = source.get("source_id", "<missing-source-id>")
            for key in ("source_title", "organization", "source_tier", "url"):
                if not source.get(key):
                    missing.append(f"{analyte}:{source_id}:{key}")

    assert missing == []


def test_current_inventory_counts_are_explicit() -> None:
    counts = {
        "reference_ranges_count": len(_canonical_names_by_source()["reference_ranges"]),
        "explanations_count": len(_canonical_names_by_source()["explanations"]),
        "critical_records_count": len(_canonical_names_by_source()["critical_thresholds"]),
        "question_template_count": len(_question_ids()),
        "runtime_approved_count": len(_canonical_names_by_source()["runtime_approved"]),
        "unit_registry_count": len(_units()),
        "manual_entry_count": len(_manual_entries()),
        "mock_unique_names_count": len(_mock_names()),
    }
    assert counts == {
        "reference_ranges_count": 35,
        "explanations_count": 35,
        "critical_records_count": 35,
        "question_template_count": 35,
        "runtime_approved_count": 35,
        "unit_registry_count": 56,
        "manual_entry_count": 35,
        "mock_unique_names_count": 38,
    }
