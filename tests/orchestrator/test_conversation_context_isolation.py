"""Conversation state and Agent history remain scoped to one conversation."""

from __future__ import annotations

from types import SimpleNamespace

from langchain_core.messages import HumanMessage

from src.models.db import User
from src.models.orchestrator_schemas import IntentEnum
from src.orchestrator.agent import _recent_messages
from src.orchestrator.session_store import ConversationScopedSessionStore, bind_conversation
from src.services import conversation_repository


def _patient_and_conversations(db):
    patient = db.query(User).filter(User.username == "benhnhan").one()
    actor = SimpleNamespace(role="patient", user_id=patient.id, username=patient.username)
    first = conversation_repository.create_conversation(db, patient_id=patient.id)
    second = conversation_repository.create_conversation(db, patient_id=patient.id)
    return actor, first, second


def test_conversation_state_is_isolated_and_persisted(test_db):
    with test_db.session() as db:
        actor, first, second = _patient_and_conversations(db)
        store = ConversationScopedSessionStore()
        with bind_conversation(db, first):
            initial = store.acknowledge_onboarding(actor)
            store.update_after_turn(
                actor,
                initial,
                last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
                current_report_ref="41",
                current_analyte="WBC",
            )
        with bind_conversation(db, second):
            second_context = store.get_or_create(actor)
            assert second_context.current_report_ref is None
            assert second_context.current_analyte is None
        fresh_store = ConversationScopedSessionStore()
        with bind_conversation(db, first):
            restored = fresh_store.get_or_create(actor)
            assert restored.current_report_ref == "41"
            assert restored.current_analyte == "WBC"
            assert restored.onboarding_acknowledged is True


def test_agent_recent_messages_do_not_cross_conversations(test_db):
    with test_db.session() as db:
        actor, first, second = _patient_and_conversations(db)
        conversation_repository.append_message(db, conversation=first, role="user", content="Giải thích WBC")
        conversation_repository.append_message(db, conversation=second, role="user", content="Giải thích HbA1c")
        with bind_conversation(db, first):
            messages = _recent_messages(actor, "Nguồn ở đâu?")
        user_text = [message.content for message in messages if isinstance(message, HumanMessage)]
        assert "Giải thích WBC" in user_text
        assert "Giải thích HbA1c" not in user_text
        assert user_text[-1] == "Nguồn ở đâu?"
