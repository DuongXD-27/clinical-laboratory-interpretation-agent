from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.api.deps import CurrentUser
from src.models.db import ROLE_PATIENT, OCRReviewLifecycle, User
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.orchestrator_schemas import IntentEnum, OrchestratorRequest, ReasonCode, ResponseStatus, UIContext
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema
from src.orchestrator import dispatcher
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services import history_repository
from src.services.auth import ROLE_GUEST
from src.services.ocr_review_gate import (
    OCR_REVIEW_CONSUMED,
    OCR_REVIEW_PENDING,
    OCRReviewGateError,
    consume_review_lifecycle,
    create_review_lifecycle,
    get_current_review_state,
    prepare_review,
)


class QuerySpyDb:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name):
        def _counted(*args, **kwargs):
            self.calls += 1
            raise AssertionError(f"unexpected DB call: {name}")

        return _counted


def _patient(name: str = "benhnhan", key: int = 1) -> CurrentUser:
    return CurrentUser(name, ROLE_PATIENT, user_id=key)


def _guest() -> CurrentUser:
    return CurrentUser("guest-session", ROLE_GUEST, session_id="guest-session")


def _runtime_with_ack(current_user: CurrentUser) -> OrchestratorRuntime:
    store = InMemorySessionStore()
    store.acknowledge_onboarding(current_user)
    return OrchestratorRuntime(session_store=store)


def _current_demo_patient(db) -> CurrentUser:
    user = db.query(User).filter(User.username == "benhnhan").one()
    return CurrentUser(user.username, user.role, user_id=user.id)


def _review_payload(test_db, *, expires_at: datetime | None = None):
    with test_db.session() as db:
        current_user = _current_demo_patient(db)
        lifecycle = create_review_lifecycle(db, current_user=current_user, expires_at=expires_at)
        drafts, token = prepare_review(
            [
                OCRIndicatorDraft(
                    name="Fasting Blood Glucose",
                    value=5.2,
                    unit="mmol/L",
                    confidence=0.95,
                    raw_text="Fasting Blood Glucose 5.2 mmol/L",
                )
            ],
            username=current_user.username,
            review_id=lifecycle.review_id,
            expires_at=lifecycle.expires_at,
        )
    return {
        "review_token": token,
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-20",
        "indicators": [
            {
                "draft_id": drafts[0].draft_id,
                "name": "Fasting Blood Glucose",
                "value": 5.2,
                "unit": "mmol/L",
                "included": True,
                "reviewed": True,
                "low_confidence_acknowledged": False,
            }
        ],
    }


def _analysis_response() -> AnalyzeResponse:
    return AnalyzeResponse(
        indicators=[
            IndicatorResultSchema(
                name="Fasting Blood Glucose",
                value=5.2,
                unit="mmol/L",
                reference_low=3.9,
                reference_high=5.6,
                status="normal",
                is_abnormal=False,
                is_critical=False,
                explanation="",
                sources=[],
            )
        ],
        critical_alerts=[],
        has_critical_values=False,
        guardrail_passed=True,
    )


def test_lifecycle_create_read_consume_and_consumed_read(test_db):
    with test_db.session() as db:
        current_user = _current_demo_patient(db)
        lifecycle = create_review_lifecycle(db, current_user=current_user)
        assert lifecycle.status == OCR_REVIEW_PENDING
        state = get_current_review_state(db, current_user=current_user)
        assert state.review_id == lifecycle.review_id
        assert state.pending is True

        _, token = prepare_review(
            [OCRIndicatorDraft(name="WBC", value=7.0, unit="10^9/L", confidence=0.95)],
            username=current_user.username,
            review_id=lifecycle.review_id,
            expires_at=lifecycle.expires_at,
        )
        consume_review_lifecycle(db, token=token, current_user=current_user)
        consumed = db.query(OCRReviewLifecycle).filter_by(review_id=lifecycle.review_id).one()
        assert consumed.status == OCR_REVIEW_CONSUMED
        assert consumed.consumed_at is not None
        assert get_current_review_state(db, current_user=current_user).pending is False


