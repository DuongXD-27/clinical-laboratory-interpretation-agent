"""Extract supplemental reference rules from explanations.json for analytes absent from the primary catalog."""

from __future__ import annotations

import json
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

# Alias map: explanation indicator → canonical analyte name used in the V2 catalog
ALIAS_MAP: dict[str, str] = {
    "Glucose": "Fasting plasma glucose",
    "LDL-Cholesterol": "LDL-C",
    "HDL-Cholesterol": "HDL-C",
    "Kali": "Potassium",
}

# Stable rule ID namespace prefixes, one per supplemental analyte
_ID_PREFIX: dict[str, str] = {
    "HbA1c": "EXPV2-HBA1C",
    "LDL-C": "EXPV2-LDLC",
    "Potassium": "EXPV2-POTASSIUM",
    "HDL-C": "EXPV2-HDLC",
}

# Deterministic group ordering for stable rule ID assignment across rebuilds
_GROUP_ORDER: dict[str, list[str]] = {
    "HbA1c": ["normal", "prediabetes", "diabetes"],
    "LDL-C": ["optimal", "acceptable", "borderline_high", "high", "very_high"],
    "Potassium": [
        "normal",
        "mild_hyperkalemia",
        "moderate_hyperkalemia",
        "severe_hyperkalemia",
        "mild_hypokalemia",
        "moderate_hypokalemia",
        "severe_hypokalemia",
    ],
    "HDL-C": ["optimal", "average", "low"],
}

# Groups classified as medical-decision (MD) rather than reference-interval (RI)
_MD_GROUPS: dict[str, set[str]] = {
    "HbA1c": {"prediabetes", "diabetes"},
    "LDL-C": {"acceptable", "borderline_high", "high", "very_high"},
    "Potassium": {
        "mild_hyperkalemia",
        "moderate_hyperkalemia",
        "severe_hyperkalemia",
        "mild_hypokalemia",
        "moderate_hypokalemia",
        "severe_hypokalemia",
    },
    "HDL-C": {"optimal", "low"},
}

# Inclusive boundary overlaps preserved verbatim from source; reported as warnings.
# Values are NOT altered — they are reproduced exactly from explanations.json.
_BOUNDARY_WARNINGS: list[dict[str, Any]] = [
    {
        "analyte": "HbA1c",
        "groups": ("normal", "prediabetes"),
        "boundary_value": 5.7,
        "unit": "%",
        "note": "normal upper=5.7 equals prediabetes lower=5.7; inclusive overlap preserved verbatim",
    },
    {
        "analyte": "Potassium",
        "groups": ("mild_hypokalemia", "moderate_hypokalemia"),
        "boundary_value": 3.0,
        "unit": "mmol/L",
        "note": "mild_hypokalemia lower=3.0 equals moderate_hypokalemia upper=3.0; preserved verbatim",
    },
    {
        "analyte": "Potassium",
        "groups": ("moderate_hyperkalemia", "severe_hyperkalemia"),
        "boundary_value": 7.0,
        "unit": "mmol/L",
        "note": "moderate_hyperkalemia upper=7.0 equals severe_hyperkalemia lower=7.0; preserved verbatim",
    },
    {
        "analyte": "HDL-C",
        "groups": ("average_m", "low_m"),
        "boundary_value": 1.04,
        "unit": "mmol/L",
        "note": "average_m lower=1.04 mmol/L equals low_m upper=1.04 mmol/L; converted from 40 mg/dL × 0.0259; inclusive overlap preserved verbatim",
    },
    {
        "analyte": "HDL-C",
        "groups": ("average_f", "low_f"),
        "boundary_value": 1.30,
        "unit": "mmol/L",
        "note": "average_f lower=1.30 mmol/L equals low_f upper=1.30 mmol/L; converted from 50 mg/dL × 0.0259; inclusive overlap preserved verbatim",
    },
]

# Conversion factor for HDL-C mg/dL → mmol/L
_HDL_CONVERSION_FACTOR = Decimal("0.0259")


