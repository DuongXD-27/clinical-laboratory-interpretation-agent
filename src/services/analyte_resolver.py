"""Authoritative canonical analyte ID resolver and locked metadata registry.

This module is the single source of truth for converting indicator names into
canonical machine IDs and mapping locked clinical rule metadata.
"""

from __future__ import annotations

# Locked 35 canonical analyte identities (IMMUTABLE)
LOCKED_35_ANALYTES: tuple[str, ...] = (
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
    "Potassium",
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
    "HDL-C",
    "LDL-C",
)

# Rule type partition across the locked 35
ANALYTE_RULE_TYPES: dict[str, str] = {
    "wbc": "RI",
    "rbc": "RI",
    "hgb": "RI",
    "hct": "RI",
    "mcv": "RI",
    "mch": "RI",
    "mchc": "RI",
    "rdw_cv": "RI",
    "plt": "RI",
    "neutrophils_%": "RI",
    "neutrophils_abs": "RI",
    "lymphocytes_%": "RI",
    "lymphocytes_abs": "RI",
    "monocytes_%": "RI",
    "monocytes_abs": "RI",
    "eosinophils_%": "RI",
    "eosinophils_abs": "RI",
    "sodium": "RI",
    "potassium": "RI",
    "chloride": "RI",
    "urea": "RI",
    "creatinine": "RI",
    "total_protein": "RI",
    "albumin": "RI",
    "uric_acid": "RI",
    "total_cholesterol": "BAND",
    "triglyceride": "BAND",
    "hdl_c": "BAND",
    "ldl_c": "BAND",
    "fasting_plasma_glucose": "CDL",
    "hba1c": "CDL",
    "ast": "ONE_SIDED_LIMIT",
    "alt": "ONE_SIDED_LIMIT",
    "ggt": "ONE_SIDED_LIMIT",
    "total_bilirubin": "ONE_SIDED_LIMIT",
}

# Frozen clinical rule band registry
FROZEN_CLINICAL_RULE_BANDS: dict[str, tuple[str, ...]] = {
    "total_cholesterol": ("desirable", "borderline_high", "high"),
    "triglyceride": ("normal", "borderline_high", "high", "very_high"),
    "hdl_c": ("low", "intermediate", "optimal"),
    "ldl_c": ("optimal", "near_optimal", "borderline_high", "high", "very_high"),
    "fasting_plasma_glucose": ("normal", "impaired_fasting_glucose", "provisional_diabetes"),
    "hba1c": ("normal_glycemia", "prediabetes_high_risk", "diabetes_diagnostic_threshold"),
}

VALID_NOTE_TYPES: tuple[str, ...] = (
    "description",
    "high_note",
    "low_note",
    "band_note",
    "critical_high_note",
    "critical_low_note",
    "preanalytic_note",
    "limitation_note",
)


def canonical_analyte_id(indicator: str) -> str:
    """Derive the canonical analyte machine ID from an indicator name.

    Convention: lowercase snake_case with spaces and hyphens replaced with underscores.
    Example:
        'LDL-C' -> 'ldl_c'
        'Fasting plasma glucose' -> 'fasting_plasma_glucose'
        'RDW-CV' -> 'rdw_cv'
        'Neutrophils %' -> 'neutrophils_%'
    """
    return str(indicator or "").strip().lower().replace("-", "_").replace(" ", "_")


# Precomputed map for fast verification
CANONICAL_ANALYTE_ID_MAP: dict[str, str] = {
    analyte: canonical_analyte_id(analyte) for analyte in LOCKED_35_ANALYTES
}
