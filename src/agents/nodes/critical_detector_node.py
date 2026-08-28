import json
import logging
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.agents.nodes.reference_range_checker_node import get_reference_repository
from src.agents.state import AgentState, CriticalAlert, IndicatorAssessment
from src.config import get_settings
from src.services.measurement_conversion import (
    bilirubin_umol_l_to_mg_dl,
    glucose_mmol_l_to_mg_dl,
    validate_numeric_measurement,
)
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

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


def load_critical_thresholds() -> dict:
    settings = get_settings()
    config_path = Path(settings.critical_thresholds_path)
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            data = json.load(f)
            # Normalize keys to lowercase for case-insensitive lookup
            return {k.lower(): v for k, v in data.items()}
    return {}


CRITICAL_THRESHOLDS = load_critical_thresholds()


def _is_unit_compatible(
    input_unit: str,
    threshold_unit: str,
) -> bool:
    """Check unit compatibility strictly using the shared ReferenceRepository normalizer.

    Current V1 Policy:
    1. Normalize input unit using ReferenceRepository.normalize_unit().
    2. Normalize threshold unit using ReferenceRepository.normalize_unit().
    3. Direct numeric comparison is allowed ONLY when normalized units are identical.
    4. Otherwise critical evaluation is skipped / fails closed.
    """
    if not input_unit or not threshold_unit:
        return False

    norm_input = ReferenceRepository.normalize_unit(input_unit).strip().lower()
    norm_thresh = ReferenceRepository.normalize_unit(threshold_unit).strip().lower()

    return norm_input == norm_thresh


