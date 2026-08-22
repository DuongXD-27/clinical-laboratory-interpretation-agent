"""Patient-safe progress observer used by the optional streaming transport."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from src.models.orchestrator_schemas import ProgressStage

ProgressCallback = Callable[[ProgressStage], Awaitable[None]]


async def emit_progress(callback: ProgressCallback | None, stage: ProgressStage) -> None:
    if callback is not None:
        await callback(stage)


__all__ = ["ProgressCallback", "emit_progress"]
