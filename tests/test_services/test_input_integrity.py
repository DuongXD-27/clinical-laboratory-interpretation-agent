from decimal import Decimal

import pytest

from src.services.input_integrity import (
    InputIntegrityConfigurationError,
    InputIntegrityEvaluator,
    PlausibilityRepository,
)


def _fixture_config(*, rules=None):
    return {"config_version": "test-only", "rules": rules or []}


def _fixture_rule(**overrides):
    # These numbers are deliberately test-engine fixtures, not medical data.
    rule = {
        "rule_id": "TEST-ONLY-POTASSIUM-BOUND",
        "analyte": "Potassium",
        "canonical_unit": "mmol/L",
        "lower_bound": 0,
        "lower_operator": ">=",
        "upper_bound": 10,
        "upper_operator": "<=",
        "source_id": "TEST-FIXTURE-NON-MEDICAL",
        "source": "Synthetic test fixture",
        "source_section": "test-only",
        "reason": "Exercise deterministic engine behavior only",
        "status": "ACTIVE",
    }
    rule.update(overrides)
    return rule


def test_value_inside_active_fixture_rule_is_valid():
    evaluator = InputIntegrityEvaluator(
        PlausibilityRepository.from_dict(_fixture_config(rules=[_fixture_rule()]))
    )

    result = evaluator.evaluate(analyte="Potassium", value=5, canonical_unit="mmol/L")

    assert result.status == "VALID"
    assert result.rule_id == "TEST-ONLY-POTASSIUM-BOUND"
    assert result.observed_value == Decimal("5")


def test_value_outside_active_fixture_rule_needs_review_without_correction():
    evaluator = InputIntegrityEvaluator(
        PlausibilityRepository.from_dict(_fixture_config(rules=[_fixture_rule()]))
    )

    result = evaluator.evaluate(analyte="Potassium", value=500, canonical_unit="mmol/L")

    assert result.status == "NEED_REVIEW"
    assert result.reason_code == "VALUE_OUTSIDE_VALIDATED_BOUND"
    assert result.observed_value == Decimal("500")
    assert "kiểm tra lại" in result.message


def test_analyte_without_active_rule_remains_backward_compatible():
    evaluator = InputIntegrityEvaluator(PlausibilityRepository.from_dict(_fixture_config()))

    result = evaluator.evaluate(
        analyte="Fasting plasma glucose",
        value=83,
        canonical_unit="mmol/L",
    )

    assert result.status == "VALID"
    assert result.rule_id is None
    assert result.observed_value == Decimal("83")


def test_active_rule_requires_complete_source_provenance():
    rule = _fixture_rule(source="")

    with pytest.raises(InputIntegrityConfigurationError, match="source"):
        PlausibilityRepository.from_dict(_fixture_config(rules=[rule]))


def test_inactive_rule_is_not_executable():
    rule = _fixture_rule(status="BLOCKED_BY_MEDICAL_DATA_AUTHORITY")
    evaluator = InputIntegrityEvaluator(
        PlausibilityRepository.from_dict(_fixture_config(rules=[rule]))
    )

    result = evaluator.evaluate(analyte="Potassium", value=500, canonical_unit="mmol/L")

    assert result.status == "VALID"
    assert result.rule_id is None


def test_production_registry_has_no_unapproved_active_bounds():
    repository = PlausibilityRepository.from_default_file()
    evaluator = InputIntegrityEvaluator(repository)

    potassium = evaluator.evaluate(analyte="Potassium", value=500, canonical_unit="mmol/L")
    glucose = evaluator.evaluate(
        analyte="Fasting plasma glucose",
        value=83,
        canonical_unit="mmol/L",
    )

    assert potassium.status == "VALID" and potassium.rule_id is None
    assert glucose.status == "VALID" and glucose.rule_id is None