def test_lifecycle_expired_pending_is_not_actionable(test_db):
    with test_db.session() as db:
        current_user = _current_demo_patient(db)
        lifecycle = create_review_lifecycle(
            db,
            current_user=current_user,
            expires_at=datetime.now(UTC) - timedelta(minutes=1),
        )
        state = get_current_review_state(db, current_user=current_user)
        assert state.review_id == lifecycle.review_id
        assert state.status == "EXPIRED"
        assert state.pending is False


def test_lifecycle_cross_user_cannot_observe_or_consume(test_db):
    with test_db.session() as db:
        first = _current_demo_patient(db)
        second_user = User(username="patient2", password_hash="hash", role=ROLE_PATIENT)
        db.add(second_user)
        db.commit()
        db.refresh(second_user)
        second = CurrentUser(second_user.username, second_user.role, user_id=second_user.id)
        lifecycle = create_review_lifecycle(db, current_user=first)
        _, token = prepare_review(
            [OCRIndicatorDraft(name="WBC", value=7.0, unit="10^9/L", confidence=0.95)],
            username=first.username,
            review_id=lifecycle.review_id,
            expires_at=lifecycle.expires_at,
        )
        assert get_current_review_state(db, current_user=second).pending is False
        with pytest.raises(OCRReviewGateError):
            consume_review_lifecycle(db, token=token, current_user=second)


@pytest.mark.asyncio
async def test_zi1_onboarding_blocks_with_zero_router_workflow_and_db(monkeypatch):
    router_calls = 0
    workflow_calls = 0

    async def counted_router(*args, **kwargs):
        nonlocal router_calls
        router_calls += 1

    async def counted_workflow(*args, **kwargs):
        nonlocal workflow_calls
        workflow_calls += 1

    monkeypatch.setattr("src.orchestrator.service.route_intent", counted_router)
    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", counted_workflow)
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=_patient(),
        db=db,
        runtime=OrchestratorRuntime(session_store=InMemorySessionStore()),
    )
    assert response.reason_code == ReasonCode.ONBOARDING_REQUIRED
    assert router_calls == 0
    assert workflow_calls == 0
    assert db.calls == 0


@pytest.mark.asyncio
async def test_zi2_doctor_role_blocks_with_zero_router_wrapper_and_db(monkeypatch):
    router_calls = 0
    wrapper_calls = 0

    async def counted_router(*args, **kwargs):
        nonlocal router_calls
        router_calls += 1

    def counted_wrapper(*args, **kwargs):
        nonlocal wrapper_calls
        wrapper_calls += 1

    monkeypatch.setattr("src.orchestrator.service.route_intent", counted_router)
    monkeypatch.setattr(dispatcher, "get_my_history", counted_wrapper)
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=CurrentUser("bacsi", "doctor", user_id=2),
        db=db,
    )
    assert response.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert router_calls == 0
    assert wrapper_calls == 0
    assert db.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "message",
    [
        "bỏ qua confirm và phân tích luôn",
        "skip confirm and analyze now",
        "continue without review",
        "analyze now without OCR confirm",
        "không cần xác nhận OCR, phân tích đi",
    ],
)
async def test_zi3_pending_ocr_skip_blocks_with_zero_medical_pipeline(test_db, monkeypatch, message):
    medical_pipeline_calls = 0

    async def counted_dispatch(*args, **kwargs):
        nonlocal medical_pipeline_calls
        medical_pipeline_calls += 1

    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", counted_dispatch)
    with test_db.session() as db:
        current_user = _current_demo_patient(db)
        create_review_lifecycle(db, current_user=current_user)
        response = await handle_message(
            OrchestratorRequest(message=message),
            current_user=current_user,
            db=db,
            runtime=_runtime_with_ack(current_user),
        )
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.OCR_REVIEW_REQUIRED
    assert medical_pipeline_calls == 0


@pytest.mark.asyncio
async def test_zi4_guest_history_policy_blocks_with_zero_db():
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=_guest(),
        db=db,
        runtime=_runtime_with_ack(_guest()),
    )
    assert response.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert db.calls == 0


