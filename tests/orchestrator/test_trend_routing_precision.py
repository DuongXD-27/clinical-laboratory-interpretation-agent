"""Regression coverage for ORCH-V1.4A1R2 Trend routing precision."""

from __future__ import annotations

import pytest

from src.models.orchestrator_schemas import IntentEnum, ReasonCode
from src.orchestrator.gates import medical_safety_gate
from src.orchestrator.intent_router import _deterministic_route, contains_lab_value


@pytest.mark.parametrize(
    ("case_id", "message"),
    (
        ("R2-T01", "HbA1c của em thời gian gần đây ra sao?"),
        ("R2-T02", "HbA1c của em dạo này thay đổi ra sao?"),
        ("R2-T03", "WBC dạo này thay đổi thế nào?"),
        ("R2-T04", "Creatinine của em có xu hướng gì?"),
        ("R2-T05", "HbA1c gần đây tăng hay giảm?"),
        ("R2-T06", "HbA1c qua các lần xét nghiệm thay đổi ra sao?"),
    ),
)
def test_r2_trend_requests_route_deterministically(case_id: str, message: str) -> None:
    route = _deterministic_route(message, has_medical_context=True)

    assert route is not None, case_id
    assert route.intent == IntentEnum.ANALYZE_TREND, case_id


@pytest.mark.parametrize(
    ("case_id", "message"),
    (
        ("R2-C01", "HbA1c của em hiện tại là bao nhiêu?"),
        ("R2-C02", "HbA1c gần nhất của em là bao nhiêu?"),
        ("R2-C03", "Giải thích HbA1c của em"),
        ("R2-C04", "HbA1c 6.8% có cao không?"),
    ),
)
def test_r2_current_result_controls_do_not_route_to_trend(case_id: str, message: str) -> None:
    route = _deterministic_route(message, has_medical_context=True)

    assert route is not None, case_id
    assert route.intent == IntentEnum.EXPLAIN_CURRENT_RESULT, case_id


@pytest.mark.parametrize(
    ("case_id", "message", "expected"),
    (
        ("R2-N01", "HbA1c", False),
        ("R2-N02", "HbA1c của em", False),
        ("R2-N03", "HbA1c 6.8%", True),
        ("R2-N04", "WBC 12.3 G/L", True),
        ("R2-N05", "Creatinine = 95", True),
        ("R2-N06", "6.1 mmol/L", True),
        ("R2-N07", "đường huyết 7.2", True),
    ),
)
def test_r2_numeric_value_detection(
    case_id: str,
    message: str,
    expected: bool,
) -> None:
    assert contains_lab_value(message) is expected, case_id


@pytest.mark.parametrize(
    "analyte_or_alias",
    (
        "HbA1c",
    ),
)
def test_r2_approved_analyte_names_with_digits_are_not_values(analyte_or_alias: str) -> None:
    assert contains_lab_value(analyte_or_alias) is False


@pytest.mark.parametrize(
    "identifier",
    (
        "HbA1c",
        "vitamin B12",
        "LDL-C",
        "HDL-C",
    ),
)
def test_r2_digits_or_hyphens_inside_identifiers_are_not_values(identifier: str) -> None:
    assert contains_lab_value(identifier) is False


def test_r2_p01_explicit_value_cannot_override_strong_trend_semantics() -> None:
    route = _deterministic_route(
        "HbA1c 6.8%, dạo này có xu hướng tăng không?",
        has_medical_context=True,
    )

    assert route is not None
    assert route.intent == IntentEnum.ANALYZE_TREND


@pytest.mark.parametrize(
    ("message", "expected_reason"),
    (
        ("Creatinine tăng thì em nên uống thuốc gì?", ReasonCode.TREATMENT_REQUEST),
        ("HbA1c cao vậy em bị tiểu đường đúng không?", ReasonCode.MEDICAL_DIAGNOSIS_REQUEST),
    ),
)
def test_r2_safety_remains_authoritative(message: str, expected_reason: ReasonCode) -> None:
    assert medical_safety_gate(message) == expected_reason


def test_r2_explicit_new_report_ingestion_remains_analyze_report() -> None:
    route = _deterministic_route("Phân tích phiếu này", has_medical_context=True)

    assert route is not None
    assert route.intent == IntentEnum.ANALYZE_REPORT
