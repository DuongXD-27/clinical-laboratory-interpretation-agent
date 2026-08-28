import pytest

from src.models.orchestrator_schemas import IntentEnum, OrchestratorRequest, ResponseStatus
from src.orchestrator.service import handle_message
from src.orchestrator.session_store import default_session_store


class DummyUser:
    def __init__(self, role="patient", user_id=999, username="test_patient"):
        self.role = role
        self.user_id = user_id
        self.username = username


@pytest.mark.asyncio
async def test_follow_up_analyte_memory(monkeypatch):
    """
    Test MEM-001: Short follow-up analyte selection.
    Turn 1: "Giải thích kết quả của tôi" (missing analyte -> NEEDS_INPUT)
    Turn 2: "WBC" (should resolve to EXPLAIN_CURRENT_RESULT due to memory)
    """
    # 1. Setup session and mock DB
    user = DummyUser()
    default_session_store.get_or_create(user)

    class DummyDB:
        def scalar(self, *args, **kwargs):
            return user.user_id

    # 2. Turn 1
    # User asks vague question without a report loaded -> NEEDS_INPUT
    default_session_store.acknowledge_onboarding(user)

    req1 = OrchestratorRequest(message="Giải thích kết quả của tôi", client_request_id="1")
    resp1 = await handle_message(req1, current_user=user, db=DummyDB())

    assert resp1.status == ResponseStatus.NEEDS_INPUT
    assert resp1.intent == IntentEnum.EXPLAIN_CURRENT_RESULT

    # Verify memory is saved
    updated_session = default_session_store.get_or_create(user)
    assert updated_session.conversation_state.pending_question == resp1.message

    # 3. Turn 2: Deterministic follow-up
    req2 = OrchestratorRequest(message="WBC", client_request_id="2")
    resp2 = await handle_message(req2, current_user=user, db=DummyDB())

    # "WBC" is deterministically resolved to EXPLAIN_CURRENT_RESULT with 1.0 confidence before LLM
    assert resp2.intent == IntentEnum.EXPLAIN_CURRENT_RESULT

    # 4. Turn 3: LLM follow-up receives pending_question in context
    prompt_received = None

    class MockLLM:
        async def ainvoke(self, prompt: str):
            nonlocal prompt_received
            prompt_received = prompt
            return "EXPLAIN_CURRENT_RESULT"

    from src.orchestrator import intent_router

    monkeypatch.setattr(intent_router, "get_llm", lambda: MockLLM())

    # Set pending question back for testing LLM prompt injection
    session = default_session_store.get_or_create(user)
    import time

    from src.models.orchestrator_schemas import ConversationState

    default_session_store.update_after_turn(
        user,
        session,
        last_intent=IntentEnum.EXPLAIN_CURRENT_RESULT,
        conversation_state=ConversationState(
            pending_question="Bạn muốn xem chỉ số nào?",
            pending_question_timestamp=time.time(),
        ),
    )

    # Free-form natural language that is not a plain keyword
    req3 = OrchestratorRequest(message="Tôi quan tâm đến chỉ số đầu tiên trong danh sách", client_request_id="3")
    await handle_message(req3, current_user=user, db=DummyDB())

    assert prompt_received is not None
    assert "pending_question':" in prompt_received
    assert "Bạn muốn xem chỉ số nào" in prompt_received
