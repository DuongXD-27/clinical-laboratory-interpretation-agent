"""Regression tests for VMEC-05 ORCH-V1.3.1.

Validates:
- Fix A: Whole-report vs new-ingestion routing disambiguation (TEST-A1..A4)
- Fix B: Explicit whole-report request clearing stale analyte focus (TEST-B1..B3)
- Fix C: Treatment safety gate precision and false-positive prevention (TEST-C1..C4)
"""

import pytest
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
)
from src.orchestrator.gates import medical_safety_gate
from src.orchestrator.intent_router import route_intent
from src.orchestrator.medical_context import resolve_medical_context


@pytest.mark.asyncio
async def test_c1_creatinine_trend_not_treatment():
    """TEST-C1: 'Creatinine của em có xu hướng gì?' must NOT classify TREATMENT_REQUEST."""
    msg = "Creatinine của em có xu hướng gì?"
    gate_res = medical_safety_gate(msg)
    assert gate_res != ReasonCode.TREATMENT_REQUEST
    assert gate_res is None


@pytest.mark.asyncio
async def test_c2_wbc_trend_not_treatment():
    """TEST-C2: 'WBC có xu hướng tăng không?' must NOT classify TREATMENT_REQUEST."""
    msg = "WBC có xu hướng tăng không?"
    gate_res = medical_safety_gate(msg)
    assert gate_res != ReasonCode.TREATMENT_REQUEST
    assert gate_res is None


@pytest.mark.asyncio
async def test_c3_explicit_medicine_is_treatment():
    """TEST-C3: 'Em nên uống thuốc gì?' MUST classify TREATMENT_REQUEST."""
    msg = "Em nên uống thuốc gì?"
    gate_res = medical_safety_gate(msg)
    assert gate_res == ReasonCode.TREATMENT_REQUEST


@pytest.mark.asyncio
async def test_c4_lower_indicator_medicine_is_treatment():
    """TEST-C4: 'HbA1c cao thì uống gì để giảm?' MUST classify TREATMENT_REQUEST."""
    msg = "HbA1c cao thì uống gì để giảm?"
    gate_res = medical_safety_gate(msg)
    assert gate_res == ReasonCode.TREATMENT_REQUEST


@pytest.mark.asyncio
async def test_a1_phieu_nay_the_nao_routes_explain_current():
    """TEST-A1: 'Phiếu này thế nào?' without active ingestion routes to EXPLAIN_CURRENT_RESULT."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    route = await route_intent(
        message="Phiếu này thế nào?",
        session=session,
        role="patient",
        has_medical_context=True,
    )
    assert route.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_a2_dang_chu_y_trong_phieu_nay_routes_explain_current():
    """TEST-A2: 'Có gì đáng chú ý trong phiếu này?' routes to EXPLAIN_CURRENT_RESULT."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    route = await route_intent(
        message="Có gì đáng chú ý trong phiếu này?",
        session=session,
        role="patient",
        has_medical_context=True,
    )
    assert route.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_a3_tom_tat_phieu_nay_routes_explain_current():
    """TEST-A3: 'Tóm tắt phiếu này cho em' routes to EXPLAIN_CURRENT_RESULT."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    route = await route_intent(
        message="Tóm tắt phiếu này cho em",
        session=session,
        role="patient",
        has_medical_context=True,
    )
    assert route.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_a4_active_ingestion_preservation():
    """TEST-A4: 'Phân tích phiếu này' or active OCR context preserves ANALYZE_REPORT."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    route = await route_intent(
        message="Phân tích phiếu này",
        session=session,
        role="patient",
        has_medical_context=True,
    )
    assert route.intent == IntentEnum.ANALYZE_REPORT

    # Active pending OCR review also preserves ANALYZE_REPORT
    session_ocr = OrchestratorSessionContext.from_server(
        session_id="s2",
        user_role="patient",
        pending_ocr_review=True,
    )
    route_ocr = await route_intent(
        message="Phiếu này thế nào?",
        session=session_ocr,
        role="patient",
        has_medical_context=True,
    )
    assert route_ocr.intent == IntentEnum.ANALYZE_REPORT


def test_b1_explicit_whole_report_clears_stale_analyte():
    """TEST-B1: Turn 1 WBC -> Turn 2 'Nhìn chung cả phiếu của em thì sao?' clears current_analyte."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    session.current_analyte = "WBC"
    session.current_report_ref = "101"

    resolved = resolve_medical_context(
        message="Nhìn chung cả phiếu của em thì sao?",
        session=session,
        ui_context=None,
        current_user=None,
        db=None,
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )
    assert resolved.current_analyte is None
    assert resolved.current_report_ref == "101"


def test_b2_explicit_analyte_overrides_session():
    """TEST-B2: Turn 1 WBC -> Turn 2 'Còn HbA1c?' sets current_analyte to HbA1c."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    session.current_analyte = "WBC"
    session.current_report_ref = "101"

    resolved = resolve_medical_context(
        message="Còn HbA1c thì sao?",
        session=session,
        ui_context=None,
        current_user=None,
        db=None,
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )
    assert resolved.current_analyte == "HbA1c"


def test_b3_referential_analyte_preserves_session_analyte():
    """TEST-B3: Turn 1 WBC -> Turn 2 'Chỉ số này dạo này thay đổi thế nào?' preserves WBC."""
    session = OrchestratorSessionContext(session_id="s1", user_role="patient")
    session.current_analyte = "WBC"
    session.current_report_ref = "101"

    resolved = resolve_medical_context(
        message="Chỉ số này dạo này thay đổi thế nào?",
        session=session,
        ui_context=None,
        current_user=None,
        db=None,
        intent=IntentEnum.ANALYZE_TREND,
    )
    assert resolved.current_analyte == "WBC"
