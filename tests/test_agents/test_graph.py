import pytest

from src.agents.graph import agent


@pytest.mark.asyncio
async def test_agent_basic_flow():
    result = await agent.ainvoke({"patient_age": 30, "patient_gender": "male", "raw_indicators": []})
    assert "indicators" in result


@pytest.mark.asyncio
async def test_agent_state_structure():
    result = await agent.ainvoke({"patient_age": 30, "patient_gender": "male", "raw_indicators": []})
    assert isinstance(result, dict)
    assert "guardrail_passed" in result
