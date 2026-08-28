"""Narrow, approved measurement conversions used by runtime safety rules."""

from decimal import Decimal, InvalidOperation
from typing import Any

# Molecular weight authority only: NIST Chemistry WebBook, D-Glucose,
# CAS 492-62-6, molecular weight 180.1559 g/mol. NIST is not the authority
# for the clinical critical thresholds that consume this conversion.
GLUCOSE_MW_NIST = Decimal("180.1559")

# Molecular weight authority: NIST Chemistry WebBook / PubChem CID 5280352,
# Bilirubin, CAS 635-65-4, molecular weight 584.66 g/mol.
# 1 mg/dL = 10 mg/L = (10 / 584.66) * 1000 umol/L = 17.102247 umol/L.
# Conversion formula: value_mg_dl = value_umol_l * 584.66 / 10000.
BILIRUBIN_MW_NIST = Decimal("584.66")

# Lipid conversion factors: CDC NHANES / Mayo Clinic / NCEP ATP III
# Standard international clinical conversion factors:
# Cholesterol (Total, HDL, LDL): 1 mg/dL = 0.0259 mmol/L
# Triglyceride: 1 mg/dL = 0.0113 mmol/L
CHOLESTEROL_CONVERSION_FACTOR = Decimal("0.0259")
TRIGLYCERIDE_CONVERSION_FACTOR = Decimal("0.0113")


def validate_numeric_measurement(value: Any) -> Decimal:
    """Validate that value is a finite, non-negative decimal measurement.

    Rejects:
    - None or non-parseable values
    - Negative finite numbers (< 0)
    - NaN, +Infinity, -Infinity

    Raises ``ValueError`` on invalid or impossible domain values so callers can fail closed.
    """
    if value is None:
        raise ValueError("measurement value must be a finite decimal number (cannot be None)")

    try:
        dec = Decimal(str(value).strip())
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"invalid numeric measurement: {value}; value must be a finite decimal number") from exc

    if not dec.is_finite():
        raise ValueError(f"non-finite numeric measurement: {value}; value must be a finite decimal number")

    if dec < Decimal("0"):
        raise ValueError(f"negative numeric measurement: {value}; value must be >= 0")

    return dec


def is_valid_numeric_measurement(value: Any) -> bool:
    """Check if value is a finite, non-negative decimal measurement."""
    try:
        validate_numeric_measurement(value)
        return True
    except (ValueError, TypeError):
        return False


def glucose_mmol_l_to_mg_dl(value_mmol_l: float | str | Decimal) -> Decimal:
    """Convert glucose mmol/L to mg/dL exactly, without rounding or quantization.

    Invalid, negative, and non-finite inputs raise ``ValueError`` so callers can fail
    closed without attempting a critical comparison.
    """
    value = validate_numeric_measurement(value_mmol_l)
    return value * GLUCOSE_MW_NIST / Decimal("10")


def bilirubin_umol_l_to_mg_dl(value_umol_l: float | str | Decimal) -> Decimal:
    """Convert bilirubin umol/L to mg/dL exactly, without rounding or quantization.

    Invalid, negative, and non-finite inputs raise ``ValueError`` so callers can fail
    closed without attempting a critical comparison.
    """
    value = validate_numeric_measurement(value_umol_l)
    return value * BILIRUBIN_MW_NIST / Decimal("10000")


def cholesterol_mmol_l_to_mg_dl(value_mmol_l: float | str | Decimal) -> Decimal:
    """Convert cholesterol (TC, HDL-C, LDL-C) mmol/L to mg/dL at full Decimal precision."""
    value = validate_numeric_measurement(value_mmol_l)
    return value / CHOLESTEROL_CONVERSION_FACTOR


def cholesterol_mg_dl_to_mmol_l(value_mg_dl: float | str | Decimal) -> Decimal:
    """Convert cholesterol (TC, HDL-C, LDL-C) mg/dL to mmol/L at full Decimal precision."""
    value = validate_numeric_measurement(value_mg_dl)
    return value * CHOLESTEROL_CONVERSION_FACTOR


def triglyceride_mmol_l_to_mg_dl(value_mmol_l: float | str | Decimal) -> Decimal:
    """Convert triglyceride mmol/L to mg/dL at full Decimal precision."""
    value = validate_numeric_measurement(value_mmol_l)
    return value / TRIGLYCERIDE_CONVERSION_FACTOR


def triglyceride_mg_dl_to_mmol_l(value_mg_dl: float | str | Decimal) -> Decimal:
    """Convert triglyceride mg/dL to mmol/L at full Decimal precision."""
    value = validate_numeric_measurement(value_mg_dl)
    return value * TRIGLYCERIDE_CONVERSION_FACTOR


def classify_lipid_band(
    analyte_canonical: str,
    value: float | str | Decimal,
    unit: str,
) -> str:
    """Classify lipid BAND using authoritative native mg/dL thresholds.

    Evaluates full-precision native mg/dL equivalent against source boundaries.
    """
    norm_unit = str(unit).strip().lower()
    norm_name = str(analyte_canonical).strip().lower()

    if norm_unit in {"mmol/l", "mmol/l."}:
        if norm_name in {"triglyceride", "triglycerides"}:
            mg_dl_val = triglyceride_mmol_l_to_mg_dl(value)
        else:
            mg_dl_val = cholesterol_mmol_l_to_mg_dl(value)
    elif norm_unit in {"mg/dl", "mg/dl."}:
        mg_dl_val = validate_numeric_measurement(value)
    else:
        raise ValueError(f"unsupported lipid unit: {unit}")

    if norm_name in {"total cholesterol", "total_cholesterol"}:
        if mg_dl_val < Decimal("200"):
            return "desirable"
        if mg_dl_val < Decimal("240"):
            return "borderline_high"
        return "high"

    if norm_name in {"triglyceride", "triglycerides"}:
        if mg_dl_val < Decimal("150"):
            return "normal"
        if mg_dl_val < Decimal("200"):
            return "borderline_high"
        if mg_dl_val < Decimal("500"):
            return "high"
        return "very_high"

    if norm_name in {"hdl-c", "hdl_c", "hdl-cholesterol", "hdl"}:
        if mg_dl_val < Decimal("40"):
            return "low"
        if mg_dl_val < Decimal("60"):
            return "intermediate"
        return "optimal"

    if norm_name in {"ldl-c", "ldl_c", "ldl-cholesterol", "ldl"}:
        if mg_dl_val < Decimal("100"):
            return "optimal"
        if mg_dl_val < Decimal("130"):
            return "near_optimal"
        if mg_dl_val < Decimal("160"):
            return "borderline_high"
        if mg_dl_val < Decimal("190"):
            return "high"
        return "very_high"

    raise ValueError(f"unknown lipid analyte: {analyte_canonical}")
