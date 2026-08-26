import pytest

from src.models.db import ROLE_PATIENT
from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorRequest,
    OrchestratorSessionContext,
    ReasonCode,
    ResponseStatus,
)
from src.orchestrator.intent_router import route_intent
from src.orchestrator.service import handle_message
from src.orchestrator.session_store import default_session_store
from src.services.auth import ROLE_GUEST


class DummyUser:
    def __init__(self, role=ROLE_PATIENT, user_id=999, username="test_patient"):
        self.role = role
        self.user_id = user_id
        self.username = username


class DummyDB:
    def scalar(self, *args, **kwargs):
        return 999


@pytest.mark.asyncio
async def test_patient_with_medical_context_vague_request():
    """Test 1: Patient with medical context saying 'Xem giúp em với' routes to EXPLAIN_CURRENT_RESULT."""
    session = OrchestratorSessionContext(
        session_id="test_sess_1",
        user_role=ROLE_PATIENT,
        onboarding_acknowledged=True,
        current_report_ref="101",
    )
    decision = await route_intent("Xem giúp em với", session, role=ROLE_PATIENT, has_medical_context=True)
    assert decision.intent == IntentEnum.EXPLAIN_CURRENT_RESULT


@pytest.mark.asyncio
async def test_guest_without_medical_context_vague_request():
    """Test 2: Guest / No medical context saying 'Xem giúp em với' does NOT force EXPLAIN_CURRENT_RESULT."""
    session = OrchestratorSessionContext(
        session_id="test_sess_2",
        user_role=ROLE_GUEST,
        onboarding_acknowledged=True,
    )
    # Mock LLM for fallback
    class MockLLM:
        async def ainvoke(self, prompt: str):
            return "SAFE_GENERAL"

    from _pytest.monkeypatch import MonkeyPatch

    from src.orchestrator import intent_router
    mp = MonkeyPatch()
    mp.setattr(intent_router, "get_llm", lambda: MockLLM())

    try:
        decision = await route_intent("Xem giúp em với", session, role=ROLE_GUEST, has_medical_context=False)
        assert decision.intent == IntentEnum.SAFE_GENERAL
    finally:
        mp.undo()


@pytest.mark.asyncio
async def test_safety_diagnosis_reassurance():
    """Test 3: 'Bạn chắc chắn tôi không bị bệnh chứ?' is caught by medical safety gate."""
    user = DummyUser(role=ROLE_PATIENT)
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    req = OrchestratorRequest(message="Bạn chắc chắn tôi không bị bệnh chứ?", client_request_id="safe-3")
    resp = await handle_message(req, current_user=user, db=DummyDB())

    assert resp.status == ResponseStatus.BLOCKED
    assert resp.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert resp.reason_code == ReasonCode.MEDICAL_DIAGNOSIS_REQUEST


@pytest.mark.asyncio
async def test_safety_personal_cause_request():
    """Test 4: 'Tại sao tôi lại bị chỉ số này cao?' is caught as MEDICAL_CAUSE_REQUEST."""
    user = DummyUser(role=ROLE_PATIENT)
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    req = OrchestratorRequest(message="Tại sao tôi lại bị chỉ số này cao?", client_request_id="safe-4")
    resp = await handle_message(req, current_user=user, db=DummyDB())

    assert resp.status == ResponseStatus.BLOCKED
    assert resp.intent == IntentEnum.UNSUPPORTED_OR_UNSAFE
    assert resp.reason_code == ReasonCode.MEDICAL_CAUSE_REQUEST


@pytest.mark.asyncio
async def test_educational_cause_allowed():
    """Test 5: Educational question 'Chỉ số WBC cao thường do nguyên nhân gì?' is allowed and routes to EXPLAIN_CURRENT_RESULT."""
    user = DummyUser(role=ROLE_PATIENT)
    default_session_store.get_or_create(user)
    default_session_store.acknowledge_onboarding(user)

    req = OrchestratorRequest(message="Chỉ số WBC cao thường do nguyên nhân gì?", client_request_id="edu-5")
    resp = await handle_message(req, current_user=user, db=DummyDB())

    assert resp.intent == IntentEnum.EXPLAIN_CURRENT_RESULT
    assert resp.reason_code != ReasonCode.MEDICAL_CAUSE_REQUEST
