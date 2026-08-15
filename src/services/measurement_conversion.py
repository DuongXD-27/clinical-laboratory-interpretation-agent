"""Narrow, approved measurement conversions used by runtime safety rules."""

from decimal import Decimal, InvalidOperation

# Molecular weight authority only: NIST Chemistry WebBook, D-Glucose,
# CAS 492-62-6, molecular weight 180.1559 g/mol. NIST is not the authority
# for the clinical critical thresholds that consume this conversion.
GLUCOSE_MW_NIST = Decimal("180.1559")


def glucose_mmol_l_to_mg_dl(value_mmol_l: float | str | Decimal) -> Decimal:
    """Convert glucose mmol/L to mg/dL exactly, without rounding or quantization.

    Invalid and non-finite inputs raise ``ValueError`` so callers can fail
    closed without attempting a critical comparison.
    """
    try:
        value = Decimal(str(value_mmol_l))
    except (InvalidOperation, ValueError):
        raise ValueError("glucose value must be a finite decimal number") from None

    if not value.is_finite():
        raise ValueError("glucose value must be a finite decimal number")

    return value * GLUCOSE_MW_NIST / Decimal("10")
