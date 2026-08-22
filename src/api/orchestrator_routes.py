from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, get_current_user
from src.models.db import get_db
from src.models.orchestrator_schemas import OrchestratorRequest, OrchestratorResponse
from src.orchestrator.service import acknowledge_onboarding, handle_message
from src.orchestrator.streaming import stream_sse_frames

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.post("/message", response_model=OrchestratorResponse)
async def orchestrator_message(
    request: OrchestratorRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OrchestratorResponse:
    return await handle_message(request, current_user=current_user, db=db)


@router.post("/message/stream", response_class=StreamingResponse)
async def orchestrator_message_stream(
    request: OrchestratorRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    return StreamingResponse(
        stream_sse_frames(request, current_user=current_user, db=db),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/onboarding/acknowledge", response_model=OrchestratorResponse)
async def orchestrator_onboarding_acknowledge(
    current_user: CurrentUser = Depends(get_current_user),
) -> OrchestratorResponse:
    return acknowledge_onboarding(current_user)
