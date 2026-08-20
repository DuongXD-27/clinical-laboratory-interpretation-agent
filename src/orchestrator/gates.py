from __future__ import annotations

from src.models.db import ROLE_DOCTOR, ROLE_PATIENT
from src.models.orchestrator_schemas import IntentEnum, OrchestratorSessionContext, ReasonCode
from src.services.auth import ROLE_GUEST


def onboarding_gate(context: OrchestratorSessionContext) -> ReasonCode | None:
    if not context.onboarding_acknowledged:
        return ReasonCode.ONBOARDING_REQUIRED
    return None


def role_admission_gate(current_user: object) -> ReasonCode | None:
    role = getattr(current_user, "role", None)
    if role in {ROLE_GUEST, ROLE_PATIENT}:
        return None
    if role == ROLE_DOCTOR:
        return ReasonCode.UNSUPPORTED_CAPABILITY
    return ReasonCode.AUTH_EXPIRED


def policy_gate(role: str, intent: IntentEnum) -> ReasonCode | None:
    if role == ROLE_GUEST and intent in {IntentEnum.VIEW_HISTORY, IntentEnum.ANALYZE_TREND}:
        return ReasonCode.UNSUPPORTED_CAPABILITY
    return None
