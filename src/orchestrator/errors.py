from __future__ import annotations

from src.models.orchestrator_schemas import ReasonCode


class OrchestratorWrapperError(Exception):
    def __init__(self, reason_code: ReasonCode) -> None:
        self.reason_code = reason_code
        super().__init__(reason_code.value)
