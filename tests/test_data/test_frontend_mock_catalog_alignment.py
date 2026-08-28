from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

from scripts.generate_frontend_analyte_catalog import is_current, render_catalog
from src.services.analyte_catalog import get_analyte_catalog_contract
from src.services.reference_repository import ReferenceRepository

REPO_ROOT = Path(__file__).resolve().parents[2]
MANUAL_ENTRY = REPO_ROOT / "frontend/src/lib/manualEntry.mjs"
GENERATED_CATALOG = REPO_ROOT / "frontend/src/generated/analyteCatalog.mjs"
MOCK_DIRS = (
    REPO_ROOT / "data/mock/templates",
    REPO_ROOT / "data/mock/generated",
)

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
    "Uric acid",
}

GROUP_LABELS = {
    "hematology": "Huyết học",
    "electrolytes": "Điện giải",
    "glucose": "Đường huyết",
    "renal": "Chức năng thận",
    "liver": "Chức năng gan",
    "lipids": "Mỡ máu",
}

UNRESOLVED_MOCK_ANALYTES = {
    "BASO (absolute)": "DECISION_REQUIRED_BASO_NOT_IN_CANONICAL_CATALOG",
    "BASO (percentage)": "DECISION_REQUIRED_BASO_NOT_IN_CANONICAL_CATALOG",
    "MPV": "DECISION_REQUIRED_MPV_NOT_IN_CANONICAL_CATALOG",
}

APPROVED_MOCK_UNIT_GAPS = {
    ("Total cholesterol", "mg/dL"): "runtime_mg_dl_to_mmol_l_conversion",
    ("Triglyceride", "mg/dL"): "runtime_mg_dl_to_mmol_l_conversion",
    ("HDL-C", "mg/dL"): "runtime_mg_dl_to_mmol_l_conversion",
    ("LDL-C", "mg/dL"): "runtime_mg_dl_to_mmol_l_conversion",
}


def _lookup_key(value: object) -> str:
    decomposed = unicodedata.normalize("NFKD", str(value or "").casefold())
    without_accents = "".join(character for character in decomposed if not unicodedata.combining(character))
    without_accents = without_accents.replace("đ", "d")
    return re.sub(r"[^a-z0-9]+", " ", without_accents).strip()


def _manual_entries() -> list[dict[str, str]]:
    text = GENERATED_CATALOG.read_text(encoding="utf-8")
    pattern = re.compile(
        r'\{\s*name:\s*"(?P<name>[^"]+)",\s*unit:\s*"(?P<unit>[^"]+)",\s*'
        r'analyteId:\s*"(?P<analyte_id>[^"]+)",\s*'
        r'canonicalGroup:\s*"(?P<group>[^"]+)",\s*'
        r'runtimeStatus:\s*"(?P<runtime_status>[^"]+)"\s*\}'
    )
    entries = [match.groupdict() for match in pattern.finditer(text)]
    for entry in entries:
        entry["category"] = GROUP_LABELS[entry["group"]]
    return entries


def test_generated_frontend_catalog_is_current() -> None:
    assert GENERATED_CATALOG.read_text(encoding="utf-8") == render_catalog()
    assert is_current()


