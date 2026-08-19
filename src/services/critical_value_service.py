from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.config import get_settings
from src.services.measurement_conversion import (
    bilirubin_umol_l_to_mg_dl,
    glucose_mmol_l_to_mg_dl,
)
from src.services.reference_repository import ReferenceRepository

logger = logging.getLogger(__name__)

_ALLOWED_CRITICAL_OPERATORS = frozenset({"<", "<=", ">", ">="})
_CONVERT_INPUT_TO_SOURCE_UNIT = "CONVERT_INPUT_TO_SOURCE_UNIT"
_FASTING_PLASMA_GLUCOSE = "Fasting plasma glucose"
_GLUCOSE_INPUT_UNIT = "mmol/l"
_GLUCOSE_SOURCE_UNIT = "mg/dl"

_TOTAL_BILIRUBIN = "Total bilirubin"
_BILIRUBIN_INPUT_UNIT = "umol/l"
_BILIRUBIN_SOURCE_UNIT = "mg/dl"

# LEGACY_OPERATOR_DEFAULT: temporary Phase 2B migration compatibility only.
# Patch C must add explicit operators to every active production side, after
# which final data-quality validation will prohibit this fallback.
_LEGACY_OPERATOR_DEFAULTS = {
    "low": "<=",
    "high": ">=",
}

# ADR-010 CRIT-TREND-03: a value is "approaching" a critical threshold when it
# lies within this relative margin of the active threshold (in threshold units).
APPROACH_MARGIN = Decimal("0.10")


@dataclass(frozen=True)
class CriticalEvaluation:
    """Deterministic outcome of a critical evaluation against the registry.

    Fail-closed by design (ADR-009 / ADR-010): any configuration or unit
    mismatch yields a neutral result with no alert. ``evaluated`` distinguishes
    "analyte is not in scope / skipped" from "evaluated and found safe", so
    callers can preserve upstream indicator state when no evaluation ran.
    """

    analyte_canonical: str
    evaluated: bool
    is_critical: bool
    critical_status: str | None
    alert_message: str | None
    comparison_value: float | Decimal | None
    comparison_unit: str | None
    active_low: tuple[float | Decimal, str] | None
    active_high: tuple[float | Decimal, str] | None


