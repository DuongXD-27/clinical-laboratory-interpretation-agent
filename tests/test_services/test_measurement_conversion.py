"""Tests for the approved GLUCOSE-CONV-01 measurement conversion."""

from decimal import Decimal

import pytest

from src.services.measurement_conversion import glucose_mmol_l_to_mg_dl


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.0, Decimal("18.01559")),
        (Decimal("0"), Decimal("0")),
        ("3.050", Decimal("54.94754950")),
        ("3.053", Decimal("55.00159627")),
        ("3.054", Decimal("55.01961186")),
        ("3.055", Decimal("55.03762745")),
        ("24.97", Decimal("449.84928230")),
        ("24.99", Decimal("450.20959410")),
    ],
)
def test_glucose_mmol_l_to_mg_dl_exact_decimal(value, expected):
    result = glucose_mmol_l_to_mg_dl(value)

    assert isinstance(result, Decimal)
    assert result == expected


@pytest.mark.parametrize("value", ["not-numeric", "", None, Decimal("NaN"), float("inf")])
def test_glucose_mmol_l_to_mg_dl_rejects_invalid_or_non_finite_input(value):
    with pytest.raises(ValueError, match="finite decimal number"):
        glucose_mmol_l_to_mg_dl(value)
