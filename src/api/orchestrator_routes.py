from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.api.conversation_routes import resolve_conversation
from src.api.deps import CurrentUser, get_current_user
from src.models.db import get_db
from src.models.orchestrator_schemas import OrchestratorRequest, OrchestratorResponse
from src.orchestrator.service import acknowledge_onboarding, handle_message
from src.orchestrator.streaming import stream_sse_frames
from src.services.langfuse_tracing import chat_trace
from src.services.request_timing import get_current_timing

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.post("/message", response_model=OrchestratorResponse)
async def orchestrator_message(
    request: OrchestratorRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrchestratorResponse:
    conversation = resolve_conversation(
        db,
        current_user=current_user,
        conversation_id=request.conversation_id,
    )
    timing = get_current_timing()
    with chat_trace(request_id=timing.request_id if timing else None):
        return await handle_message(request, current_user=current_user, db=db, conversation=conversation)


@router.post("/message/stream", response_class=StreamingResponse)
async def orchestrator_message_stream(
    request: OrchestratorRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    # Giai hoi thoai TRUOC khi mo stream. Sau khi StreamingResponse bat dau, mot
    # HTTPException khong con doi duoc status code -- client da nhan 200 va se
    # thay stream dut giua chung thay vi mot loi 404 doc duoc.
    conversation = resolve_conversation(
        db,
        current_user=current_user,
        conversation_id=request.conversation_id,
    )
    return StreamingResponse(
        stream_sse_frames(request, current_user=current_user, db=db, conversation=conversation),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/onboarding/acknowledge", response_model=OrchestratorResponse)
async def orchestrator_onboarding_acknowledge(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrchestratorResponse:
    conversation = resolve_conversation(db, current_user=current_user, conversation_id=None)
    return acknowledge_onboarding(current_user, db=db, conversation=conversation)