def load_critical_thresholds() -> dict[str, Any]:
    settings = get_settings()
    config_path = Path(settings.critical_thresholds_path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            # Normalize keys to lowercase for case-insensitive lookup
            return {k.lower(): v for k, v in data.items()}
    return {}


CRITICAL_THRESHOLDS: dict[str, Any] = load_critical_thresholds()


def is_unit_compatible(input_unit: str, threshold_unit: str) -> bool:
    """Check unit compatibility strictly using the shared ReferenceRepository normalizer."""
    if not input_unit or not threshold_unit:
        return False
    norm_input = ReferenceRepository.normalize_unit(input_unit).strip().lower()
    norm_thresh = ReferenceRepository.normalize_unit(threshold_unit).strip().lower()
    return norm_input == norm_thresh


def parse_numeric(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def parse_decimal_numeric(val: Any) -> Decimal | None:
    if val is None:
        return None
    try:
        value = Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None
    return value if value.is_finite() else None


def compare_critical(value: float | Decimal, threshold: float | Decimal, operator: str) -> bool:
    """Compare deterministically with an allowlisted critical-rule operator.

    Invalid operators fail closed. String evaluation is deliberately not used.
    """
    if operator == "<":
        return value < threshold
    if operator == "<=":
        return value <= threshold
    if operator == ">":
        return value > threshold
    if operator == ">=":
        return value >= threshold
    return False


def resolve_active_side(
    thresholds: dict[str, Any],
    side: str,
    *,
    use_decimal: bool = False,
) -> tuple[float | Decimal, str] | None:
    """Return an executable ``(threshold, operator)`` pair or fail closed."""
    threshold_raw = thresholds.get(side)
    operator_key = f"{side}_operator"

    if threshold_raw is None:
        if thresholds.get(operator_key) is not None:
            logger.warning(
                "Critical %s side ignored: inactive threshold has non-null operator %r",
                side,
                thresholds.get(operator_key),
            )
        return None

    threshold = parse_decimal_numeric(threshold_raw) if use_decimal else parse_numeric(threshold_raw)
    if threshold is None:
        logger.warning(
            "Critical %s side ignored: threshold %r is not numeric",
            side,
            threshold_raw,
        )
        return None

    # Temporary compatibility for the current production -1 sentinels.
    if threshold < 0:
        return None

    if operator_key not in thresholds:
        operator = _LEGACY_OPERATOR_DEFAULTS[side]
        logger.debug(
            "LEGACY_OPERATOR_DEFAULT applied to active critical %s side: %s",
            side,
            operator,
        )
        return threshold, operator

    operator = thresholds.get(operator_key)
    if not isinstance(operator, str) or operator not in _ALLOWED_CRITICAL_OPERATORS:
        logger.warning(
            "Critical %s side ignored: unsupported operator %r",
            side,
            operator,
        )
        return None

    return threshold, operator


def evaluate_critical(
    analyte_canonical: str,
    value: float,
    input_unit: str,
    *,
    display_name: str | None = None,
    thresholds: dict[str, Any] | None = None,
) -> CriticalEvaluation:
    """Evaluate a single value against the critical registry (fail closed).

    ``analyte_canonical`` must already be canonicalized by the caller. Callers
    may pass a specific ``thresholds`` record (e.g. resolved from their own
    registry binding); when omitted, the shared registry is used.
    """
    display_name = display_name or analyte_canonical
    name = str(display_name).strip()
    input_unit = str(input_unit or "").strip()
    numeric_val = parse_numeric(value)
    neutral = CriticalEvaluation(
        analyte_canonical=analyte_canonical,
        evaluated=False,
        is_critical=False,
        critical_status=None,
        alert_message=None,
        comparison_value=None,
        comparison_unit=None,
        active_low=None,
        active_high=None,
    )
    if numeric_val is None:
        return neutral

    canonical_key = str(analyte_canonical).lower()
    thresholds = thresholds or CRITICAL_THRESHOLDS.get(canonical_key)
    if not thresholds:
        return neutral

    threshold_unit = thresholds.get("unit", "")

    comparison_value: float | Decimal = numeric_val
    comparison_unit = input_unit or threshold_unit
    use_decimal = False

    normalized_input_unit = ReferenceRepository.normalize_unit(input_unit).strip().lower()
    normalized_threshold_unit = ReferenceRepository.normalize_unit(threshold_unit).strip().lower()
    same_normalized_unit = is_unit_compatible(input_unit, threshold_unit)
    approved_glucose_conversion = (
        analyte_canonical == _FASTING_PLASMA_GLUCOSE
        and thresholds.get("vmec_comparison_strategy") == _CONVERT_INPUT_TO_SOURCE_UNIT
        and normalized_input_unit == _GLUCOSE_INPUT_UNIT
        and normalized_threshold_unit == _GLUCOSE_SOURCE_UNIT
    )
    approved_bilirubin_conversion = (
        analyte_canonical == _TOTAL_BILIRUBIN
        and thresholds.get("vmec_comparison_strategy") == _CONVERT_INPUT_TO_SOURCE_UNIT
        and normalized_input_unit == _BILIRUBIN_INPUT_UNIT
        and normalized_threshold_unit == _BILIRUBIN_SOURCE_UNIT
    )

    if approved_glucose_conversion:
        try:
            comparison_value = glucose_mmol_l_to_mg_dl(value)
        except ValueError:
            logger.warning(
                "Critical glucose conversion skipped for '%s': value %r is invalid",
                name,
                value,
            )
            return neutral
        comparison_unit = threshold_unit
        use_decimal = True
    elif approved_bilirubin_conversion:
        try:
            comparison_value = bilirubin_umol_l_to_mg_dl(value)
        except ValueError:
            logger.warning(
                "Critical bilirubin conversion skipped for '%s': value %r is invalid",
                name,
                value,
            )
            return neutral
        comparison_unit = threshold_unit
        use_decimal = True
    elif not same_normalized_unit:
        logger.warning(
            "Critical evaluation skipped for '%s' (canonical: '%s'): unit '%s' does not match threshold unit '%s' and no approved conversion applies (fail closed)",
            name,
            analyte_canonical,
            input_unit,
            threshold_unit,
        )
        return neutral

    low_side = resolve_active_side(thresholds, "low", use_decimal=use_decimal)
    high_side = resolve_active_side(thresholds, "high", use_decimal=use_decimal)

    if low_side is not None and compare_critical(comparison_value, low_side[0], low_side[1]):
        low_val, low_operator = low_side
        return CriticalEvaluation(
            analyte_canonical=analyte_canonical,
            evaluated=True,
            is_critical=True,
            critical_status="critical_low",
            alert_message=(
                f"CẢNH BÁO: {name} giảm tới ngưỡng nguy kịch "
                f"({comparison_value} {low_operator} {low_val} {comparison_unit}). "
                "Yêu cầu can thiệp y tế."
            ),
            comparison_value=comparison_value,
            comparison_unit=comparison_unit,
            active_low=low_side,
            active_high=high_side,
        )
    if high_side is not None and compare_critical(comparison_value, high_side[0], high_side[1]):
        high_val, high_operator = high_side
        return CriticalEvaluation(
            analyte_canonical=analyte_canonical,
            evaluated=True,
            is_critical=True,
            critical_status="critical_high",
            alert_message=(
                f"CẢNH BÁO: {name} tăng tới ngưỡng nguy kịch "
                f"({comparison_value} {high_operator} {high_val} {comparison_unit}). "
                "Yêu cầu can thiệp y tế."
            ),
            comparison_value=comparison_value,
            comparison_unit=comparison_unit,
            active_low=low_side,
            active_high=high_side,
        )

    return CriticalEvaluation(
        analyte_canonical=analyte_canonical,
        evaluated=True,
        is_critical=False,
        critical_status=None,
        alert_message=None,
        comparison_value=comparison_value,
        comparison_unit=comparison_unit,
        active_low=low_side,
        active_high=high_side,
    )


def approaches_critical(
    evaluation: CriticalEvaluation,
    previous_value: float,
    *,
    latest_raw: float | None = None,
) -> bool:
    """ADR-010 CRIT-TREND-03 approaching rule.

    True only when ALL hold:
      - the analyte has an active critical threshold (any side);
      - the latest point is not already critical;
      - the latest point is moving toward a threshold (latest > previous when the
        high side is active, latest < previous when the low side is active);
      - the latest value lies within APPROACH_MARGIN of that active threshold
        (computed in threshold units).
    """
    if evaluation.is_critical or evaluation.comparison_value is None:
        return False
    if evaluation.active_low is None and evaluation.active_high is None:
        return False

    latest = evaluation.comparison_value
    latest_raw = latest_raw if latest_raw is not None else _as_decimal(latest)

    if evaluation.active_high is not None:
        threshold, _ = evaluation.active_high
        if latest_raw > previous_value and _within_margin(latest, threshold):
            return True
    if evaluation.active_low is not None:
        threshold, _ = evaluation.active_low
        if latest_raw < previous_value and _within_margin(latest, threshold):
            return True
    return False


def _as_decimal(value: float | Decimal) -> Decimal:
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return Decimal("0")


def _within_margin(value: float | Decimal, threshold: float | Decimal) -> bool:
    threshold_decimal = _as_decimal(threshold)
    if threshold_decimal == 0:
        return False
    margin = abs(_as_decimal(value) - threshold_decimal) / abs(threshold_decimal)
    return margin <= APPROACH_MARGIN
