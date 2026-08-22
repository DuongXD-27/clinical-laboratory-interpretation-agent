from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from src.api.deps import CurrentUser
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT
from src.models.orchestrator_schemas import (
    DataType,
    HistorySummaryPayload,
    IntentEnum,
    OrchestratorRequest,
    OrchestratorResponse,
    ReasonCode,
    ResponseStatus,
    UIContext,
)
from src.orchestrator.dispatcher import WorkflowResult
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.services.auth import ROLE_GUEST


class QuerySpyDb:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name):
        def _counted(*args, **kwargs):
            self.calls += 1
            raise AssertionError(f"unexpected DB call: {name}")

        return _counted


def _patient() -> CurrentUser:
    return CurrentUser("benhnhan", ROLE_PATIENT, user_id=1)


def _guest() -> CurrentUser:
    return CurrentUser("guest-session", ROLE_GUEST, session_id="guest-session")


def _doctor() -> CurrentUser:
    return CurrentUser("bacsi", ROLE_DOCTOR, user_id=2)


def _runtime_with_ack(current_user: CurrentUser) -> OrchestratorRuntime:
    store = InMemorySessionStore()
    store.acknowledge_onboarding(current_user)
    return OrchestratorRuntime(session_store=store)


def _history_result() -> WorkflowResult:
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=HistorySummaryPayload(
            report_ref="report-1",
            test_date="2026-08-20",
            summary="summary",
            status="NORMAL",
            has_critical_values=False,
            result_count=1,
        ),
        workflow_selected="fake",
    )


@pytest.mark.asyncio
async def test_ac1_onboarding_blocks_before_router_db_and_workflow(monkeypatch):
    router_calls = 0
    workflow_calls = 0

    async def counted_router(*args, **kwargs):
        nonlocal router_calls
        router_calls += 1
        raise AssertionError("router must not execute")

    async def counted_dispatch(*args, **kwargs):
        nonlocal workflow_calls
        workflow_calls += 1
        raise AssertionError("workflow must not execute")

    monkeypatch.setattr("src.orchestrator.service.route_intent", counted_router)
    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", counted_dispatch)
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=_patient(),
        db=db,
        runtime=OrchestratorRuntime(session_store=InMemorySessionStore()),
    )
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.ONBOARDING_REQUIRED
    assert router_calls == 0
    assert workflow_calls == 0
    assert db.calls == 0


@pytest.mark.asyncio
async def test_ac2_doctor_role_admission_blocks_before_router_context_and_db(monkeypatch):
    router_calls = 0

    async def counted_router(*args, **kwargs):
        nonlocal router_calls
        router_calls += 1
        raise AssertionError("router must not execute")

    monkeypatch.setattr("src.orchestrator.service.route_intent", counted_router)
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=_doctor(),
        db=db,
    )
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert router_calls == 0
    assert db.calls == 0


@pytest.mark.asyncio
async def test_ac3_guest_view_history_denied_at_policy_before_db_access():
    db = QuerySpyDb()
    response = await handle_message(
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        current_user=_guest(),
        db=db,
        runtime=_runtime_with_ack(_guest()),
    )
    assert response.intent == IntentEnum.VIEW_HISTORY
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert db.calls == 0


@pytest.mark.asyncio
async def test_ac4_current_analyte_comparison_routes_to_trend(monkeypatch):
    current_user = _patient()
    runtime = _runtime_with_ack(current_user)
    session = runtime.session_store.get_or_create(current_user)
    runtime.session_store.update_after_turn(
        current_user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        current_analyte="HbA1c",
    )
    captured = {}

    async def fake_dispatch(intent, context):
        captured["intent"] = intent
        captured["analyte"] = context.current_analyte
        return _history_result()

    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", fake_dispatch)
    response = await handle_message(
        OrchestratorRequest(message="So với lần trước thì sao?"),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=runtime,
    )
    assert captured == {"intent": IntentEnum.ANALYZE_TREND, "analyte": "HbA1c"}
    assert response.intent == IntentEnum.ANALYZE_TREND


@pytest.mark.asyncio
async def test_ac5_missing_analyte_for_comparison_needs_input():
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(message="So với lần trước thì sao?"),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.status == ResponseStatus.NEEDS_INPUT
    assert response.reason_code == ReasonCode.AMBIGUOUS_CONTEXT


