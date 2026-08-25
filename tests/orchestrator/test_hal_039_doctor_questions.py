from datetime import date, datetime
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT, LabReport, ReportIndicator, ReportQuestion
from src.models.orchestrator_schemas import DoctorQuestionsPayload, IntentEnum, ResponseStatus
from src.orchestrator import wrappers
from src.orchestrator.dispatcher import DispatchContext, dispatch_workflow
from src.orchestrator.response_composer import build_final_response


class Patient:
    role = ROLE_PATIENT
    username = "hal039"
    user_id = 39


def _report(*, questions: list[ReportQuestion] | None = None) -> LabReport:
    report = LabReport(
        id=390,
        patient_id=Patient.user_id,
        test_date=date(2026, 8, 24),
        created_at=datetime(2026, 8, 24, 7, 0, 0),
        language="vi",
        summary="Phiếu HAL-039",
        has_critical_values=False,
        guardrail_passed=True,
        disclaimer="Thông tin giáo dục.",
    )
    wbc = ReportIndicator(
        id=391,
        report_id=report.id,
        name="WBC",
        analyte_raw="WBC",
        analyte_canonical="WBC",
        value=12.0,
        unit="10^9/L",
        status="high",
        explanation="",
        sources=[],
    )
    creatinine = ReportIndicator(
        id=392,
        report_id=report.id,
        name="Creatinine",
        analyte_raw="Creatinine",
        analyte_canonical="Creatinine",
        value=140.0,
        unit="umol/L",
        status="high",
        explanation="",
        sources=[],
    )
    report.indicators = [wbc, creatinine]
    report.critical_alerts = []
    report.questions = questions or []
    report.out_of_scope_entries = []
    report.doctor_views = []
    return report


def _stored(question_id: int, indicator_id: int, text: str, order: int) -> ReportQuestion:
    return ReportQuestion(
        id=question_id,
        report_id=390,
        indicator_id=indicator_id,
        question_text=text,
        priority="abnormal",
        display_order=order,
        status="generated",
        is_selected=False,
        created_at=datetime(2026, 8, 24, 8, 0, 0),
    )


def _authorized(monkeypatch, report: LabReport) -> MagicMock:
    db = MagicMock()
    db.scalar.return_value = Patient.user_id
    monkeypatch.setattr(wrappers.history_repository, "get_report", lambda _db, _id: report)
    return db


def test_persisted_questions_are_reused_without_regeneration_and_keep_order(monkeypatch):
    report = _report(
        questions=[
            _stored(2, 392, "Câu Creatinine đã duyệt.", 1),
            _stored(1, 391, "Câu WBC đã duyệt nguyên văn.", 0),
        ]
    )
    db = _authorized(monkeypatch, report)
    generator = MagicMock(side_effect=AssertionError("must not regenerate persisted questions"))
    monkeypatch.setattr(wrappers, "generate_questions", generator)

    payload = wrappers.get_report_questions(Patient(), db, report_ref="390")

    assert [question.text for question in payload.questions] == [
        "Câu WBC đã duyệt nguyên văn.",
        "Câu Creatinine đã duyệt.",
    ]
    generator.assert_not_called()


def test_active_analyte_returns_only_matching_persisted_questions(monkeypatch):
    report = _report(
        questions=[
            _stored(1, 391, "Chỉ câu WBC.", 0),
            _stored(2, 392, "Không trả câu Creatinine.", 1),
        ]
    )
    db = _authorized(monkeypatch, report)

    payload = wrappers.get_report_questions(Patient(), db, report_ref=390, analyte="WBC")

    assert [question.text for question in payload.questions] == ["Chỉ câu WBC."]


def test_missing_analyte_question_falls_back_only_for_requested_analyte(monkeypatch):
    report = _report(questions=[_stored(2, 392, "Câu Creatinine.", 0)])
    db = _authorized(monkeypatch, report)
    captured = []

    def fake_generate(indicators):
        captured.extend(indicators)
        return []

    monkeypatch.setattr(wrappers, "generate_questions", fake_generate)

    payload = wrappers.get_report_questions(Patient(), db, report_ref=390, analyte="WBC")

    assert payload.questions == []
    assert [item["name"] for item in captured] == ["WBC"]
    assert captured[0]["analyte_id"] == "wbc"


def test_other_patients_report_remains_inaccessible(monkeypatch):
    report = _report(questions=[_stored(1, 391, "Không được lộ.", 0)])
    db = MagicMock()
    db.scalar.return_value = Patient.user_id + 1
    monkeypatch.setattr(wrappers.history_repository, "get_report", lambda _db, _id: report)

    with pytest.raises(wrappers.OrchestratorWrapperError):
        wrappers.get_report_questions(Patient(), db, report_ref=390)


@pytest.mark.asyncio
async def test_dispatch_passes_active_analyte_and_visible_message_lists_questions(monkeypatch):
    approved = "Bác sĩ thường cân nhắc những yếu tố nào khi WBC tăng?"
    payload = DoctorQuestionsPayload(
        questions=[
            wrappers.GeneratedQuestion(
                text=approved,
                priority="abnormal",
                display_order=0,
                analyte_id="wbc",
                indicator_name="WBC",
            )
        ]
    )
    call = MagicMock(return_value=payload)
    monkeypatch.setattr("src.orchestrator.dispatcher.get_report_questions", call)

    result = await dispatch_workflow(
        IntentEnum.GET_DOCTOR_QUESTIONS,
        DispatchContext(
            current_user=Patient(),
            db=MagicMock(),
            current_report_ref="390",
            current_analyte="WBC",
        ),
    )
    response = await build_final_response(
        intent=IntentEnum.GET_DOCTOR_QUESTIONS,
        status=ResponseStatus.SUCCESS,
        data=result.data,
    )

    assert call.call_args.kwargs["analyte"] == "WBC"
    assert approved in response.message
    assert "1. " in response.message
