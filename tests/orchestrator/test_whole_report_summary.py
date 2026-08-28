"""Tests for VMEC-05 ORCH-V1.3 Whole-Report Summary & Autonomous Fulfillment."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    OrchestratorRequest,
    ReasonCode,
    ResponseStatus,
    UIContext,
)
from src.models.schemas import (
    CriticalAlertSchema,
    IndicatorResultSchema,
    LabReportDetailSchema,
    LabReportSummarySchema,
    TrendPointResponse,
    TrendResponse,
)
from src.orchestrator.dispatcher import DispatchContext, dispatch_workflow
from src.orchestrator.response_composer import _format_whole_report_deterministic_summary
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository, trend_service
from src.services.auth import ROLE_GUEST


class DummyPatient:
    def __init__(self, user_id=101, username="test_patient", role=ROLE_PATIENT):
        self.user_id = user_id
        self.username = username
        self.role = role


class DummyGuest:
    def __init__(self, session_id="guest_session_123", username="guest_user", role=ROLE_GUEST):
        self.session_id = session_id
        self.username = username
        self.role = role


def _runtime_with_ack(user: object) -> OrchestratorRuntime:
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    return OrchestratorRuntime(session_store=store)


def _make_sample_report_detail(report_id=42, patient_id=101):
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
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=12.5,
                unit="G/L",
                analyte_canonical="WBC",
                reference_low=4.0,
                reference_high=10.0,
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation="Bạch cầu tăng nhẹ so với khoảng tham chiếu.",
                sources=["HD-BYT"],
            ),
            IndicatorResultSchema(
                name="RBC",
                value=3.2,
                unit="T/L",
                analyte_canonical="RBC",
                reference_low=3.8,
                reference_high=5.5,
                status="low",
                is_abnormal=True,
                is_critical=False,
                explanation="Hồng cầu giảm nhẹ.",
                sources=["HD-BYT"],
            ),
            IndicatorResultSchema(
                name="Glucose",
                value=5.2,
                unit="mmol/L",
                analyte_canonical="Fasting plasma glucose",
                reference_low=3.9,
                reference_high=6.4,
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation="Đường huyết bình thường.",
                sources=[],
            ),
            IndicatorResultSchema(
                name="UnknownMarker",
                value=15.0,
                unit="U/L",
                analyte_canonical=None,
                reference_low=None,
                reference_high=None,
                status="unknown",
                is_abnormal=False,
                is_critical=False,
                explanation="Chỉ số chưa xác định.",
                sources=[],
            ),
        ],
        critical_alerts=[],
    )


# TEST-01: Whole report with HIGH + LOW + NORMAL
@pytest.mark.asyncio
async def test_01_whole_report_high_low_normal(monkeypatch):
    detail = _make_sample_report_detail()
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    context = DispatchContext(
        current_user=DummyPatient(),
        db=mock_db,
        current_report_ref="42",
        current_analyte=None,
    )
    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, context)
    assert result.status == ResponseStatus.SUCCESS
    assert isinstance(result.data, AnalysisDataPayload)
    assert len(result.data.indicators) == 4

    summary_text = _format_whole_report_deterministic_summary(result.data)
    assert "WBC" in summary_text
    assert "RBC" in summary_text
    assert "CAO" in summary_text
    assert "THẤP" in summary_text
    assert "1 chỉ số nằm trong khoảng tham chiếu" in summary_text
    assert "UnknownMarker" in summary_text


# TEST-02: Critical + HIGH/LOW
@pytest.mark.asyncio
async def test_02_critical_prioritization_and_no_duplication(monkeypatch):
    detail = _make_sample_report_detail()
    detail.has_critical_values = True
    detail.critical_alerts = [
        CriticalAlertSchema(
            indicator_name="Potassium",
            value=6.8,
            unit="mmol/L",
            message="Giá trị Kali máu tăng cao nguy kịch.",
        )
    ]
    detail.indicators.insert(
        0,
        IndicatorResultSchema(
            name="Potassium",
            value=6.8,
            unit="mmol/L",
            analyte_canonical="Potassium",
            reference_low=3.5,
            reference_high=5.0,
            status="critical_high",
            is_abnormal=True,
            is_critical=True,
            critical_status="critical_high",
            explanation="Kali máu cao nguy hiểm.",
            sources=[],
        ),
    )
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    context = DispatchContext(
        current_user=DummyPatient(),
        db=mock_db,
        current_report_ref="42",
        current_analyte=None,
    )
    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, context)
    summary_text = _format_whole_report_deterministic_summary(result.data)

    # Critical appears in critical section
    assert "CHỈ SỐ NGUY KỊCH" in summary_text
    assert "Potassium: 6.8 mmol/L" in summary_text
    # Critical item is not duplicated in ordinary High/Low section
    abnormal_section = summary_text.split("Các chỉ số nằm ngoài khoảng tham chiếu:")[1].split(
        "Các chỉ số chưa xác định"
    )[0]
    assert "Potassium" not in abnormal_section
    assert "WBC" in abnormal_section


# TEST-03: UNKNOWN is strictly isolated, never NORMAL
def test_03_unknown_is_isolated():
    payload = AnalysisDataPayload(
        indicators=[
            IndicatorResultSchema(
                name="SpecialMarker",
                value=99.0,
                unit="U/mL",
                status="unknown",
                is_abnormal=False,
                is_critical=False,
            )
        ]
    )
    summary_text = _format_whole_report_deterministic_summary(payload)
    assert "chưa xác định khoảng tham chiếu" in summary_text
    assert "SpecialMarker" in summary_text
    assert "trong khoảng tham chiếu thông thường" not in summary_text


# TEST-04: All normal report
def test_04_all_normal_report():
    payload = AnalysisDataPayload(
        indicators=[
            IndicatorResultSchema(
                name="Glucose",
                value=5.0,
                unit="mmol/L",
                reference_low=3.9,
                reference_high=6.4,
                status="normal",
                is_abnormal=False,
                is_critical=False,
            ),
            IndicatorResultSchema(
                name="WBC",
                value=6.0,
                unit="G/L",
                reference_low=4.0,
                reference_high=10.0,
                status="normal",
                is_abnormal=False,
                is_critical=False,
            ),
        ]
    )
    summary_text = _format_whole_report_deterministic_summary(payload)
    assert "Tất cả các chỉ số xét nghiệm đã phân tích đều nằm trong khoảng tham chiếu thông thường." in summary_text
    assert "bệnh" not in summary_text
    assert "khỏe mạnh" not in summary_text


# TEST-05: Single analyte regression
@pytest.mark.asyncio
async def test_05_single_analyte_regression(monkeypatch):
    detail = _make_sample_report_detail()
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    context = DispatchContext(
        current_user=DummyPatient(),
        db=mock_db,
        current_report_ref="42",
        current_analyte="WBC",
    )
    result = await dispatch_workflow(IntentEnum.EXPLAIN_CURRENT_RESULT, context)
    assert result.status == ResponseStatus.SUCCESS
    assert isinstance(result.data, ExplanationDataPayload)
    assert "Bạch cầu tăng nhẹ" in result.data.explanation


# TEST-06: Whole-report vague query with no UIContext
@pytest.mark.asyncio
async def test_06_whole_report_vague_query_no_uicontext(monkeypatch):
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    detail = _make_sample_report_detail()

    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(
        history_repository,
        "list_reports",
        lambda db, **kwargs: (
            1,
            [
                LabReportSummarySchema(
                    id=42,
                    test_date=date(2026, 8, 15),
                    created_at=datetime(2026, 8, 15, 10, 0, 0),
                    has_critical_values=False,
                    summary="",
                )
            ],
        ),
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    req = OrchestratorRequest(message="Kết quả gần nhất của em có gì cần chú ý không?", ui_context=None)
    resp = await handle_message(req, current_user=patient, db=mock_db, runtime=runtime)

    assert resp.status == ResponseStatus.SUCCESS
    assert resp.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert resp.data_type == DataType.ANALYSIS
    assert resp.reason_code is None
    assert "WBC" in resp.message or "bạch cầu" in resp.message.lower() or "kết quả" in resp.message.lower()


# TEST-07: Abnormal summary wording
@pytest.mark.asyncio
async def test_07_abnormal_summary_wording(monkeypatch):
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    detail = _make_sample_report_detail()

    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(
        history_repository,
        "list_reports",
        lambda db, **kwargs: (
            1,
            [
                LabReportSummarySchema(
                    id=42,
                    test_date=date(2026, 8, 15),
                    created_at=datetime(2026, 8, 15, 10, 0, 0),
                    has_critical_values=False,
                    summary="",
                )
            ],
        ),
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    req = OrchestratorRequest(message="Có chỉ số nào bất thường không?", ui_context=None)
    resp = await handle_message(req, current_user=patient, db=mock_db, runtime=runtime)

    assert resp.status == ResponseStatus.SUCCESS
    assert resp.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert resp.data_type == DataType.ANALYSIS


# TEST-08: Zero-report patient returns graceful NEEDS_INPUT
@pytest.mark.asyncio
async def test_08_zero_report_patient_graceful_handling(monkeypatch):
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    mock_db = MagicMock()
    monkeypatch.setattr(history_repository, "list_reports", lambda db, **kwargs: (0, []))

    req = OrchestratorRequest(message="Xem giúp em với", ui_context=None)
    resp = await handle_message(req, current_user=patient, db=mock_db, runtime=runtime)

    assert resp.status == ResponseStatus.NEEDS_INPUT
    assert "chưa thấy phiếu xét nghiệm nào" in resp.message
    # Must NOT leak internal schema terms
    assert "current_report_ref" not in resp.message
    assert "current_analyte" not in resp.message
    assert "AMBIGUOUS_CONTEXT" not in resp.message


# TEST-09 & TEST-10: Multi-turn journey (Summary -> Follow-up Single Analyte -> Context Switch)
@pytest.mark.asyncio
async def test_09_10_multi_turn_journey(monkeypatch):
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    detail = _make_sample_report_detail()

    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(
        history_repository,
        "list_reports",
        lambda db, **kwargs: (
            1,
            [
                LabReportSummarySchema(
                    id=42,
                    test_date=date(2026, 8, 15),
                    created_at=datetime(2026, 8, 15, 10, 0, 0),
                    has_critical_values=False,
                    summary="",
                )
            ],
        ),
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    # Turn 1: Whole-report summary
    req1 = OrchestratorRequest(message="Kết quả của em thế nào?", ui_context=None)
    resp1 = await handle_message(req1, current_user=patient, db=mock_db, runtime=runtime)
    assert resp1.status == ResponseStatus.SUCCESS
    assert resp1.data_type == DataType.ANALYSIS

    # Turn 2: Follow-up on WBC
    req2 = OrchestratorRequest(message="Giải thích kỹ hơn WBC", ui_context=None)
    resp2 = await handle_message(req2, current_user=patient, db=mock_db, runtime=runtime)
    assert resp2.status == ResponseStatus.SUCCESS
    assert resp2.data_type == DataType.EXPLANATION
    assert "Bạch cầu tăng nhẹ" in resp2.message or "bạch cầu" in resp2.message.lower()

    # Turn 3: Context switch to Glucose
    req3 = OrchestratorRequest(message="Còn Glucose thì sao?", ui_context=None)
    resp3 = await handle_message(req3, current_user=patient, db=mock_db, runtime=runtime)
    assert resp3.status == ResponseStatus.SUCCESS
    assert resp3.data_type == DataType.EXPLANATION
    assert "Đường huyết" in resp3.message or "glucose" in resp3.message.lower()


# TEST-11: Referential trend follow-up
@pytest.mark.asyncio
async def test_11_referential_trend_follow_up(monkeypatch):
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    detail = _make_sample_report_detail()

    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(
        history_repository,
        "list_reports",
        lambda db, **kwargs: (
            1,
            [
                LabReportSummarySchema(
                    id=42,
                    test_date=date(2026, 8, 15),
                    created_at=datetime(2026, 8, 15, 10, 0, 0),
                    has_critical_values=False,
                    summary="",
                )
            ],
        ),
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    # Turn 1: Explain WBC to set session context
    req1 = OrchestratorRequest(message="Giải thích WBC của tôi", ui_context=None)
    resp1 = await handle_message(req1, current_user=patient, db=mock_db, runtime=runtime)
    assert resp1.status == ResponseStatus.SUCCESS

    # Mock trend service for WBC
    monkeypatch.setattr(
        trend_service,
        "get_patient_trend",
        lambda db, **kwargs: TrendResponse(
            analyte_canonical="WBC",
            display_name="WBC",
            canonical_unit="G/L",
            filter="latest5",
            trend_available=True,
            result_count=2,
            points=[
                TrendPointResponse(report_id=1, test_date=date(2026, 7, 1), value=11.5, assessment="high"),
                TrendPointResponse(report_id=2, test_date=date(2026, 8, 15), value=9.0, assessment="normal"),
            ],
        ),
    )

    # Turn 2: Referential query using "chỉ số này"
    req2 = OrchestratorRequest(message="Chỉ số này dạo này có thay đổi gì không?", ui_context=None)
    resp2 = await handle_message(req2, current_user=patient, db=mock_db, runtime=runtime)
    assert resp2.status == ResponseStatus.SUCCESS
    assert resp2.intent == IntentEnum.ANALYZE_TREND
    assert resp2.data_type == DataType.TREND


# TEST-12: Guest authorization blocked from accessing patient reports
@pytest.mark.asyncio
async def test_12_guest_authorization():
    guest = DummyGuest()
    runtime = _runtime_with_ack(guest)
    mock_db = MagicMock()

    req = OrchestratorRequest(message="Kết quả gần nhất của tôi thế nào?", ui_context=None)
    resp = await handle_message(req, current_user=guest, db=mock_db, runtime=runtime)

    # Guests cannot access patient history or reports
    assert resp.status == ResponseStatus.BLOCKED
    assert resp.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY


# TEST-13: UIContext independence
@pytest.mark.asyncio
async def test_13_uicontext_independence(monkeypatch):
    patient = DummyPatient()
    detail = _make_sample_report_detail()
    mock_db = MagicMock()
    mock_db.scalar.return_value = 101
    monkeypatch.setattr(
        history_repository,
        "list_reports",
        lambda db, **kwargs: (
            1,
            [
                LabReportSummarySchema(
                    id=42,
                    test_date=date(2026, 8, 15),
                    created_at=datetime(2026, 8, 15, 10, 0, 0),
                    has_critical_values=False,
                    summary="",
                )
            ],
        ),
    )
    monkeypatch.setattr(history_repository, "get_report", lambda db, rid: MagicMock(id=42, patient_id=101))
    monkeypatch.setattr(history_repository, "to_detail", lambda r: detail)

    # Request 1: No UIContext
    runtime1 = _runtime_with_ack(patient)
    req1 = OrchestratorRequest(message="Kết quả gần nhất của em có gì cần chú ý?", ui_context=None)
    resp1 = await handle_message(req1, current_user=patient, db=mock_db, runtime=runtime1)

    # Request 2: With unrelated page UIContext (e.g. settings page)
    runtime2 = _runtime_with_ack(patient)
    req2 = OrchestratorRequest(
        message="Kết quả gần nhất của em có gì cần chú ý?",
        ui_context=UIContext(screen="settings_view", view="profile_tab"),
    )
    resp2 = await handle_message(req2, current_user=patient, db=mock_db, runtime=runtime2)

    assert resp1.status == resp2.status == ResponseStatus.SUCCESS
    assert resp1.intent == resp2.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert resp1.data_type == resp2.data_type == DataType.ANALYSIS


# TEST-14: Medical safety validator stops diagnosis/treatment
@pytest.mark.asyncio
async def test_14_medical_safety():
    patient = DummyPatient()
    runtime = _runtime_with_ack(patient)
    mock_db = MagicMock()

    # Medical diagnosis query must be blocked
    req = OrchestratorRequest(message="Chỉ số này cao có phải tôi bị bệnh tim không?", ui_context=None)
    resp = await handle_message(req, current_user=patient, db=mock_db, runtime=runtime)

    assert resp.status == ResponseStatus.BLOCKED
    assert resp.reason_code == ReasonCode.MEDICAL_DIAGNOSIS_REQUEST
    assert "MEDICAL_DIAGNOSIS_REQUEST" not in resp.message
    assert "UNSUPPORTED_OR_UNSAFE" not in resp.message
    assert "không thể đưa ra chẩn đoán bệnh" in resp.message
    assert "bác sĩ" in resp.message
