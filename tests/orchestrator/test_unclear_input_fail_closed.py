"""Tests for VMEC-05 CHAT-V1.5-001: Unclear Input Fail-Closed.

Validates that unclear/nonsense user input fails closed to UNKNOWN_INTENT
with a fixed neutral clarification message, rather than falling through to
cached patient reports/analytes.
"""

from datetime import date, datetime
from types import SimpleNamespace

import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    DataType,
    IntentEnum,
    OrchestratorRequest,
    ReasonCode,
    ResponseStatus,
)
from src.models.schemas import (
    IndicatorResultSchema,
    LabReportDetailSchema,
    LabReportSummarySchema,
)
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository


def _patient(user_id: int = 801) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, role=ROLE_PATIENT, username=f"patient_{user_id}")


def _make_detail(patient_id: int = 801, report_id: int = 101) -> LabReportDetailSchema:
    return LabReportDetailSchema(
        id=report_id,
        patient_id=patient_id,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        status="normal",
        summary="Xét nghiệm máu tổng quát",
        has_critical_values=False,
        verification_status="verified",
        reviewed_by_doctor=True,
        language="vi",
        guardrail_passed=True,
        disclaimer="Tham khảo y khoa",
        critical_alerts=[],
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=14.5,
                unit="G/L",
                analyte_canonical="WBC",
                reference_low=4.0,
                reference_high=10.0,
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation="Bạch cầu tăng nhẹ so với khoảng tham chiếu.",
                sources=["REF-01"],
            ),
            IndicatorResultSchema(
                name="Creatinine",
                value=85.0,
                unit="umol/L",
                analyte_canonical="Creatinine",
                reference_low=70.0,
                reference_high=115.0,
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation="Chỉ số Creatinine bình thường.",
                sources=["REF-01"],
            ),
        ],
    )


def _report(patient_id: int, report_id: int = 101) -> SimpleNamespace:
    return SimpleNamespace(
        id=report_id,
        patient_id=patient_id,
        test_date=date(2026, 8, 15),
        created_at=date(2026, 8, 15),
    )


class QuerySpyDb:
    def __init__(self, patient_id: int = 801):
        self.queries = []
        self.patient_id = patient_id

    def execute(self, *args, **kwargs):
        self.queries.append((args, kwargs))
        return self

    def scalar(self, *args, **kwargs):
        return self.patient_id


UNCLEAR_RESPONSE_TEXT = "Tôi chưa hiểu yêu cầu của bạn. Bạn vui lòng nhập lại hoặc mô tả rõ hơn điều bạn muốn hỏi."


@pytest.mark.asyncio
async def test_u01_asdfgh_returns_clarification():
    """U-01: 'asdfgh' -> clarification fail-closed."""
    user = _patient()
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="asdfgh"),
        current_user=user,
        db=QuerySpyDb(),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.reason_code == ReasonCode.UNKNOWN_INTENT
    assert response.message == UNCLEAR_RESPONSE_TEXT
    assert response.data_type == DataType.BLOCKED


@pytest.mark.asyncio
async def test_u02_question_marks_returns_clarification():
    """U-02: '???' -> clarification fail-closed."""
    user = _patient()
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="???"),
        current_user=user,
        db=QuerySpyDb(),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.reason_code == ReasonCode.UNKNOWN_INTENT
    assert response.message == UNCLEAR_RESPONSE_TEXT


@pytest.mark.asyncio
async def test_u03_numbers_and_letters_returns_clarification():
    """U-03: '123 abc' -> clarification fail-closed."""
    user = _patient()
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="123 abc"),
        current_user=user,
        db=QuerySpyDb(),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.reason_code == ReasonCode.UNKNOWN_INTENT
    assert response.message == UNCLEAR_RESPONSE_TEXT


@pytest.mark.asyncio
async def test_u04_active_wbc_context_with_blah_blah_returns_clarification_not_wbc(monkeypatch):
    """U-04: Patient has active WBC context + 'blah blah' -> clarification, NOT WBC explanation."""
    user = _patient(804)
    report = _report(user.user_id)
    detail = _make_detail(user.user_id)
    monkeypatch.setattr(history_repository, "get_report", lambda db, r_id: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    session = store.get_or_create(user)
    store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_report_ref="101",
        current_analyte="WBC",
    )
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="blah blah"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.BLOCKED
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.reason_code == ReasonCode.UNKNOWN_INTENT
    assert response.message == UNCLEAR_RESPONSE_TEXT
    # Must NOT contain medical explanation of WBC
    assert "WBC" not in response.message
    assert "14.5" not in response.message


