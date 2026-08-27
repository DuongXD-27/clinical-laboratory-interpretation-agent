"""Deterministic, source-backed input-integrity rules for lab measurements.

This module deliberately owns plausibility only. Reference intervals and
critical thresholds are separate medical concepts and are never used to infer
or synthesize an integrity bound here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Literal

from src.config import get_settings
from src.services.measurement_conversion import validate_numeric_measurement
from src.services.reference_repository import ReferenceRepository

InputIntegrityStatus = Literal["VALID", "NEED_REVIEW"]

_BOUND_OPERATORS = frozenset({">", ">=", "<", "<="})


class InputIntegrityConfigurationError(ValueError):
    """Raised when an integrity configuration cannot be executed safely."""


@dataclass(frozen=True)
class InputIntegrityRule:
    rule_id: str
    analyte: str
    canonical_unit: str
    lower_bound: Decimal | None
    lower_operator: str | None
    upper_bound: Decimal | None
    upper_operator: str | None
    source_id: str
    source: str
    source_section: str
    reason: str


@dataclass(frozen=True)
class InputIntegrityResult:
    status: InputIntegrityStatus
    reason_code: str | None
    message: str
    rule_id: str | None
    source_id: str | None
    observed_value: Decimal
    canonical_unit: str


class PlausibilityRepository:
    """Validated registry of explicitly approved input-integrity rules."""

    REQUIRED_RULE_FIELDS = frozenset(
        {
            "rule_id",
            "analyte",
            "canonical_unit",
            "lower_bound",
            "lower_operator",
            "upper_bound",
            "upper_operator",
            "source_id",
            "source",
            "source_section",
            "reason",
            "status",
        }
    )

    def __init__(self, rules: list[InputIntegrityRule]):
        by_key: dict[tuple[str, str], InputIntegrityRule] = {}
        for rule in rules:
            key = (rule.analyte.casefold(), ReferenceRepository.normalize_unit(rule.canonical_unit).casefold())
            if key in by_key:
                raise InputIntegrityConfigurationError(
                    f"duplicate active input-integrity rule for {rule.analyte} {rule.canonical_unit}"
                )
            by_key[key] = rule
        self._rules = by_key

    @classmethod
    def from_default_file(cls) -> PlausibilityRepository:
        return cls.from_file(get_settings().input_integrity_rules_path)

    @classmethod
    def from_file(cls, path: str | Path) -> PlausibilityRepository:
        config_path = Path(path)
        try:
            with config_path.open(encoding="utf-8") as handle:
                payload = json.load(handle)
        except FileNotFoundError as exc:
            raise InputIntegrityConfigurationError(
                f"missing input-integrity config: {config_path}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise InputIntegrityConfigurationError(
                f"invalid input-integrity JSON: {config_path}"
            ) from exc
        return cls.from_dict(payload)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> PlausibilityRepository:
        if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
            raise InputIntegrityConfigurationError("input-integrity config must contain a rules list")

        rules: list[InputIntegrityRule] = []
        for index, raw_rule in enumerate(payload["rules"]):
            if not isinstance(raw_rule, dict):
                raise InputIntegrityConfigurationError(f"rule {index} must be an object")
            missing = cls.REQUIRED_RULE_FIELDS - set(raw_rule)
            if missing:
                raise InputIntegrityConfigurationError(
                    f"rule {index} missing fields: {', '.join(sorted(missing))}"
                )
            if raw_rule["status"] != "ACTIVE":
                continue
            rules.append(cls._parse_active_rule(raw_rule, index=index))
        return cls(rules)

    @classmethod
    def _parse_active_rule(cls, raw: dict[str, Any], *, index: int) -> InputIntegrityRule:
        def required_text(field: str) -> str:
            value = raw.get(field)
            if not isinstance(value, str) or not value.strip():
                raise InputIntegrityConfigurationError(
                    f"active rule {index} requires non-empty {field}"
                )
            return value.strip()

        lower = cls._optional_decimal(raw.get("lower_bound"), index=index, field="lower_bound")
        upper = cls._optional_decimal(raw.get("upper_bound"), index=index, field="upper_bound")
        lower_operator = raw.get("lower_operator")
        upper_operator = raw.get("upper_operator")
        if lower is None and upper is None:
            raise InputIntegrityConfigurationError(f"active rule {index} has no bound")
        if lower is not None and lower_operator not in {">", ">="}:
            raise InputIntegrityConfigurationError(f"active rule {index} has invalid lower_operator")
        if lower is None and lower_operator is not None:
            raise InputIntegrityConfigurationError(f"active rule {index} has operator without lower_bound")
        if upper is not None and upper_operator not in {"<", "<="}:
            raise InputIntegrityConfigurationError(f"active rule {index} has invalid upper_operator")
        if upper is None and upper_operator is not None:
            raise InputIntegrityConfigurationError(f"active rule {index} has operator without upper_bound")
        if lower is not None and upper is not None and lower >= upper:
            raise InputIntegrityConfigurationError(f"active rule {index} has non-increasing bounds")

        return InputIntegrityRule(
            rule_id=required_text("rule_id"),
            analyte=required_text("analyte"),
            canonical_unit=ReferenceRepository.normalize_unit(required_text("canonical_unit")),
            lower_bound=lower,
            lower_operator=lower_operator,
            upper_bound=upper,
            upper_operator=upper_operator,
            source_id=required_text("source_id"),
            source=required_text("source"),
            source_section=required_text("source_section"),
            reason=required_text("reason"),
        )

    @staticmethod
    def _optional_decimal(value: Any, *, index: int, field: str) -> Decimal | None:
        if value is None:
            return None
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise InputIntegrityConfigurationError(
                f"active rule {index} has non-numeric {field}"
            ) from exc
        if not parsed.is_finite():
            raise InputIntegrityConfigurationError(f"active rule {index} has non-finite {field}")
        return parsed

    def get(self, analyte: str, canonical_unit: str) -> InputIntegrityRule | None:
        key = (
            analyte.strip().casefold(),
            ReferenceRepository.normalize_unit(canonical_unit).strip().casefold(),
        )
        return self._rules.get(key)


class InputIntegrityEvaluator:
    REVIEW_MESSAGE = (
        "Giá trị này cần được kiểm tra lại trước khi phân tích. "
        "Có thể đã có lỗi khi nhập giá trị hoặc đơn vị."
    )

    def __init__(self, repository: PlausibilityRepository):
        self.repository = repository

    def evaluate(self, *, analyte: str, value: Any, canonical_unit: str) -> InputIntegrityResult:
        observed = validate_numeric_measurement(value)
        normalized_unit = ReferenceRepository.normalize_unit(canonical_unit)
        rule = self.repository.get(analyte, normalized_unit)
        if rule is None:
            return InputIntegrityResult(
                status="VALID",
                reason_code=None,
                message="",
                rule_id=None,
                source_id=None,
                observed_value=observed,
                canonical_unit=normalized_unit,
            )

        outside = False
        if rule.lower_bound is not None:
            outside = outside or not self._compare(observed, rule.lower_bound, rule.lower_operator)
        if rule.upper_bound is not None:
            outside = outside or not self._compare(observed, rule.upper_bound, rule.upper_operator)

        return InputIntegrityResult(
            status="NEED_REVIEW" if outside else "VALID",
            reason_code="VALUE_OUTSIDE_VALIDATED_BOUND" if outside else None,
            message=self.REVIEW_MESSAGE if outside else "",
            rule_id=rule.rule_id,
            source_id=rule.source_id,
            observed_value=observed,
            canonical_unit=normalized_unit,
        )

    @staticmethod
    def _compare(value: Decimal, bound: Decimal, operator: str | None) -> bool:
        if operator not in _BOUND_OPERATORS:
            return False
        if operator == ">":
            return value > bound
        if operator == ">=":
            return value >= bound
        if operator == "<":
            return value < bound
        return value <= bound