def _parse_numeric(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_decimal_numeric(val: Any) -> Decimal | None:
    try:
        return validate_numeric_measurement(val)
    except (ValueError, TypeError):
        return None


def _compare_critical(
    value: float | Decimal,
    threshold: float | Decimal,
    operator: str,
) -> bool:
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


def _critical_alert_message(
    *,
    name: str,
    direction: str,
    original_value: float,
    original_unit: str,
    comparison_value: float | Decimal,
    operator: str,
    threshold: float | Decimal,
    comparison_unit: str,
) -> str:
    comparison = f"{comparison_value} {operator} {threshold} {comparison_unit}"
    if not _is_unit_compatible(original_unit, comparison_unit):
        comparison = f"giá trị nhập {original_value} {original_unit}; giá trị quy đổi chỉ để so ngưỡng: {comparison}"
    return f"CẢNH BÁO: {name} {direction} tới ngưỡng nguy kịch ({comparison}). Yêu cầu can thiệp y tế."


def _resolve_active_side(
    thresholds: dict[str, Any],
    side: str,
    *,
    use_decimal: bool = False,
) -> tuple[float | Decimal, str] | None:
    """Return an executable ``(threshold, operator)`` pair or fail closed.

    ``null`` is the final inactive representation. Negative thresholds remain
    temporarily inactive for compatibility with the pre-migration ``-1``
    sentinel data, but are not valid final-schema values.
    """
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

    threshold = _parse_decimal_numeric(threshold_raw) if use_decimal else _parse_numeric(threshold_raw)
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


async def detect_critical_values_node(state: AgentState) -> dict:
    """Phát hiện các chỉ số ở mức nguy kịch (critical) bằng rule-based an toàn đơn vị và định danh."""
    raw_indicators = state.get("raw_indicators", [])

    # Check if indicators were already populated by upstream node (e.g. reference_range_checker)
    has_upstream_indicators = bool(state.get("indicators"))
    indicators: list[IndicatorAssessment] = state.get("indicators", [])

    if not indicators and raw_indicators:
        indicators = [
            {
                "name": ind["name"],
                "value": ind["value"],
                "unit": ind.get("unit", ""),
                "reference_low": None,
                "reference_high": None,
                "status": "unknown",
                "is_abnormal": False,
                "is_critical": False,
            }
            for ind in raw_indicators
        ]

    # Tạo bản sao list mới thay vì dùng reference để tránh lỗi Duplicate Alerts
    critical_alerts: list[CriticalAlert] = list(state.get("critical_alerts", []))
    has_critical = state.get("has_critical_values", False)

    try:
        repository = get_reference_repository()
    except ReferenceRepositoryError as exc:
        logger.error("Reference repository unavailable in critical detector: %s", exc)
        repository = None

    updated_indicators = []

    for ind in indicators:
        # Copy dictionary để không ảnh hưởng trực tiếp đến state reference
        new_ind = dict(ind)
        name = new_ind.get("name", "")
        val = new_ind.get("value")
        input_unit = str(new_ind.get("unit", "")).strip()
        current_status = new_ind.get("status")

        numeric_val = _parse_numeric(val)
        if numeric_val is None or not name:
            updated_indicators.append(new_ind)
            continue

        # Blocker 02: If upstream Reference Range Checker already evaluated and returned 'unknown',
        # do NOT overwrite unknown with critical_low / critical_high.
        if has_upstream_indicators and current_status == "unknown":
            logger.debug(
                "Critical evaluation skipped for '%s': upstream status is 'unknown'",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        # Blocker 01: Canonicalization via ReferenceRepository.
        # Canonicalization failure MUST NOT fall back to raw name lookup in CRITICAL_THRESHOLDS.
        if repository is None:
            logger.warning(
                "Critical evaluation skipped for '%s': ReferenceRepository unavailable",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        canonical_analyte = repository.resolve_analyte(name)
        if not canonical_analyte:
            logger.debug(
                "Critical evaluation skipped for '%s': analyte not resolvable by ReferenceRepository",
                name,
            )
            updated_indicators.append(new_ind)
            continue

        # Look up threshold strictly by canonical analyte name (lowercase)
        canonical_key = canonical_analyte.lower()
        if canonical_key not in CRITICAL_THRESHOLDS:
            # Not a critical-registered analyte
            updated_indicators.append(new_ind)
            continue

        thresholds = CRITICAL_THRESHOLDS[canonical_key]
        threshold_unit = thresholds.get("unit", "")
        source_url = str(thresholds.get("source_url") or "").strip()
        if source_url:
            new_ind["critical_threshold_source"] = {
                "source_id": str(thresholds.get("source_id") or ""),
                "title": str(thresholds.get("source_title") or ""),
                "organization": str(thresholds.get("source_organization") or ""),
                "url": source_url,
                "section_or_context": (
                    f"Page {thresholds['source_page']}: {thresholds['source_literal']}"
                    if thresholds.get("source_page") and thresholds.get("source_literal")
                    else str(thresholds.get("source_literal") or "").strip() or None
                ),
                "analyte": canonical_analyte,
                "note_type": "critical_threshold",
            }

        # Blocker 03: compare directly only in the same normalized unit. The
        # sole cross-unit path is the human-approved, explicitly configured
        # glucose mmol/L -> mg/dL conversion below.
        comparison_value: float | Decimal = numeric_val
        comparison_unit = input_unit or threshold_unit
        use_decimal = False

        normalized_input_unit = ReferenceRepository.normalize_unit(input_unit).strip().lower()
        normalized_threshold_unit = ReferenceRepository.normalize_unit(threshold_unit).strip().lower()
        same_normalized_unit = _is_unit_compatible(input_unit, threshold_unit)
        approved_glucose_conversion = (
            canonical_analyte == _FASTING_PLASMA_GLUCOSE
            and thresholds.get("vmec_comparison_strategy") == _CONVERT_INPUT_TO_SOURCE_UNIT
            and normalized_input_unit == _GLUCOSE_INPUT_UNIT
            and normalized_threshold_unit == _GLUCOSE_SOURCE_UNIT
        )
        approved_bilirubin_conversion = (
            canonical_analyte == _TOTAL_BILIRUBIN
            and thresholds.get("vmec_comparison_strategy") == _CONVERT_INPUT_TO_SOURCE_UNIT
            and normalized_input_unit == _BILIRUBIN_INPUT_UNIT
            and normalized_threshold_unit == _BILIRUBIN_SOURCE_UNIT
        )

        if approved_glucose_conversion:
            try:
                comparison_value = glucose_mmol_l_to_mg_dl(val)
            except ValueError:
                logger.warning(
                    "Critical glucose conversion skipped for '%s': value %r is invalid",
                    name,
                    val,
                )
                updated_indicators.append(new_ind)
                continue
            comparison_unit = threshold_unit
            use_decimal = True
        elif approved_bilirubin_conversion:
            try:
                comparison_value = bilirubin_umol_l_to_mg_dl(val)
            except ValueError:
                logger.warning(
                    "Critical bilirubin conversion skipped for '%s': value %r is invalid",
                    name,
                    val,
                )
                updated_indicators.append(new_ind)
                continue
            comparison_unit = threshold_unit
            use_decimal = True
        elif not same_normalized_unit:
            logger.warning(
                "Critical evaluation skipped for '%s' (canonical: '%s'): unit '%s' does not match threshold unit '%s' and no approved conversion applies (fail closed)",
                name,
                canonical_analyte,
                input_unit,
                threshold_unit,
            )
            updated_indicators.append(new_ind)
            continue

        low_side = _resolve_active_side(thresholds, "low", use_decimal=use_decimal)
        high_side = _resolve_active_side(thresholds, "high", use_decimal=use_decimal)

        # Side-local, deterministic comparison. An invalid side fails closed
        # without preventing the valid opposite side from being evaluated.
        if low_side is not None and _compare_critical(comparison_value, low_side[0], low_side[1]):
            low_val, low_operator = low_side
            new_ind["is_abnormal"] = True
            new_ind["is_critical"] = True
            new_ind["critical_status"] = "critical_low"
            has_critical = True
            # Chống trùng lặp (nếu đồ thị chạy lại / retry)
            if not any(a.get("indicator_name") == name for a in critical_alerts):
                critical_alerts.append(
                    {
                        "indicator_name": name,
                        "value": val,
                        "unit": input_unit,
                        "message": _critical_alert_message(
                            name=name,
                            direction="giảm",
                            original_value=val,
                            original_unit=input_unit,
                            comparison_value=comparison_value,
                            operator=low_operator,
                            threshold=low_val,
                            comparison_unit=comparison_unit,
                        ),
                    }
                )
        elif high_side is not None and _compare_critical(comparison_value, high_side[0], high_side[1]):
            high_val, high_operator = high_side
            new_ind["is_abnormal"] = True
            new_ind["is_critical"] = True
            new_ind["critical_status"] = "critical_high"
            has_critical = True
            # Chống trùng lặp
            if not any(a.get("indicator_name") == name for a in critical_alerts):
                critical_alerts.append(
                    {
                        "indicator_name": name,
                        "value": val,
                        "unit": input_unit,
                        "message": _critical_alert_message(
                            name=name,
                            direction="tăng",
                            original_value=val,
                            original_unit=input_unit,
                            comparison_value=comparison_value,
                            operator=high_operator,
                            threshold=high_val,
                            comparison_unit=comparison_unit,
                        ),
                    }
                )
        else:
            new_ind["is_critical"] = False
            new_ind["critical_status"] = None

        # Giữ lại indicator đã xử lý
        updated_indicators.append(new_ind)

    return {
        "indicators": updated_indicators,
        "critical_alerts": critical_alerts,
        "has_critical_values": has_critical,
    }
