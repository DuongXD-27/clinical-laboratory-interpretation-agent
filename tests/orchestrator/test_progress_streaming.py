"""Canonical Agent progress-streaming contracts."""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.models.orchestrator_schemas import (
    DataType,
    ExplanationDataPayload,
    IntentEnum,
    MessageStartedPayload,
    OrchestratorRequest,
    OrchestratorResponse,
    OrchestratorStreamEvent,
    ProgressStage,
    ResponseStatus,
    StreamEventType,
)
from src.orchestrator.agent import AgentResult
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.orchestrator.session_store import InMemorySessionStore
from src.orchestrator.streaming import encode_sse_event, stream_message_events


def _actor_and_runtime():
    actor = SimpleNamespace(role="patient", user_id=7001, username="stream-patient")
    store = InMemorySessionStore()
    store.acknowledge_onboarding(actor)
    return actor, OrchestratorRuntime(session_store=store)


@pytest.mark.asyncio
async def test_service_emits_routing_then_response_composition(monkeypatch):
    actor, runtime = _actor_and_runtime()
    emitted = []
    response = OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message="Phản hồi an toàn.",
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation="Phản hồi an toàn."),
    )

    async def fake_agent(**_kwargs):
        return AgentResult(response, None, None, "agent_chat")

    async def capture(stage):
        emitted.append(stage)

    monkeypatch.setattr("src.orchestrator.agent.run_agent", fake_agent)
    result = await handle_message(
        OrchestratorRequest(message="xin chào"),
        current_user=actor,
        db=object(),
        runtime=runtime,
        progress_callback=capture,
    )
    assert result.status == ResponseStatus.SUCCESS
    assert emitted == [ProgressStage.ROUTING, ProgressStage.RESPONSE_COMPOSITION]


@pytest.mark.asyncio
async def test_stream_event_order_and_schema(monkeypatch):
    response = OrchestratorResponse(
        intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        status=ResponseStatus.SUCCESS,
        message="Xong.",
        data_type=DataType.EXPLANATION,
        data=ExplanationDataPayload(explanation="Xong."),
    )

    async def fake_handle(_request, **kwargs):
        await kwargs["progress_callback"](ProgressStage.ROUTING)
        return response

    monkeypatch.setattr("src.orchestrator.streaming.handle_message", fake_handle)
    events = [
        event
        async for event in stream_message_events(
            OrchestratorRequest(message="xin chào"), current_user=object(), db=object()
        )
    ]
    assert [event.event_type for event in events] == [
        StreamEventType.MESSAGE_STARTED,
        StreamEventType.PROGRESS,
        StreamEventType.MESSAGE_COMPLETED,
    ]
    assert [event.sequence for event in events] == [1, 2, 3]


def test_sse_frame_contains_only_public_fields():
    event = OrchestratorStreamEvent(
        event_id="evt-1",
        event_type=StreamEventType.MESSAGE_STARTED,
        turn_id="turn-1",
        sequence=1,
        occurred_at="2026-08-28T00:00:00Z",
        payload=MessageStartedPayload(),
    )
    frame = encode_sse_event(event)
    data_line = next(line for line in frame.splitlines() if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert set(payload) == {
        "contract_version",
        "event_id",
        "event_type",
        "turn_id",
        "sequence",
        "occurred_at",
        "payload",
    }