def _mock_indicators() -> list[dict[str, str]]:
    indicators: list[dict[str, str]] = []
    for directory in MOCK_DIRS:
        for path in directory.glob("*.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            reports = payload if isinstance(payload, list) else [payload]
            for report in reports:
                for indicator in report.get("indicators", []):
                    indicators.append(
                        {
                            "path": str(path.relative_to(REPO_ROOT)),
                            "name": str(indicator.get("name") or "").strip(),
                            "unit": str(indicator.get("unit") or "").strip(),
                        }
                    )
    return indicators


def _alias_values(entry) -> set[str]:
    return {entry.canonical_name, *entry.aliases}


def test_ui_mock_001_002_frontend_entries_resolve_to_catalog_identity_and_group() -> None:
    catalog = get_analyte_catalog_contract()
    entries = _manual_entries()

    assert len(entries) == 35
    for manual in entries:
        catalog_entry = catalog.resolve(manual["name"])
        assert catalog_entry is not None, manual
        assert manual["analyte_id"] == catalog_entry.analyte_id
        assert manual["group"] == catalog_entry.group
        assert manual["category"] == GROUP_LABELS[catalog_entry.group]


def test_ui_mock_003_004_005_frontend_support_status_matches_catalog() -> None:
    catalog = get_analyte_catalog_contract()
    manual_by_name = {entry["name"]: entry for entry in _manual_entries()}

    approved = {name for name, manual in manual_by_name.items() if manual["runtime_status"] == "APPROVED"}
    assert approved == APPROVED_EXACT_SET
    assert manual_by_name["Uric acid"]["runtime_status"] == "APPROVED"
    assert "eGFR" not in manual_by_name

    for manual in manual_by_name.values():
        catalog_entry = catalog.resolve(manual["name"])
        assert catalog_entry is not None
        assert manual["runtime_status"] == catalog_entry.runtime_status


def test_ui_mock_006_007_mock_names_are_resolvable_or_explicitly_unresolved() -> None:
    catalog = get_analyte_catalog_contract()
    unresolved: dict[str, str] = {}
    classified: dict[str, str] = {}

    for indicator in _mock_indicators():
        name = indicator["name"]
        entry = catalog.resolve(name)
        if entry is None:
            unresolved[name] = UNRESOLVED_MOCK_ANALYTES.get(name, "MISSING_REASON")
            continue
        if entry.runtime_status == "HOLD":
            classified[name] = "HOLD"
        elif entry.runtime_status == "UNSUPPORTED":
            classified[name] = "UNSUPPORTED"
        elif _lookup_key(name) == _lookup_key(entry.canonical_name):
            classified[name] = "CANONICAL"
        else:
            classified[name] = "KNOWN_ALIAS"

    assert unresolved == UNRESOLVED_MOCK_ANALYTES
    assert "MISSING_REASON" not in unresolved.values()
    assert classified["Triglycerides"] == "KNOWN_ALIAS"
    assert classified["RDW"] == "KNOWN_ALIAS"
    assert classified["Uric Acid"] == "CANONICAL"
    assert classified["eGFR"] == "UNSUPPORTED"


def test_ui_mock_008_unit_contract_for_supported_frontend_and_mock_entries() -> None:
    catalog = get_analyte_catalog_contract()

    frontend_gaps: dict[str, str] = {}
    for manual in _manual_entries():
        entry = catalog.resolve(manual["name"])
        assert entry is not None
        if entry.runtime_status == "APPROVED" and ReferenceRepository.normalize_unit(
            manual["unit"]
        ) != ReferenceRepository.normalize_unit(entry.canonical_unit):
            frontend_gaps[manual["name"]] = f"{manual['unit']} != {entry.canonical_unit}"
    assert frontend_gaps == {}

    mock_gaps: dict[str, str] = {}
    for indicator in _mock_indicators():
        entry = catalog.resolve(indicator["name"])
        if entry is None or entry.runtime_status != "APPROVED":
            continue
        normalized_unit = ReferenceRepository.normalize_unit(indicator["unit"])
        normalized_canonical = ReferenceRepository.normalize_unit(entry.canonical_unit)
        if normalized_unit != normalized_canonical:
            reason = APPROVED_MOCK_UNIT_GAPS.get((entry.canonical_name, indicator["unit"]))
            if reason is None:
                mock_gaps[indicator["name"]] = f"{indicator['unit']} != {entry.canonical_unit}"

    assert mock_gaps == {}


def test_ui_mock_009_no_new_conversion_factor_is_encoded_in_frontend_or_mock_contract() -> None:
    text = MANUAL_ENTRY.read_text(encoding="utf-8")

    assert "0.0259" not in text
    assert "0.0113" not in text
    assert "180.1559" not in text
