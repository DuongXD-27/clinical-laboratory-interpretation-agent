from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock

import pytest

from src.api import routes as analysis_routes
from src.api.deps import CurrentUser
from src.models.db import ROLE_PATIENT, User
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    IntentEnum,
    OrchestratorRequest,
    ReasonCode,
)
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema
from src.orchestrator.medical_context import resolve_medical_context
from src.orchestrator import service as orchestrator_service
from src.orchestrator import session_store as session_store_module
from src.orchestrator.intent_router import RouteDecision
from src.orchestrator import response_composer
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository


def _create_patient(test_db, username: str) -> int:
    with test_db.session() as db:
        user = User(username=username, password_hash="hash", role=ROLE_PATIENT)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _patient(username: str, user_id: int) -> CurrentUser:
    return CurrentUser(username, ROLE_PATIENT, user_id=user_id)


def _request(test_date: date, value: float) -> AnalyzeRequest:
    return AnalyzeRequest(
        patient_age=35,
        patient_gender="male",
        test_date=test_date,
        language="vi",
        indicators=[{"name": "WBC", "value": value, "unit": "10^9/L"}],
    )


def _response(value: float) -> AnalyzeResponse:
    return AnalyzeResponse(
        indicators=[
            IndicatorResultSchema(
                name="WBC",
                value=value,
                unit="10^9/L",
                analyte_canonical="WBC",
                canonical_value=value,
                canonical_unit="10^9/L",
                reference_low=4.0,
                reference_high=11.0,
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation=f"WBC {value}",
                sources=[],
            )
        ],
        critical_alerts=[],
        has_critical_values=False,
        summary=f"report value {value}",
        guardrail_passed=True,
    )


def _graph_result(value: float) -> dict:
    response = _response(value)
    return {
        "indicators": [indicator.model_dump() for indicator in response.indicators],
        "critical_alerts": [],
        "has_critical_values": False,
        "guardrail_passed": True,
        "disclaimer": "Test disclaimer",
        "questions_for_doctor": [],
        "out_of_scope_indicators": [],
        "summary": response.summary,
    }


def _save_report(test_db, patient_id: int, test_date: date, value: float) -> int:
    with test_db.session() as db:
        report = history_repository.save_report(
            db,
            patient_id=patient_id,
            request=_request(test_date, value),
            response=_response(value),
        )
        return report.id


def _active_store(patient: CurrentUser, report_ref: int, *, analyte: str | None = "WBC") -> InMemorySessionStore:
    store = InMemorySessionStore()
    session = store.acknowledge_onboarding(patient)
    store.update_after_turn(
        patient,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_report_ref=str(report_ref),
        current_analyte=analyte,
    )
    return store


