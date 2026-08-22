import pytest
from src.orchestrator.intent_router import _deterministic_route
from src.models.orchestrator_schemas import IntentEnum, ReasonCode

def test_safe_general_routing():
    for greeting in ["Chào bạn", "Chào em", "Xin chào", "Hello", "Hi", "Cảm ơn", "Bạn làm được gì?", "Trợ lý này giúp gì được cho tôi?", "Tôi nên bắt đầu từ đâu?"]:
        route = _deterministic_route(greeting)
        assert route is not None, f"Expected {greeting} to be routed"
        assert route.intent == IntentEnum.SAFE_GENERAL, f"Expected SAFE_GENERAL for {greeting}"

def test_medical_requests_still_blocked():
    for blocked in ["Tôi bị bệnh gì?", "Chẩn đoán cho tôi", "Tại sao chỉ số này cao?", "Tôi nên uống thuốc gì?", "Điều trị thế nào?", "HbA1c của tôi là 7.2, có sao không?"]:
        route = _deterministic_route(blocked)
        if route is not None:
            assert route.intent != IntentEnum.SAFE_GENERAL

def test_raw_medical_value_contract():
    # If the user provides a raw medical value, it should not be SAFE_GENERAL
    # It might fall back to LLM or be blocked, but must not be SAFE_GENERAL
    route = _deterministic_route("HbA1c của tôi là 7.2")
    assert route is None or route.intent != IntentEnum.SAFE_GENERAL
