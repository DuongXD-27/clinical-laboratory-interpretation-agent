"""Tests for VMEC-05 Conversational Independence & Autonomous Context Retrieval."""

import time
from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT, LabReport
from src.models.orchestrator_schemas import (
    ConversationState,
    IntentEnum,
    OrchestratorRequest,
    ResponseStatus,
    UIContext,
)
from src.models.schemas import (
    IndicatorResultSchema,
    LabReportDetailSchema,
    LabReportSummarySchema,
    TrendPointResponse,
    TrendResponse,
)
from src.orchestrator.service import handle_message
from src.orchestrator.session_store import default_session_store
from src.services import history_repository, trend_service


class DummyPatientUser:
    def __init__(self, user_id=101, username="patient_jane", role=ROLE_PATIENT):
        self.user_id = user_id
        self.username = username
        self.role = role


def _mock_report_detail(report_id=42, patient_id=101):
    return LabReportDetailSchema(
        id=report_id,
        patient_id=patient_id,
        patient_name="Jane Doe",
        test_date=date(2026, 3, 15),
        created_at=datetime(2026, 3, 15, 10, 0, 0),
        status="normal",
        summary="Xét nghiệm định kỳ",
        has_critical_values=False,
        verification_status="verified",
        reviewed_by_doctor=True,
        doctor_note=None,
        language="vi",
        guardrail_passed=True,
        disclaimer="Thông tin mang tính tham khảo y khoa.",
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=6.5,
                unit="10^9/L",
                reference_range="4.0 - 10.0",
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation="Bạch cầu trong giới hạn bình thường.",
                analyte_canonical="WBC",
                analyte_raw="WBC",
                canonical_unit="10^9/L",
                sources=["Bộ Y Tế"],
            ),
            IndicatorResultSchema(
                name="Glucose",
                value=5.2,
                unit="mmol/L",
                reference_range="4.1 - 6.1",
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation="Đường huyết lúc đói bình thường.",
                analyte_canonical="Fasting plasma glucose",
                analyte_raw="Glucose",
                canonical_unit="mmol/L",
                sources=["Bộ Y Tế"],
            ),
        ],
        critical_alerts=[],
    )


@pytest.mark.asyncio
async def test_latest_report_fetch_without_ui_context(monkeypatch):
    """
    Patient asks to explain a specific analyte (WBC) without selecting any report
    in UI (e.g. opens chat from home/dashboard). The system should autonomously
    fetch the patient's latest report from DB.
    """
    user = DummyPatientUser()
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    mock_db = MagicMock()
    mock_db.scalar.return_value = user.user_id

    # Mock list_reports to return latest report id=42
    report_summary = LabReportSummarySchema(
        id=42,
        test_date=date(2026, 3, 15),
        created_at=datetime(2026, 3, 15, 10, 0, 0),
        status="normal",
        summary="Xét nghiệm định kỳ",
        has_critical_values=False,
        reviewed_by_doctor=True,
        indicator_count=2,
        verification_status="verified",
    )
    monkeypatch.setattr(history_repository, "list_reports", lambda db, patient_id, **kw: (1, [report_summary]))

    # Mock get_report and to_detail
    mock_lab_report = LabReport(id=42, patient_id=user.user_id, test_date=date(2026, 3, 15))
    monkeypatch.setattr(history_repository, "get_report", lambda db, rep_id: mock_lab_report)
    monkeypatch.setattr(history_repository, "to_detail", lambda rep: _mock_report_detail(42, user.user_id))

    req = OrchestratorRequest(
        message="Giải thích chỉ số WBC của tôi",
        client_request_id="indep-001",
        ui_context=None,  # No UI Context!
    )
    resp = await handle_message(req, current_user=user, db=mock_db)

    assert resp.status == ResponseStatus.SUCCESS
    assert resp.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert "bạch cầu" in resp.message.lower() or "wbc" in resp.message.lower()