@pytest.mark.asyncio
async def test_explicit_latest_overrides_stale_session_report_and_response_values(test_db):
    patient_id = _create_patient(test_db, "latest_owner")
    patient = _patient("latest_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    report_b = _save_report(test_db, patient_id, date(2026, 8, 20), 9.7)
    store = _active_store(patient, report_a)

    with test_db.session() as db:
        response = await handle_message(
            OrchestratorRequest(message="đọc phiếu gần nhất"),
            current_user=patient,
            db=db,
            runtime=OrchestratorRuntime(session_store=store),
        )

    assert isinstance(response.data, AnalysisDataPayload)
    assert response.data.indicators[0].value == 9.7
    refreshed = store.get_or_create(patient)
    assert refreshed.current_report_ref == str(report_b)
    assert refreshed.current_analyte is None


@pytest.mark.asyncio
async def test_successful_report_save_activates_new_report_and_clears_analyte(test_db, monkeypatch):
    patient_id = _create_patient(test_db, "upload_owner")
    patient = _patient("upload_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    store = _active_store(patient, report_a)
    monkeypatch.setattr(analysis_routes, "default_session_store", store, raising=False)
    monkeypatch.setattr(
        analysis_routes.agent,
        "ainvoke",
        AsyncMock(return_value=_graph_result(8.8)),
    )

    with test_db.session() as db:
        result = await analysis_routes.run_analysis(
            _request(date(2026, 8, 21), 8.8),
            current_user=patient,
            db=db,
        )
        _, reports = history_repository.list_reports(db, patient_id=patient_id, limit=1)

    assert result.saved_report_id is not None
    assert reports[0].id == result.saved_report_id
    refreshed = store.get_or_create(patient)
    assert refreshed.current_report_ref == str(result.saved_report_id)
    assert refreshed.current_analyte is None

    with test_db.session() as db:
        generic = resolve_medical_context(
            "đọc kết quả của tôi",
            refreshed,
            ui_context=None,
            current_user=patient,
            db=db,
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        )
    assert generic.current_report_ref == str(result.saved_report_id)

    referential = resolve_medical_context(
        "chỉ số này",
        refreshed,
        ui_context=None,
        current_user=patient,
        db=None,
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
    )
    assert referential.current_analyte is None
    assert referential.reason_code == ReasonCode.AMBIGUOUS_CONTEXT


@pytest.mark.asyncio
async def test_generic_read_uses_newest_even_when_worker_session_is_stale(test_db, monkeypatch):
    patient_id = _create_patient(test_db, "generic_owner")
    patient = _patient("generic_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    report_b = _save_report(test_db, patient_id, date(2026, 8, 21), 8.8)
    store = _active_store(patient, report_a)
    monkeypatch.setattr(
        orchestrator_service,
        "route_intent",
        AsyncMock(return_value=RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT)),
    )

    with test_db.session() as db:
        response = await handle_message(
            OrchestratorRequest(message="đọc kết quả của tôi"),
            current_user=patient,
            db=db,
            runtime=OrchestratorRuntime(session_store=store),
        )

    assert isinstance(response.data, AnalysisDataPayload)
    assert response.data.indicators[0].value == 8.8
    assert store.get_or_create(patient).current_report_ref == str(report_b)


def test_explicit_owned_report_date_overrides_active_newest(test_db):
    patient_id = _create_patient(test_db, "date_owner")
    patient = _patient("date_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    report_b = _save_report(test_db, patient_id, date(2026, 8, 20), 9.7)
    store = _active_store(patient, report_b, analyte=None)

    with test_db.session() as db:
        resolved = resolve_medical_context(
            "đọc phiếu ngày 15/08/2026",
            store.get_or_create(patient),
            ui_context=None,
            current_user=patient,
            db=db,
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        )

    assert resolved.current_report_ref == str(report_a)


def test_latest_lookup_is_limited_to_authenticated_patient(test_db):
    patient_a_id = _create_patient(test_db, "scope_a")
    patient_b_id = _create_patient(test_db, "scope_b")
    patient_a = _patient("scope_a", patient_a_id)
    report_a_old = _save_report(test_db, patient_a_id, date(2026, 8, 10), 5.5)
    report_a_latest = _save_report(test_db, patient_a_id, date(2026, 8, 20), 6.6)
    _save_report(test_db, patient_b_id, date(2026, 8, 22), 99.0)
    store = _active_store(patient_a, report_a_old)

    with test_db.session() as db:
        resolved = resolve_medical_context(
            "phiếu mới nhất",
            store.get_or_create(patient_a),
            ui_context=None,
            current_user=patient_a,
            db=db,
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        )

    assert resolved.current_report_ref == str(report_a_latest)


def test_explicit_report_id_wins_even_when_message_mentions_newest(test_db):
    patient_id = _create_patient(test_db, "explicit_owner")
    patient = _patient("explicit_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    report_b = _save_report(test_db, patient_id, date(2026, 8, 20), 9.7)
    store = _active_store(patient, report_b, analyte=None)

    with test_db.session() as db:
        resolved = resolve_medical_context(
            f"đọc phiếu số {report_a}, không phải phiếu mới nhất",
            store.get_or_create(patient),
            ui_context=None,
            current_user=patient,
            db=db,
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        )

    assert resolved.current_report_ref == str(report_a)


def test_explicit_analyte_can_be_reestablished_for_newest_report(test_db):
    patient_id = _create_patient(test_db, "analyte_owner")
    patient = _patient("analyte_owner", patient_id)
    report_a = _save_report(test_db, patient_id, date(2026, 8, 15), 6.1)
    report_b = _save_report(test_db, patient_id, date(2026, 8, 20), 9.7)
    store = _active_store(patient, report_a, analyte="HbA1c")

    with test_db.session() as db:
        resolved = resolve_medical_context(
            "WBC trong phiếu mới nhất",
            store.get_or_create(patient),
            ui_context=None,
            current_user=patient,
            db=db,
            intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        )

    assert resolved.current_report_ref == str(report_b)
    assert resolved.current_analyte == "WBC"


@pytest.mark.asyncio
async def test_http_e2e_report_a_upload_b_history_and_latest(
    client,
    test_db,
    monkeypatch,
):
    store = InMemorySessionStore()
    monkeypatch.setattr(analysis_routes, "default_session_store", store)
    monkeypatch.setattr(orchestrator_service, "default_session_store", store)
    monkeypatch.setattr(session_store_module, "default_session_store", store)
    monkeypatch.setattr(
        response_composer,
        "get_llm",
        lambda: (_ for _ in ()).throw(RuntimeError("deterministic E2E")),
    )
    graph = AsyncMock(side_effect=[_graph_result(6.1), _graph_result(9.7)])
    monkeypatch.setattr(analysis_routes.agent, "ainvoke", graph)

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    await client.post("/api/v1/orchestrator/onboarding/acknowledge", headers=headers)

    report_a_response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json=_request(date(2026, 8, 15), 6.1).model_dump(mode="json"),
    )
    assert report_a_response.status_code == 200, report_a_response.text
    report_a_id = report_a_response.json()["saved_report_id"]

    read_a = await client.post(
        "/api/v1/orchestrator/message",
        headers=headers,
        json={"message": f"đọc phiếu số {report_a_id}"},
    )
    assert read_a.status_code == 200, read_a.text
    assert read_a.json()["data"]["indicators"][0]["value"] == 6.1

    with test_db.session() as db:
        user = db.query(User).filter(User.username == "benhnhan").one()
        patient = _patient(user.username, user.id)
    session_before_upload = store.get_or_create(patient).current_report_ref

    report_b_response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json=_request(date(2026, 8, 21), 9.7).model_dump(mode="json"),
    )
    assert report_b_response.status_code == 200, report_b_response.text
    report_b_id = report_b_response.json()["saved_report_id"]
    session_after_upload = store.get_or_create(patient).current_report_ref

    history = await client.get("/api/v1/history?limit=5", headers=headers)
    assert history.status_code == 200, history.text
    assert history.json()["items"][0]["id"] == report_b_id

    latest = await client.post(
        "/api/v1/orchestrator/message",
        headers=headers,
        json={"message": "đọc phiếu gần nhất"},
    )
    assert latest.status_code == 200, latest.text
    latest_payload = latest.json()
    resolved_report_id = store.get_or_create(patient).current_report_ref
    response_values = [indicator["value"] for indicator in latest_payload["data"]["indicators"]]

    assert report_a_id != report_b_id
    assert session_before_upload == str(report_a_id)
    assert session_after_upload == str(report_b_id)
    assert resolved_report_id == str(report_b_id)
    assert response_values == [9.7]

    print(f"REPORT_A_ID={report_a_id}")
    print(f"REPORT_B_ID={report_b_id}")
    print(f"SESSION_REPORT_BEFORE_UPLOAD={session_before_upload}")
    print(f"SESSION_REPORT_AFTER_UPLOAD={session_after_upload}")
    print(f"RESOLVED_REPORT_ID={resolved_report_id}")
    print(f"RESPONSE_VALUES={response_values}")
