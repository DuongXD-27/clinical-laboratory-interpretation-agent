"""Focused G2 educational-depth regressions (G2-01 through G2-08 only)."""

from datetime import date, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import IntentEnum, OrchestratorRequest, ResponseStatus
from src.models.schemas import IndicatorResultSchema, LabReportDetailSchema
from src.orchestrator import dispatcher
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository

APPROVED_EDUCATION = (
    "Bạch cầu là một thành phần quan trọng của máu, đóng vai trò chủ chốt "
    "trong hệ thống miễn dịch."
)
APPROVED_SOURCE = "https://approved.example/wbc"


class _Catalog:
    def __init__(self, explanation: str | None = APPROVED_EDUCATION) -> None:
        self.explanation = explanation

    def resolve(self, _analyte: str):
        if self.explanation is None:
            return None
        return SimpleNamespace(
            curated_explanation=self.explanation,
            sources=(APPROVED_SOURCE,),
        )


def _setup(
    monkeypatch,
    *,
    indicator_explanation: str = APPROVED_EDUCATION,
    catalog_explanation: str | None = APPROVED_EDUCATION,
    active_analyte: str | None = None,
):
    patient_id = 701
    report_id = 42
    user = SimpleNamespace(user_id=patient_id, username="g2_patient", role=ROLE_PATIENT)
    store = InMemorySessionStore()
    store.get_or_create(user)
    session = store.acknowledge_onboarding(user)
    session.current_report_ref = str(report_id)
    session.current_analyte = active_analyte

    detail = LabReportDetailSchema(
        id=report_id,
        patient_id=patient_id,
        test_date=date(2026, 8, 20),
        created_at=datetime(2026, 8, 20, 9, 0, 0),
        status="high",
        summary="Xét nghiệm máu",
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
                unit="10^9/L",
                analyte_canonical="WBC",
                analyte_raw="WBC",
                reference_low=4.0,
                reference_high=10.0,
                status="high",
                is_abnormal=True,
                is_critical=False,
                explanation=indicator_explanation,
                sources=[APPROVED_SOURCE] if indicator_explanation else [],
            )
        ],
        critical_alerts=[],
    )
    report = MagicMock(id=report_id, patient_id=patient_id)
    monkeypatch.setattr(history_repository, "get_report", lambda _db, _rid: report)
    monkeypatch.setattr(history_repository, "to_detail", lambda _report: detail)
    monkeypatch.setattr(
        dispatcher,
        "get_analyte_catalog",
        lambda: _Catalog(catalog_explanation),
        raising=False,
    )

    db = MagicMock()
    db.scalar.return_value = patient_id
    return user, db, OrchestratorRuntime(session_store=store)


async def _ask(monkeypatch, message: str, **setup_kwargs):
    user, db, runtime = _setup(monkeypatch, **setup_kwargs)
    response = await handle_message(
        OrchestratorRequest(message=message),
        current_user=user,
        db=db,
        runtime=runtime,
    )
    assert response.status == ResponseStatus.SUCCESS
    assert response.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    return response


@pytest.mark.asyncio
async def test_g2_01_wbc_definition_is_education_first(monkeypatch) -> None:
    response = await _ask(monkeypatch, "WBC là gì?")

    assert response.message.index(APPROVED_EDUCATION) < response.message.index("12.5 10^9/L")
    assert response.sources == [APPROVED_SOURCE]


@pytest.mark.asyncio
async def test_g2_02_wbc_meaning_is_education_first(monkeypatch) -> None:
    response = await _ask(monkeypatch, "WBC có ý nghĩa gì?")

    assert response.message.index(APPROVED_EDUCATION) < response.message.index("12.5 10^9/L")


@pytest.mark.asyncio
async def test_g2_03_wbc_value_remains_current_fact_first(monkeypatch) -> None:
    response = await _ask(monkeypatch, "WBC là bao nhiêu?")

    assert response.message.index("Giá trị: 12.5 10^9/L") < response.message.index("Trạng thái: CAO")
    assert response.message.index("12.5 10^9/L") < response.message.index(APPROVED_EDUCATION)


@pytest.mark.asyncio
async def test_g2_04_wbc_status_remains_status_first(monkeypatch) -> None:
    response = await _ask(monkeypatch, "WBC có cao không?")

    assert response.message.index("Trạng thái: CAO") < response.message.index("Giá trị: 12.5 10^9/L")
    assert response.message.index("Trạng thái: CAO") < response.message.index(APPROVED_EDUCATION)


@pytest.mark.asyncio
async def test_g2_05_personal_explanation_keeps_facts_plus_approved_education(monkeypatch) -> None:
    response = await _ask(monkeypatch, "Giải thích WBC của tôi")

    assert response.message.index("12.5 10^9/L") < response.message.index(APPROVED_EDUCATION)
    assert response.sources == [APPROVED_SOURCE]


@pytest.mark.asyncio
async def test_g2_06_referential_definition_uses_active_wbc_and_education_first(monkeypatch) -> None:
    response = await _ask(
        monkeypatch,
        "Chỉ số này là gì?",
        active_analyte="WBC",
    )

    assert response.data.facts.analyte_name == "WBC"
    assert response.message.index(APPROVED_EDUCATION) < response.message.index("12.5 10^9/L")


@pytest.mark.asyncio
async def test_g2_07_missing_education_never_invents_and_keeps_safe_facts(monkeypatch) -> None:
    response = await _ask(
        monkeypatch,
        "WBC là gì?",
        indicator_explanation="",
        catalog_explanation=None,
    )

    assert "12.5 10^9/L" in response.message
    assert "Trạng thái: CAO" in response.message
    assert "miễn dịch" not in response.message.casefold()
    assert "nhiễm trùng" not in response.message.casefold()


@pytest.mark.asyncio
async def test_g2_08_conflicting_educational_numbers_never_override_facts(monkeypatch) -> None:
    conflicting = "WBC của bạn là 8.1 G/L và khoảng tham chiếu là 3.0 - 9.0 G/L."
    response = await _ask(
        monkeypatch,
        "WBC là gì?",
        indicator_explanation=conflicting,
        catalog_explanation=conflicting,
    )

    assert "12.5 10^9/L" in response.message
    assert "Khoảng tham chiếu: 4.0 - 10.0 10^9/L" in response.message
    assert "8.1 G/L" not in response.message
    assert "3.0 - 9.0" not in response.message
