from __future__ import annotations

from datetime import date

import pytest

from src.api.deps import CurrentUser
from src.models.db import ROLE_PATIENT, User
from src.models.orchestrator_schemas import DoctorQuestionsPayload, IntentEnum, ResponseStatus
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema
from src.orchestrator import response_composer, wrappers
from src.orchestrator.response_composer import build_final_response
from src.services import history_repository
from src.services.question_templates import GeneratedQuestion


def _create_patient(test_db, username: str) -> CurrentUser:
    with test_db.session() as db:
        user = User(username=username, password_hash="hash", role=ROLE_PATIENT)
        db.add(user)
        db.commit()
        db.refresh(user)
        return CurrentUser(user.username, user.role, user_id=user.id)


def _response(rows: list[dict]) -> AnalyzeResponse:
    return AnalyzeResponse(
        indicators=[
            IndicatorResultSchema(
                name=row["name"],
                value=row["value"],
                unit=row["unit"],
                analyte_canonical=row.get("analyte_canonical", row["name"]),
                canonical_value=row.get("canonical_value", row["value"]),
                canonical_unit=row.get("canonical_unit", row["unit"]),
                reference_low=row.get("reference_low"),
                reference_high=row.get("reference_high"),
                status=row.get("status", "normal"),
                is_abnormal=row.get("status") in {"low", "high", "critical_low", "critical_high"},
                is_critical=row.get("status") in {"critical_low", "critical_high"},
                explanation=row.get("explanation", ""),
                sources=row.get("sources", []),
            )
            for row in rows
        ],
        critical_alerts=[],
        has_critical_values=False,
        summary="",
        guardrail_passed=True,
    )


def _save_report(
    test_db,
    current_user: CurrentUser,
    *,
    rows: list[dict],
    questions: list[GeneratedQuestion],
) -> int:
    with test_db.session() as db:
        report = history_repository.save_report(
            db,
            patient_id=current_user.user_id,
            request=AnalyzeRequest(
                patient_age=35,
                patient_gender="male",
                test_date=date(2026, 8, 24),
                language="vi",
                indicators=[
                    {"name": row["name"], "value": row["value"], "unit": row["unit"]}
                    for row in rows
                ],
            ),
            response=_response(rows),
            questions=questions,
        )
        return report.id


def test_explicit_analyte_never_returns_unrelated_persisted_questions(test_db):
    current_user = _create_patient(test_db, "hal039_patient_unrelated")
    report_ref = _save_report(
        test_db,
        current_user,
        rows=[
            {
                "name": "WBC",
                "value": 15.0,
                "unit": "10^9/L",
                "status": "high",
                "reference_low": 4.72,
                "reference_high": 11.3,
            },
            {
                "name": "HbA1c",
                "value": 8.2,
                "unit": "%",
                "status": "high",
                "reference_low": 4.0,
                "reference_high": 5.6,
            },
        ],
        questions=[
            GeneratedQuestion(
                text="HbA1c persisted wording must not leak into WBC.",
                priority="abnormal",
                display_order=0,
                analyte_id="hba1c",
                indicator_name="HbA1c",
            )
        ],
    )

    with test_db.session() as db:
        payload = wrappers.get_report_questions(
            current_user,
            db,
            report_ref=str(report_ref),
            current_analyte="WBC",
        )

    texts = [question.text for question in payload.questions]
    assert texts
    assert "HbA1c persisted wording must not leak into WBC." not in texts
    assert all("WBC" in text for text in texts)


def test_matching_persisted_question_wording_is_preserved_exactly(test_db):
    current_user = _create_patient(test_db, "hal039_patient_exact")
    exact_text = "Toi can hoi bac si ve viec theo doi WBC nhu the nao?"
    report_ref = _save_report(
        test_db,
        current_user,
        rows=[
            {
                "name": "WBC",
                "value": 15.0,
                "unit": "10^9/L",
                "status": "high",
                "reference_low": 4.72,
                "reference_high": 11.3,
            }
        ],
        questions=[
            GeneratedQuestion(
                text=exact_text,
                priority="abnormal",
                display_order=0,
                analyte_id="wbc",
                indicator_name="WBC",
            )
        ],
    )

    with test_db.session() as db:
        payload = wrappers.get_report_questions(
            current_user,
            db,
            report_ref=str(report_ref),
            current_analyte="WBC",
        )

    assert [question.text for question in payload.questions] == [exact_text]


@pytest.mark.asyncio
async def test_doctor_questions_are_rendered_without_composer_llm(monkeypatch):
    def fail_if_called():
        raise AssertionError("doctor question rendering must not call the composer LLM")

    monkeypatch.setattr(response_composer, "get_llm", fail_if_called)
    exact_text = "Toi can trao doi voi bac si ve ke hoach theo doi WBC?"

    response = await build_final_response(
        intent=IntentEnum.GET_DOCTOR_QUESTIONS,
        status=ResponseStatus.SUCCESS,
        data=DoctorQuestionsPayload(
            questions=[
                GeneratedQuestion(
                    text=exact_text,
                    priority="abnormal",
                    display_order=0,
                    analyte_id="wbc",
                    indicator_name="WBC",
                )
            ]
        ),
    )

    assert response.status == ResponseStatus.SUCCESS
    assert exact_text in response.message
    assert "Đây là các câu hỏi gợi ý để trao đổi với bác sĩ." not in response.message