@pytest.mark.asyncio
async def test_dashboard_chat_flow(monkeypatch):
    """
    Patient on dashboard asks for doctor questions without page context.
    Orchestrator must autonomously fetch latest report and generate questions.
    """
    user = DummyPatientUser()
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    mock_db = MagicMock()
    mock_db.scalar.return_value = user.user_id

    report_summary = LabReportSummarySchema(
        id=42,
        test_date=date(2026, 3, 15),
        created_at=datetime(2026, 3, 15, 10, 0, 0),
        status="normal",
        summary="Xét nghiệm",
        has_critical_values=False,
        reviewed_by_doctor=True,
        indicator_count=2,
        verification_status="verified",
    )
    monkeypatch.setattr(history_repository, "list_reports", lambda db, patient_id, **kw: (1, [report_summary]))
    mock_lab_report = LabReport(id=42, patient_id=user.user_id, test_date=date(2026, 3, 15))
    monkeypatch.setattr(history_repository, "get_report", lambda db, rep_id: mock_lab_report)
    monkeypatch.setattr(history_repository, "to_detail", lambda rep: _mock_report_detail(42, user.user_id))

    req = OrchestratorRequest(
        message="Gợi ý câu hỏi cho bác sĩ",
        client_request_id="indep-002",
        ui_context=UIContext(candidate_report_ref=None, candidate_analyte=None),
    )
    resp = await handle_message(req, current_user=user, db=mock_db)

    assert resp.status == ResponseStatus.SUCCESS
    assert resp.intent == IntentEnum.GET_DOCTOR_QUESTIONS
    assert resp.data is not None


@pytest.mark.asyncio
async def test_trend_request_without_page_navigation(monkeypatch):
    """
    Patient asks for trend of Glucose from any screen.
    Trend service should be called with extracted analyte directly.
    """
    user = DummyPatientUser()
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    mock_db = MagicMock()

    mock_trend = TrendResponse(
        analyte_canonical="Fasting plasma glucose",
        display_name="Glucose máu lúc đói",
        canonical_unit="mmol/L",
        filter="latest5",
        result_count=2,
        trend_available=True,
        points=[
            TrendPointResponse(report_id=1, test_date=date(2026, 1, 10), value=5.1, assessment="normal"),
            TrendPointResponse(report_id=42, test_date=date(2026, 3, 15), value=5.2, assessment="normal"),
        ],
    )
    monkeypatch.setattr(trend_service, "get_patient_trend", lambda *a, **kw: mock_trend)

    req = OrchestratorRequest(
        message="Chỉ số Glucose của tôi thay đổi thế nào?",
        client_request_id="indep-003",
        ui_context=None,
    )
    resp = await handle_message(req, current_user=user, db=mock_db)

    assert resp.status == ResponseStatus.SUCCESS
    assert resp.intent == IntentEnum.ANALYZE_TREND


@pytest.mark.asyncio
async def test_stale_pending_question_expiration(monkeypatch):
    """
    Verify TTL expiration of pending_question in ConversationState.
    When expired, follow-up resolution should NOT hijack unrelated messages.
    """
    user = DummyPatientUser()
    session = default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    mock_db = MagicMock()

    # Simulate pending question asked 400 seconds ago (TTL is 300s)
    old_timestamp = time.time() - 400.0
    state = ConversationState(
        pending_question="Bạn muốn xem chỉ số nào?",
        pending_question_timestamp=old_timestamp,
        ttl_seconds=300.0,
    )
    assert state.is_expired() is True
    assert state.get_active_pending_question() is None

    default_session_store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        conversation_state=state,
    )

    # Now user sends a general greeting "Xin chào"
    req = OrchestratorRequest(message="Xin chào", client_request_id="indep-004")
    resp = await handle_message(req, current_user=user, db=mock_db)

    # Must route to SAFE_GENERAL, not try to answer the old expired EXPLAIN_CURRENT_RESULT question
    assert resp.intent == IntentEnum.SAFE_GENERAL
    assert resp.status == ResponseStatus.SUCCESS


@pytest.mark.asyncio
async def test_knowledge_only_does_not_fetch_report(monkeypatch):
    """
    General / knowledge questions must NEVER trigger autonomous report fetching.
    """
    user = DummyPatientUser()
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    mock_db = MagicMock()
    list_reports_called = False

    def _mock_list_reports(*args, **kwargs):
        nonlocal list_reports_called
        list_reports_called = True
        return (0, [])

    monkeypatch.setattr(history_repository, "list_reports", _mock_list_reports)

    req = OrchestratorRequest(message="Bạn có thể giúp tôi làm gì?", client_request_id="indep-005")
    resp = await handle_message(req, current_user=user, db=mock_db)

    assert resp.intent == IntentEnum.SAFE_GENERAL
    assert resp.status == ResponseStatus.SUCCESS
    assert list_reports_called is False