@pytest.mark.asyncio
async def test_u05_active_report_with_nonsense_returns_clarification_not_summary(monkeypatch):
    """U-05: Patient has active report + nonsense input ('ơ kìa') -> clarification, NOT whole-report summary."""
    user = _patient(805)
    report = _report(user.user_id)
    detail = _make_detail(user.user_id)
    summary_item = LabReportSummarySchema(
        id=101,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        has_critical_values=False,
        summary="Xét nghiệm máu tổng quát",
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, r_id: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)
    monkeypatch.setattr(history_repository, "list_reports", lambda db, **kw: (1, [summary_item]))

    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    session = store.get_or_create(user)
    store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_report_ref="101",
    )
    runtime = OrchestratorRuntime(session_store=store)

    for nonsense in ["ơ kìa", "test test test", "abc xyz"]:
        response = await handle_message(
            OrchestratorRequest(message=nonsense),
            current_user=user,
            db=QuerySpyDb(user.user_id),
            runtime=runtime,
        )

        assert response.status == ResponseStatus.BLOCKED
        assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
        assert response.reason_code == ReasonCode.UNKNOWN_INTENT
        assert response.message == UNCLEAR_RESPONSE_TEXT
        assert "tổng hợp kết quả" not in response.message.lower()


@pytest.mark.asyncio
async def test_u06_referential_with_valid_active_wbc_returns_wbc_explanation(monkeypatch):
    """U-06: 'chỉ số này' with valid active WBC -> WBC explanation."""
    user = _patient(806)
    report = _report(user.user_id)
    detail = _make_detail(user.user_id)
    monkeypatch.setattr(history_repository, "get_report", lambda db, r_id: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    session = store.get_or_create(user)
    store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_report_ref="101",
        current_analyte="WBC",
    )
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="chỉ số này"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.SUCCESS
    assert response.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert response.data_type == DataType.EXPLANATION


@pytest.mark.asyncio
async def test_u07_referential_without_referent_returns_clarification():
    """U-07: 'chỉ số này' without referent -> clarification (AMBIGUOUS_CONTEXT)."""
    user = _patient(807)
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="chỉ số này"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.NEEDS_INPUT
    assert response.reason_code == ReasonCode.AMBIGUOUS_CONTEXT
    assert "chỉ số nào" in response.message.lower()


@pytest.mark.asyncio
async def test_u08_explicit_analyte_not_unclear(monkeypatch):
    """U-08: 'WBC' and 'Creatinine' -> supported analyte behavior, NOT unclear."""
    user = _patient(808)
    report = _report(user.user_id)
    detail = _make_detail(user.user_id)
    summary_item = LabReportSummarySchema(
        id=101,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        has_critical_values=False,
        summary="Xét nghiệm máu tổng quát",
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, r_id: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)
    monkeypatch.setattr(history_repository, "list_reports", lambda db, **kw: (1, [summary_item]))

    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    # Test WBC
    response_wbc = await handle_message(
        OrchestratorRequest(message="WBC"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )
    assert response_wbc.status == ResponseStatus.SUCCESS
    assert response_wbc.intent == IntentEnum.EXPLAIN_CURRENT_RESULT

    # Test Creatinine
    response_cr = await handle_message(
        OrchestratorRequest(message="Creatinine"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )
    assert response_cr.status == ResponseStatus.SUCCESS
    assert response_cr.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_u09_latest_report_query_supported(monkeypatch):
    """U-09: 'phiếu gần nhất' -> supported report behavior."""
    user = _patient(809)
    report = _report(user.user_id)
    detail = _make_detail(user.user_id)
    summary_item = LabReportSummarySchema(
        id=101,
        test_date=date(2026, 8, 15),
        created_at=datetime(2026, 8, 15, 10, 0, 0),
        has_critical_values=False,
        summary="Xét nghiệm máu tổng quát",
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, r_id: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)
    monkeypatch.setattr(history_repository, "list_reports", lambda db, **kw: (1, [summary_item]))

    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    response = await handle_message(
        OrchestratorRequest(message="phiếu gần nhất"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )

    assert response.status == ResponseStatus.SUCCESS
    assert response.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_u10_trend_request_unchanged(monkeypatch):
    """U-10: 'HbA1c dạo này thay đổi ra sao?' -> ANALYZE_TREND unchanged."""
    user = _patient(810)
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    runtime = OrchestratorRuntime(session_store=store)

    # Note: If patient has no trend data, it still routes to ANALYZE_TREND and returns TREND_INSUFFICIENT_POINTS
    response = await handle_message(
        OrchestratorRequest(message="HbA1c dạo này thay đổi ra sao?"),
        current_user=user,
        db=QuerySpyDb(user.user_id),
        runtime=runtime,
    )

    assert response.intent == IntentEnum.ANALYZE_TREND
    # Reason code should be trend insufficient points or success, but NOT UNKNOWN_INTENT
    assert response.reason_code != ReasonCode.UNKNOWN_INTENT
