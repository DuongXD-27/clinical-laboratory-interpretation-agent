"""Bounded ORCH-V1.4B referential-context resolution tests."""

from types import SimpleNamespace

import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorRequest,
    OrchestratorRole,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
)
from src.orchestrator.medical_context import resolve_medical_context
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository


def _session(
    *,
    report_ref: str | None = "101",
    analyte: str | None = None,
    last_intent: IntentEnum | None = IntentEnum.EXPLAIN_CURRENT_RESULT,
) -> OrchestratorSessionContext:
    return OrchestratorSessionContext.from_server(
        session_id="referential-test",
        user_role=OrchestratorRole.PATIENT,
        onboarding_acknowledged=True,
        current_report_ref=report_ref,
        current_analyte=analyte,
        last_intent=last_intent,
    )


def _patient(user_id: int = 901) -> SimpleNamespace:
    return SimpleNamespace(user_id=user_id, role=ROLE_PATIENT)


def _indicator(name: str, status: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        analyte_canonical=name,
        status=status,
        critical_status=None,
    )


def _report(patient_id: int, *indicators: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(patient_id=patient_id, indicators=list(indicators))


def test_b01_single_abnormal_whole_report_referent_resolves_to_wbc(monkeypatch):
    user = _patient()
    report = _report(user.user_id, _indicator("WBC", "high"), _indicator("Creatinine", "normal"))
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)

    resolved = resolve_medical_context(
        message="Giải thích kỹ hơn chỉ số đó",
        session=_session(),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte == "WBC"
    assert resolved.reason_code is None


def test_b01_pronoun_referent_resolves_to_the_single_abnormal_analyte(monkeypatch):
    user = _patient()
    report = _report(user.user_id, _indicator("WBC", "high"), _indicator("Creatinine", "normal"))
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)

    resolved = resolve_medical_context(
        message="Giải thích nó",
        session=_session(),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte == "WBC"
    assert resolved.reason_code is None


def test_b02_multiple_abnormal_referents_require_clarification(monkeypatch):
    user = _patient()
    report = _report(user.user_id, _indicator("WBC", "high"), _indicator("HbA1c", "high"))
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)

    resolved = resolve_medical_context(
        message="Giải thích kỹ hơn chỉ số đó",
        session=_session(),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte is None
    assert resolved.reason_code == ReasonCode.AMBIGUOUS_CONTEXT


@pytest.mark.asyncio
async def test_b02_ambiguous_referent_returns_safe_clarification(monkeypatch):
    user = _patient(902)
    report = _report(user.user_id, _indicator("WBC", "high"), _indicator("HbA1c", "high"))
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    session = store.get_or_create(user)
    store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_report_ref="101",
        clear_analyte=True,
    )

    response = await handle_message(
        OrchestratorRequest(message="Giải thích kỹ hơn chỉ số đó"),
        current_user=user,
        db=object(),
        runtime=OrchestratorRuntime(session_store=store),
    )

    assert response.status == ResponseStatus.NEEDS_INPUT
    assert response.reason_code == ReasonCode.AMBIGUOUS_CONTEXT
    assert "chỉ số nào" in response.message.casefold()
    assert store.get_or_create(user).current_analyte is None


def test_b03_explicit_hba1c_overrides_inferred_wbc(monkeypatch):
    user = _patient()
    report = _report(user.user_id, _indicator("WBC", "high"), _indicator("Creatinine", "normal"))
    monkeypatch.setattr(history_repository, "get_report", lambda db, report_id: report)

    resolved = resolve_medical_context(
        message="Giải thích HbA1c thay vì chỉ số đó",
        session=_session(),
        ui_context=None,
        current_user=user,
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte == "HbA1c"
    assert resolved.reason_code is None


def test_b04_active_single_analyte_context_wins_for_referential_follow_up():
    resolved = resolve_medical_context(
        message="Giải thích kỹ hơn chỉ số này",
        session=_session(analyte="WBC"),
        ui_context=None,
        current_user=_patient(),
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte == "WBC"
    assert resolved.reason_code is None


def test_b05_standalone_referent_without_context_requires_clarification():
    resolved = resolve_medical_context(
        message="Giải thích chỉ số đó",
        session=_session(report_ref=None, last_intent=None),
        ui_context=None,
        current_user=_patient(),
        db=object(),
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )

    assert resolved.current_analyte is None
    assert resolved.reason_code == ReasonCode.AMBIGUOUS_CONTEXT


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["Tôi bị bệnh gì?", "Tôi nên điều trị thế nào?"])
async def test_b06_safety_interruption_preserves_active_analyte(message):
    user = _patient(903)
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

    response = await handle_message(
        OrchestratorRequest(message=message),
        current_user=user,
        db=object(),
        runtime=OrchestratorRuntime(session_store=store),
    )

    assert response.status == ResponseStatus.BLOCKED
    assert store.get_or_create(user).current_report_ref == "101"
    assert store.get_or_create(user).current_analyte == "WBC"
