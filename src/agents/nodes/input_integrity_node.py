"""Pipeline gate for source-backed measurement plausibility rules."""

from __future__ import annotations

import logging
from functools import lru_cache

from src.agents.nodes.reference_range_checker_node import get_reference_repository
from src.agents.state import AgentState
from src.services.input_integrity import (
    InputIntegrityConfigurationError,
    InputIntegrityEvaluator,
    PlausibilityRepository,
)
from src.services.measurement_conversion import validate_numeric_measurement
from src.services.reference_repository import ReferenceRepositoryError

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def get_input_integrity_evaluator() -> InputIntegrityEvaluator:
    return InputIntegrityEvaluator(PlausibilityRepository.from_default_file())


async def input_integrity_node(state: AgentState) -> dict:
    """Resolve identity/unit, then evaluate only explicitly activated rules."""

    try:
        reference_repository = get_reference_repository()
    except ReferenceRepositoryError as exc:
        logger.error("Input-integrity gate unavailable: %s", exc)
        return {"input_integrity_results": []}

    try:
        evaluator = get_input_integrity_evaluator()
    except InputIntegrityConfigurationError as exc:
        # A valid empty registry is backward-compatible. A missing/corrupt
        # registry is different: silently bypassing a rule that operators
        # intended to be active would be unsafe, so supported canonical rows
        # stop before classification.
        logger.error("Input-integrity configuration unavailable: %s", exc)
        blocked_results = []
        for index, indicator in enumerate(state.get("raw_indicators", [])):
            canonical_analyte = reference_repository.resolve_analyte(
                str(indicator.get("name", "")).strip()
            )
            if canonical_analyte is None:
                continue
            blocked_results.append(
                {
                    "index": index,
                    "status": "NEED_REVIEW",
                    "reason_code": "INPUT_INTEGRITY_CONFIGURATION_UNAVAILABLE",
                    "message": InputIntegrityEvaluator.REVIEW_MESSAGE,
                    "rule_id": None,
                    "source_id": None,
                    "observed_value": indicator.get("value"),
                    "canonical_analyte": canonical_analyte,
                    "canonical_unit": reference_repository.normalize_unit(
                        str(indicator.get("unit", ""))
                    ),
                }
            )
        return {"input_integrity_results": blocked_results}

    results: list[dict] = []
    for index, indicator in enumerate(state.get("raw_indicators", [])):
        raw_name = str(indicator.get("name", "")).strip()
        raw_unit = str(indicator.get("unit", "")).strip()
        canonical_analyte = reference_repository.resolve_analyte(raw_name)
        if canonical_analyte is None:
            continue

        canonical_unit = reference_repository.canonical_unit_for(canonical_analyte)
        normalized_input_unit = reference_repository.normalize_unit(raw_unit)
        # Numeric conversion is intentionally not inferred here. An active rule
        # applies only when the submitted unit normalizes to its canonical unit.
        if canonical_unit is None or normalized_input_unit != canonical_unit:
            continue
        try:
            numeric_value = validate_numeric_measurement(indicator.get("value"))
        except (TypeError, ValueError):
            continue

        result = evaluator.evaluate(
            analyte=canonical_analyte,
            value=numeric_value,
            canonical_unit=canonical_unit,
        )
        serialized = {
            "index": index,
            "status": result.status,
            "reason_code": result.reason_code,
            "message": result.message,
            "rule_id": result.rule_id,
            "source_id": result.source_id,
            "observed_value": float(result.observed_value),
            "canonical_analyte": canonical_analyte,
            "canonical_unit": result.canonical_unit,
        }
        results.append(serialized)
        if result.status == "NEED_REVIEW":
            logger.warning(
                "input_integrity analyte=%s reason_code=%s rule_id=%s result=NEED_REVIEW",
                canonical_analyte,
                result.reason_code,
                result.rule_id,
            )

    return {"input_integrity_results": results}