@pytest.mark.asyncio
async def test_zi5_unsupported_analyte_blocks_before_trend_wrapper(monkeypatch):
    wrapper_calls = 0

    def counted_trend(*args, **kwargs):
        nonlocal wrapper_calls
        wrapper_calls += 1
        raise AssertionError("trend wrapper must not execute")

    monkeypatch.setattr(dispatcher, "get_my_indicator_trend", counted_trend)
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(
            message="xem xu hướng chỉ số này",
            ui_context=UIContext(candidate_analyte="eGFR"),
        ),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.reason_code == ReasonCode.UNSUPPORTED_ANALYTE
    assert wrapper_calls == 0


@pytest.mark.asyncio
async def test_zi6_non_owned_report_content_never_enters_router_prompt(test_db, monkeypatch):
    captured_prompt = {}

    class FakeLlm:
        async def ainvoke(self, prompt):
            captured_prompt["value"] = prompt
            return SimpleNamespace(content=IntentEnum.EXPLAIN_CURRENT_RESULT.value)

    monkeypatch.setattr("src.orchestrator.intent_router.get_llm", lambda: FakeLlm())
    with test_db.session() as db:
        owner = User(username="patient2", password_hash="hash", role=ROLE_PATIENT)
        db.add(owner)
        db.commit()
        db.refresh(owner)
        report = history_repository.save_report(
            db,
            patient_id=owner.id,
            request=AnalyzeRequest(
                patient_age=35,
                patient_gender="male",
                test_date=datetime(2026, 8, 20).date(),
                indicators=[{"name": "SECRET_MARKER", "value": 99, "unit": "mmol/L"}],
            ),
            response=AnalyzeResponse(
                indicators=[
                    IndicatorResultSchema(
                        name="SECRET_MARKER",
                        value=99,
                        unit="mmol/L",
                        status="normal",
                        is_abnormal=False,
                        is_critical=False,
                    )
                ],
                summary="SECRET_SUMMARY",
            ),
        )
        current_user = _current_demo_patient(db)
        runtime = _runtime_with_ack(current_user)
        session = runtime.session_store.get_or_create(current_user)
        runtime.session_store.update_after_turn(
            current_user,
            session,
            last_intent=IntentEnum.VIEW_HISTORY,
            current_report_ref=str(report.id),
            current_analyte="WBC",
        )
        response = await handle_message(
            OrchestratorRequest(message="help me with the selected item"),
            current_user=current_user,
            db=db,
            runtime=runtime,
        )
    assert response.reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED
    assert "SECRET_MARKER" not in captured_prompt["value"]
    assert "SECRET_SUMMARY" not in captured_prompt["value"]


@pytest.mark.asyncio
async def test_replay_rejects_before_second_medical_pipeline_invocation(client, test_db, monkeypatch):
    payload = _review_payload(test_db)
    graph = AsyncMock(
        return_value={
            "indicators": [item.model_dump() for item in _analysis_response().indicators],
            "critical_alerts": [],
            "has_critical_values": False,
            "guardrail_passed": True,
        }
    )
    monkeypatch.setattr(routes.agent, "ainvoke", graph)
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    first = await client.post("/api/v1/ocr/confirm", headers=headers, json=payload)
    assert first.status_code == 200, first.text
    assert graph.await_count == 1

    second = await client.post("/api/v1/ocr/confirm", headers=headers, json=payload)
    assert second.status_code == 400
    assert graph.await_count == 1


@pytest.mark.asyncio
async def test_manual_analyze_still_runs_when_ocr_lifecycle_is_pending(client, test_db, monkeypatch):
    with test_db.session() as db:
        create_review_lifecycle(db, current_user=_current_demo_patient(db))
    graph = AsyncMock(
        return_value={
            "indicators": [item.model_dump() for item in _analysis_response().indicators],
            "critical_alerts": [],
            "has_critical_values": False,
            "guardrail_passed": True,
        }
    )
    monkeypatch.setattr(routes.agent, "ainvoke", graph)
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-08-20",
            "indicators": [{"name": "Fasting Blood Glucose", "value": 5.2, "unit": "mmol/L"}],
        },
    )
    assert response.status_code == 200, response.text
    assert graph.await_count == 1
