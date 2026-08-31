"""Minimal SSE event stream around the existing orchestrator execution flow."""

from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import AsyncIterator
from contextlib import suppress
from datetime import UTC, datetime

from src.models.orchestrator_schemas import (
    MessageCompletedPayload,
    MessageStartedPayload,
    OrchestratorRequest,
    OrchestratorStreamEvent,
    ProgressPayload,
    ProgressStage,
    StreamErrorPayload,
    StreamEventType,
)
from src.orchestrator.service import OrchestratorRuntime, handle_message
from src.services.langfuse_tracing import chat_trace
from src.services.request_timing import get_current_timing

logger = logging.getLogger(__name__)

_SAFE_ERROR_MESSAGE = "Trợ lý chưa thể phản hồi lúc này. Vui lòng thử lại."


def encode_sse_event(event: OrchestratorStreamEvent) -> str:
    """Encode one validated public event using the SSE wire format."""

    return f"event: {event.event_type.value}\nid: {event.event_id}\ndata: {event.model_dump_json()}\n\n"


async def stream_message_events(
    request: OrchestratorRequest,
    *,
    current_user: object,
    db: object,
    runtime: OrchestratorRuntime | None = None,
    conversation: object | None = None,
) -> AsyncIterator[OrchestratorStreamEvent]:
    """Execute ``handle_message`` once and expose only patient-safe events."""

    turn_id = secrets.token_urlsafe(16)
    sequence = 0

    def build_event(event_type: StreamEventType, payload: object) -> OrchestratorStreamEvent:
        nonlocal sequence
        sequence += 1
        return OrchestratorStreamEvent(
            event_id=secrets.token_urlsafe(12),
            event_type=event_type,
            turn_id=turn_id,
            sequence=sequence,
            occurred_at=datetime.now(UTC),
            payload=payload,
        )

    yield build_event(StreamEventType.MESSAGE_STARTED, MessageStartedPayload())

    queue: asyncio.Queue[tuple[StreamEventType, object]] = asyncio.Queue(maxsize=1)

    async def publish_progress(stage: ProgressStage) -> None:
        await queue.put((StreamEventType.PROGRESS, ProgressPayload(stage=stage)))

    async def execute_existing_flow() -> None:
        try:
            response = await handle_message(
                request,
                current_user=current_user,
                db=db,
                runtime=runtime,
                progress_callback=publish_progress,
                conversation=conversation,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("orchestrator_stream_failed", extra={"turn_id": turn_id})
            await queue.put(
                (
                    StreamEventType.ERROR,
                    StreamErrorPayload(message=_SAFE_ERROR_MESSAGE),
                )
            )
        else:
            await queue.put(
                (
                    StreamEventType.MESSAGE_COMPLETED,
                    MessageCompletedPayload(response=response),
                )
            )

    task = asyncio.create_task(execute_existing_flow())
    try:
        while True:
            event_type, payload = await queue.get()
            yield build_event(event_type, payload)
            if event_type in {StreamEventType.MESSAGE_COMPLETED, StreamEventType.ERROR}:
                break
    finally:
        if not task.done():
            task.cancel()
        with suppress(asyncio.CancelledError):
            await task


async def stream_sse_frames(
    request: OrchestratorRequest,
    *,
    current_user: object,
    db: object,
    runtime: OrchestratorRuntime | None = None,
    conversation: object | None = None,
) -> AsyncIterator[str]:
    timing = get_current_timing()
    with chat_trace(request_id=timing.request_id if timing else None):
        async for event in stream_message_events(
            request,
            current_user=current_user,
            db=db,
            runtime=runtime,
            conversation=conversation,
        ):
            yield encode_sse_event(event)


__all__ = ["encode_sse_event", "stream_message_events", "stream_sse_frames"]
