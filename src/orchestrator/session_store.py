from __future__ import annotations

import secrets
from dataclasses import dataclass
from typing import Protocol

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorRole,
    OrchestratorSessionContext,
    UIContext,
)
from src.services.auth import ROLE_GUEST


class SessionStore(Protocol):
    def get_or_create(self, current_user: object) -> OrchestratorSessionContext:
        ...

    def save(self, current_user: object, context: OrchestratorSessionContext) -> None:
        ...

    def acknowledge_onboarding(self, current_user: object) -> OrchestratorSessionContext:
        ...


@dataclass
class _SessionRecord:
    context: OrchestratorSessionContext


class InMemorySessionStore:
    def __init__(self) -> None:
        self._records: dict[str, _SessionRecord] = {}
        self._patient_sessions: dict[int, str] = {}

    def _key_and_context_id(self, current_user: object) -> tuple[str, str, OrchestratorRole]:
        role = getattr(current_user, "role", "")
        if role == ROLE_GUEST:
            session_id = getattr(current_user, "session_id", None)
            if not isinstance(session_id, str) or not session_id:
                raise ValueError("guest session_id is required")
            return f"guest:{session_id}", session_id, OrchestratorRole.GUEST

        if role == ROLE_PATIENT:
            account_key = getattr(current_user, "user_id", None)
            if not isinstance(account_key, int):
                raise ValueError("patient user_id is required")
            session_id = self._patient_sessions.setdefault(account_key, secrets.token_urlsafe(16))
            return f"patient:{account_key}", session_id, OrchestratorRole.PATIENT

        raise ValueError("role is not admitted")

    def get_or_create(self, current_user: object) -> OrchestratorSessionContext:
        key, session_id, role = self._key_and_context_id(current_user)
        record = self._records.get(key)
        if record is not None:
            return record.context

        context = OrchestratorSessionContext.from_server(
            session_id=session_id,
            user_role=role,
        )
        self._records[key] = _SessionRecord(context=context)
        return context

    def save(self, current_user: object, context: OrchestratorSessionContext) -> None:
        key, _, _ = self._key_and_context_id(current_user)
        self._records[key] = _SessionRecord(context=context)

    def acknowledge_onboarding(self, current_user: object) -> OrchestratorSessionContext:
        context = self.get_or_create(current_user)
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=True,
            current_report_ref=context.current_report_ref,
            current_analyte=context.current_analyte,
            last_intent=context.last_intent,
            pending_ocr_review=context.pending_ocr_review,
            transient_ui_context=context.transient_ui_context,
        )
        self.save(current_user, updated)
        return updated

    def replace_pending_review(
        self,
        current_user: object,
        context: OrchestratorSessionContext,
        *,
        pending_ocr_review: bool,
    ) -> OrchestratorSessionContext:
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=context.onboarding_acknowledged,
            current_report_ref=context.current_report_ref,
            current_analyte=context.current_analyte,
            last_intent=context.last_intent,
            pending_ocr_review=pending_ocr_review,
            transient_ui_context=context.transient_ui_context,
        )
        self.save(current_user, updated)
        return updated

    def update_after_turn(
        self,
        current_user: object,
        context: OrchestratorSessionContext,
        *,
        last_intent: IntentEnum | None,
        current_report_ref: str | None = None,
        current_analyte: str | None = None,
        transient_ui_context: UIContext | None = None,
    ) -> OrchestratorSessionContext:
        updated = OrchestratorSessionContext.from_server(
            session_id=context.session_id,
            user_role=context.user_role,
            onboarding_acknowledged=context.onboarding_acknowledged,
            current_report_ref=current_report_ref or context.current_report_ref,
            current_analyte=current_analyte or context.current_analyte,
            last_intent=last_intent,
            pending_ocr_review=context.pending_ocr_review,
            transient_ui_context=transient_ui_context or context.transient_ui_context,
        )
        self.save(current_user, updated)
        return updated


default_session_store = InMemorySessionStore()