def convert_mgdl_to_mmol(value_mgdl: float) -> float:
    """Convert mg/dL to mmol/L using factor 0.0259, rounded ROUND_HALF_UP to 2 decimal places."""
    result = _HDL_CONVERSION_FACTOR * Decimal(str(value_mgdl))
    return float(result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def canonical_analyte(indicator: str) -> str:
    """Resolve an explanation indicator to its canonical analyte name via alias map."""
    return ALIAS_MAP.get(indicator, indicator)


def _reference_type(analyte: str, group: str) -> str:
    if group in _MD_GROUPS.get(analyte, set()):
        return "MD"
    return "RI"


def extract_supplemental_rules(
    explanations_path: Path,
    primary_analytes: set[str],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """
    Parse explanations.json and produce supplemental JSON-ready rules for analytes
    semantically absent from the primary catalog.

    Skips analytes present in primary_analytes (after alias resolution).
    Only analytes with an _ID_PREFIX entry are eligible for supplemental import.

    Returns:
        (rules, warnings)
        rules   — list of supplemental rule dicts with None for null fields
        warnings — list of inclusive-boundary overlap descriptors
    """
    with explanations_path.open("r", encoding="utf-8") as file:
        entries: list[dict[str, Any]] = json.load(file)

    rules: list[dict[str, Any]] = []

    for entry in entries:
        indicator = str(entry.get("indicator", "")).strip()
        analyte = canonical_analyte(indicator)

        if analyte in primary_analytes:
            continue

        prefix = _ID_PREFIX.get(analyte)
        if prefix is None:
            continue

        sources: list[str] = [str(s) for s in entry.get("sources", [])]
        primary_source_url = sources[0] if sources else None
        entry_id = str(entry.get("id", ""))

        group_order = _GROUP_ORDER.get(analyte, [])
        sorted_ranges = sorted(
            entry.get("reference_ranges", []),
            key=lambda r: (
                group_order.index(r["group"]) if r["group"] in group_order else 9999,
                str(r.get("gender", "A")),
            ),
        )

        for seq, rng in enumerate(sorted_ranges, start=1):
            group = str(rng.get("group", ""))
            gender_raw = str(rng.get("gender", "A"))
            sex = {"M": "M", "F": "F", "A": "A"}.get(gender_raw, "A")
            unit = str(rng.get("unit", ""))
            low = rng.get("low")
            high = rng.get("high")
            note = str(rng.get("note") or "")

            # Provenance fields — populated only for unit-converted analytes
            source_unit_original: str | None = None
            source_range_lower_original: float | None = None
            source_range_upper_original: float | None = None
            conversion_factor: str | None = None
            conversion_rounding: str | None = None

            if analyte == "HDL-C":
                source_unit_original = unit
                source_range_lower_original = float(low) if low is not None else None
                source_range_upper_original = float(high) if high is not None else None
                conversion_factor = "0.0259"
                conversion_rounding = "ROUND_HALF_UP_2DP"
                unit = "mmol/L"
                range_lower = convert_mgdl_to_mmol(low) if low is not None else None
                range_upper = convert_mgdl_to_mmol(high) if high is not None else None
            else:
                range_lower = float(low) if low is not None else None
                range_upper = float(high) if high is not None else None

            rules.append({
                "rule_id": f"{prefix}-{seq:03d}",
                "source_row_number": None,
                "analyte_canonical": analyte,
                "specimen": None,
                "fasting_required": None,
                "sex": sex,
                "age_scope": "Adult",
                "unit_machine": unit,
                "unit_display_vn": unit,
                "unit_raw": unit,
                "unit_canonical": unit,
                "value_type": None,
                "range_lower": range_lower,
                "range_upper": range_upper,
                "reference_type": _reference_type(analyte, group),
                "source_priority_tier": None,
                "source_url": primary_source_url,
                "confidence": "CURATED",
                "range_flag": "OK",
                "source_origin": "explanations.json",
                "source_entry_id": entry_id,
                "range_group": group,
                "range_note": note,
                "source_urls": sources,
                "source_unit_original": source_unit_original,
                "source_range_lower_original": source_range_lower_original,
                "source_range_upper_original": source_range_upper_original,
                "conversion_factor": conversion_factor,
                "conversion_rounding": conversion_rounding,
            })

    return rules, [dict(w) for w in _BOUNDARY_WARNINGS]
