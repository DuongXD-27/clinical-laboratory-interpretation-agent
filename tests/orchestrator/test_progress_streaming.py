"""TIP-CHAT-004 backend progress-streaming contract tests."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from src.api import orchestrator_routes
from src.api.deps import CurrentUser
from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    OrchestratorRequest,
    OrchestratorResponse,
    ProgressStage,
    ResponseStatus,
    StreamEventType,
    TrendDataPayload,
)
from src.models.schemas import TrendPointResponse, TrendResponse
from src.orchestrator.dispatcher import DispatchContext, WorkflowResult, dispatch_workflow
from src.orchestrator.intent_router import RouteDecision
from src.orchestrator.medical_context import ResolvedMedicalContext
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.orchestrator.streaming import encode_sse_event, stream_message_events


class NoDb:
    def __getattr__(self, name):
        raise AssertionError(f"unexpected DB access: {name}")


def _patient() -> CurrentUser:
    return CurrentUser("stream-patient", ROLE_PATIENT, user_id=7001)


def _runtime_with_ack(user: CurrentUser) -> OrchestratorRuntime:
    store = InMemorySessionStore()
    store.acknowledge_onboarding(user)
    return OrchestratorRuntime(session_store=store)


def _final_response() -> OrchestratorResponse:
    return OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message="Giải thích an toàn.",
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation="Giải thích an toàn.", sources=[]),
    )


async def _collect_events(*, runtime: OrchestratorRuntime | None = None):
    user = _patient()
    runtime = runtime or _runtime_with_ack(user)
    return [
        event
        async for event in stream_message_events(
            OrchestratorRequest(message="Giải thích WBC"),
            current_user=user,
            db=NoDb(),
            runtime=runtime,
        )
    ]


@pytest.mark.asyncio
async def test_started_progress_completed_order_schema_and_sequence(monkeypatch):
    async def fake_handle(*args, progress_callback=None, **kwargs):
        assert progress_callback is not None
        await progress_callback(ProgressStage.ROUTING)
        await progress_callback(ProgressStage.MEDICAL_CONTEXT)
        await progress_callback(ProgressStage.RESPONSE_COMPOSITION)
        return _final_response()

    monkeypatch.setattr("src.orchestrator.streaming.handle_message", fake_handle)
    events = await _collect_events()

    assert [event.event_type for event in events] == [
        StreamEventType.MESSAGE_STARTED,
        StreamEventType.PROGRESS,
        StreamEventType.PROGRESS,
        StreamEventType.PROGRESS,
        StreamEventType.MESSAGE_COMPLETED,
    ]
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert len({event.turn_id for event in events}) == 1
    assert events[0].turn_id
    terminals = [
        event for event in events if event.event_type in {StreamEventType.MESSAGE_COMPLETED, StreamEventType.ERROR}
    ]
    assert len(terminals) == 1
    completed = terminals[0]
    assert completed.event_type == StreamEventType.MESSAGE_COMPLETED
    assert OrchestratorResponse.model_validate(completed.payload.response.model_dump()) == _final_response()


@pytest.mark.asyncio
async def test_stream_error_is_terminal_and_does_not_expose_exception(monkeypatch):
    async def failing_handle(*args, progress_callback=None, **kwargs):
        assert progress_callback is not None
        await progress_callback(ProgressStage.ROUTING)
        raise RuntimeError("get_my_history patient_id=42 secret prompt route_confidence=0.71")

    monkeypatch.setattr("src.orchestrator.streaming.handle_message", failing_handle)
    events = await _collect_events()
    assert events[-1].event_type == StreamEventType.ERROR
    assert sum(event.event_type in {StreamEventType.MESSAGE_COMPLETED, StreamEventType.ERROR} for event in events) == 1
    serialized = "\n".join(event.model_dump_json() for event in events)
    for private_term in ("get_my_history", "patient_id", "secret prompt", "route_confidence"):
        assert private_term not in serialized


@pytest.mark.asyncio
async def test_service_emits_real_routing_context_and_composition_boundaries(monkeypatch):
    user = _patient()
    stages: list[ProgressStage] = []

    async def capture(stage: ProgressStage) -> None:
        stages.append(stage)

    async def fake_route(*args, **kwargs):
        assert stages == [ProgressStage.ROUTING]
        return RouteDecision(intent=IntentEnum.EXPLAIN_CURRENT_RESULT, route_confidence=1.0)

    def fake_resolve(**kwargs):
        assert stages == [ProgressStage.ROUTING, ProgressStage.MEDICAL_CONTEXT]
        return ResolvedMedicalContext(current_report_ref="report-1", current_analyte="WBC")

    async def fake_dispatch(*args, **kwargs):
        return WorkflowResult(
            status=ResponseStatus.SUCCESS,
            data=ExplanationDataPayload(explanation="WBC explanation", sources=[]),
            workflow_selected="private_workflow_name",
        )

    monkeypatch.setattr("src.orchestrator.service.route_intent", fake_route)
    monkeypatch.setattr("src.orchestrator.medical_context.resolve_medical_context", fake_resolve)
    monkeypatch.setattr("src.orchestrator.service.dispatch_workflow", fake_dispatch)
    monkeypatch.setattr(
        "src.orchestrator.response_composer.get_llm", lambda: (_ for _ in ()).throw(RuntimeError("offline"))
    )

    response = await handle_message(
        OrchestratorRequest(message="Giải thích WBC"),
        current_user=user,
        db=NoDb(),
        runtime=_runtime_with_ack(user),
        progress_callback=capture,
    )
    assert response.status == ResponseStatus.SUCCESS
    assert stages == [
        ProgressStage.ROUTING,
        ProgressStage.MEDICAL_CONTEXT,
        ProgressStage.RESPONSE_COMPOSITION,
    ]


@pytest.mark.asyncio
async def test_trend_dispatch_emits_longitudinal_only_when_retrieval_starts(monkeypatch):
    stages: list[ProgressStage] = []

    async def capture(stage: ProgressStage) -> None:
        stages.append(stage)

    trend = TrendDataPayload(
        trend=TrendResponse(
            analyte_canonical="WBC",
            display_name="WBC",
            canonical_unit="10^9/L",
            filter="latest5",
            result_count=3,
            trend_available=True,
            points=[
                TrendPointResponse(
                    report_id=index, test_date=date(2026, 8, index), value=float(index), assessment="normal"
                )
                for index in (1, 2, 3)
            ],
            observed_direction="increasing",
        )
    )

    monkeypatch.setattr("src.orchestrator.dispatcher._is_supported_analyte", lambda name: True)

    def fake_trend(*args, **kwargs):
        assert stages == [ProgressStage.LONGITUDINAL_RETRIEVAL]
        return trend

    monkeypatch.setattr("src.orchestrator.dispatcher.get_my_indicator_trend", fake_trend)
    result = await dispatch_workflow(
        IntentEnum.ANALYZE_TREND,
        DispatchContext(
            current_user=_patient(),
            db=NoDb(),
            current_report_ref="report-1",
            current_analyte="WBC",
            progress_callback=capture,
        ),
    )
    assert result.data == trend
    assert stages == [ProgressStage.LONGITUDINAL_RETRIEVAL]


@pytest.mark.asyncio
async def test_ordinary_explanation_does_not_emit_longitudinal_retrieval(monkeypatch):
    stages: list[ProgressStage] = []

    async def capture(stage: ProgressStage) -> None:
        stages.append(stage)

    indicator = SimpleNamespace(
        name="WBC",
        analyte_canonical="WBC",
        analyte_raw="WBC",
        explanation="WBC explanation",
        sources=[],
    )
    monkeypatch.setattr("src.orchestrator.dispatcher._is_supported_analyte", lambda name: True)
    monkeypatch.setattr(
        "src.orchestrator.dispatcher.get_my_report",
        lambda *args, **kwargs: SimpleNamespace(indicators=[indicator]),
    )
    result = await dispatch_workflow(
        IntentEnum.EXPLAIN_CURRENT_RESULT,
        DispatchContext(
            current_user=_patient(),
            db=NoDb(),
            current_report_ref="report-1",
            current_analyte="WBC",
            progress_callback=capture,
        ),
    )
    assert result.status == ResponseStatus.SUCCESS
    assert ProgressStage.LONGITUDINAL_RETRIEVAL not in stages


@pytest.mark.asyncio
async def test_safety_refusal_streams_one_valid_completed_response():
    user = _patient()
    events = [
        event
        async for event in stream_message_events(
            OrchestratorRequest(message="Kết quả này chứng minh tôi mắc bệnh gì?"),
            current_user=user,
            db=NoDb(),
            runtime=_runtime_with_ack(user),
        )
    ]
    assert [event.event_type for event in events] == [
        StreamEventType.MESSAGE_STARTED,
        StreamEventType.MESSAGE_COMPLETED,
    ]
    assert sum(event.event_type in {StreamEventType.MESSAGE_COMPLETED, StreamEventType.ERROR} for event in events) == 1
    response = events[-1].payload.response
    assert OrchestratorResponse.model_validate(response.model_dump()) == response
    assert response.status == ResponseStatus.BLOCKED


def test_sse_frame_contains_only_public_event_name_id_and_json(monkeypatch):
    async def fake_handle(*args, progress_callback=None, **kwargs):
        return _final_response()

    monkeypatch.setattr("src.orchestrator.streaming.handle_message", fake_handle)

    async def get_started():
        async for event in stream_message_events(
            OrchestratorRequest(message="hello"),
            current_user=_patient(),
            db=NoDb(),
            runtime=_runtime_with_ack(_patient()),
        ):
            return event
        raise AssertionError("stream emitted no event")

    import asyncio

    event = asyncio.run(get_started())
    frame = encode_sse_event(event)
    assert frame.startswith("event: message.started\nid: ")
    assert "\ndata: {" in frame
    assert frame.endswith("\n\n")
    for private_term in ("workflow_selected", "route_confidence", "session_id", "patient_id"):
        assert private_term not in frame


@pytest.mark.asyncio
async def test_streaming_endpoint_uses_sse_and_existing_endpoint_stays_json(client, monkeypatch):
    async def fake_handle(*args, progress_callback=None, **kwargs):
        if progress_callback is not None:
            await progress_callback(ProgressStage.ROUTING)
        return _final_response()

    monkeypatch.setattr("src.orchestrator.streaming.handle_message", fake_handle)
    monkeypatch.setattr(orchestrator_routes, "handle_message", fake_handle)

    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    regular = await client.post(
        "/api/v1/orchestrator/message",
        headers=headers,
        json={"message": "Giải thích WBC"},
    )
    assert regular.status_code == 200
    assert regular.headers["content-type"].startswith("application/json")
    assert OrchestratorResponse.model_validate(regular.json()) == _final_response()

    streamed = await client.post(
        "/api/v1/orchestrator/message/stream",
        headers=headers,
        json={"message": "Giải thích WBC"},
    )
    assert streamed.status_code == 200
    assert streamed.headers["content-type"].startswith("text/event-stream")
    assert "event: message.started" in streamed.text
    assert "event: progress" in streamed.text
    assert "event: message.completed" in streamed.text
    assert streamed.text.index("event: message.started") < streamed.text.index("event: message.completed")