@pytest.mark.asyncio
async def test_ac6_diagnosis_request_uses_unsafe_flow():
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(message="Kết quả này chứng minh tôi mắc bệnh gì?"),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.status == ResponseStatus.BLOCKED
    assert response.reason_code == ReasonCode.MEDICAL_DIAGNOSIS_REQUEST
    assert response.safety_notice


@pytest.mark.asyncio
async def test_ac8_chat_lab_value_needs_input_and_does_not_dispatch():
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(message="HbA1c của tôi 7.2, có sao không?"),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.status == ResponseStatus.NEEDS_INPUT
    assert response.reason_code == ReasonCode.AMBIGUOUS_CONTEXT
    assert "7.2" not in response.model_dump_json()


@pytest.mark.asyncio
async def test_ac10_gibberish_returns_unknown_intent_schema_valid():
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(message="xqz"),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert response.reason_code == ReasonCode.UNKNOWN_INTENT
    assert OrchestratorResponse.model_validate(response.model_dump()) == response


@pytest.mark.asyncio
async def test_ac11_intent_router_prompt_is_sanitized(monkeypatch):
    captured = {}

    class FakeLlm:
        async def ainvoke(self, prompt):
            captured["prompt"] = prompt
            return SimpleNamespace(content="VIEW_HISTORY")

    monkeypatch.setattr("src.orchestrator.intent_router.get_llm", lambda: FakeLlm())
    from src.orchestrator.intent_router import route_intent

    await route_intent(
        "open report 123 from 2026-08-20 for patient@example.com",
        runtime_session(),
        ROLE_PATIENT,
    )
    prompt = captured["prompt"]
    assert "123" not in prompt
    assert "2026-08-20" not in prompt
    assert "patient@example.com" not in prompt
    assert "chat_history" not in prompt


def runtime_session():
    current_user = _patient()
    runtime = _runtime_with_ack(current_user)
    return runtime.session_store.get_or_create(current_user)


@pytest.mark.asyncio
async def test_ac12_orchestrator_logs_exclude_raw_message_values_and_tokens(monkeypatch, caplog):
    async def fake_dispatch(*args, **kwargs):
        return _history_result()

    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", fake_dispatch)
    current_user = _patient()
    with caplog.at_level(logging.INFO, logger="src.orchestrator.service"):
        await handle_message(
            OrchestratorRequest(message="cho tôi xem lịch sử token-secret"),
            current_user=current_user,
            db=QuerySpyDb(),
            runtime=_runtime_with_ack(current_user),
        )
    log_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "token-secret" not in log_text
    assert "cho tôi xem lịch sử" not in log_text


@pytest.mark.asyncio
async def test_ac13_every_core_path_returns_schema_valid_response(monkeypatch):
    async def fake_dispatch(*args, **kwargs):
        return _history_result()

    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", fake_dispatch)
    current_user = _patient()
    runtime = _runtime_with_ack(current_user)
    requests = [
        OrchestratorRequest(message="cho tôi xem lịch sử"),
        OrchestratorRequest(message="xqz"),
        OrchestratorRequest(message="HbA1c của tôi 7.2, có sao không?"),
        OrchestratorRequest(message="Kết quả này chứng minh tôi mắc bệnh gì?"),
    ]
    for request in requests:
        response = await handle_message(request, current_user=current_user, db=QuerySpyDb(), runtime=runtime)
        assert OrchestratorResponse.model_validate(response.model_dump()) == response


@pytest.mark.asyncio
async def test_ui_context_can_narrow_context_without_granting_identity(monkeypatch):
    captured = {}

    async def fake_dispatch(intent, context):
        captured["report_ref"] = context.current_report_ref
        captured["analyte"] = context.current_analyte
        return _history_result()

    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", fake_dispatch)
    current_user = _patient()
    response = await handle_message(
        OrchestratorRequest(
            message="giải thích chỉ số này",
            ui_context=UIContext(candidate_report_ref="12", candidate_analyte="WBC"),
        ),
        current_user=current_user,
        db=QuerySpyDb(),
        runtime=_runtime_with_ack(current_user),
    )
    assert response.status == ResponseStatus.SUCCESS
    assert captured == {"report_ref": "12", "analyte": "WBC"}
    assert response.data_type != DataType.BLOCKED
