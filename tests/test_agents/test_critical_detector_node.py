import pytest

from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.agents.state import AgentState


@pytest.mark.asyncio
async def test_detect_critical_values_node():
    """Test critical value detector logic."""
    mock_state: AgentState = {
        "raw_indicators": [
            {"name": "Kali", "value": 2.0, "unit": "mmol/L"},        # Critical low
            {"name": "Glucose", "value": 30.5, "unit": "mmol/L"},    # Critical high
            {"name": "LDL-C", "value": 3.2, "unit": "mmol/L"},       # Normal
            {"name": "WBC", "value": 7.5, "unit": "10^9/L"},         # Unknown (not in thresholds)
        ]
    }

    result_state = await detect_critical_values_node(mock_state)

    indicators = result_state.get("indicators", [])

    # Kiểm tra số lượng indicator
    assert len(indicators) == 4

    # Kiểm tra Kali
    kali = next(ind for ind in indicators if ind["name"] == "Kali")
    assert kali["status"] == "critical_low"
    assert kali["is_critical"] is True

    # Kiểm tra Glucose
    glucose = next(ind for ind in indicators if ind["name"] == "Glucose")
    assert glucose["status"] == "critical_high"
    assert glucose["is_critical"] is True

    # Kiểm tra LDL-C (Không vi phạm ngưỡng nguy kịch -> giữ nguyên trạng thái khởi tạo 'unknown')
    ldl = next(ind for ind in indicators if ind["name"] == "LDL-C")
    assert ldl["status"] == "unknown"
    assert ldl.get("is_critical") is False

    # Kiểm tra WBC
    wbc = next(ind for ind in indicators if ind["name"] == "WBC")
    assert wbc["status"] == "unknown"
    assert wbc.get("is_critical") is False

    # Kiểm tra cờ tổng
    assert result_state.get("has_critical_values") is True

    # Kiểm tra mảng cảnh báo
    alerts = result_state.get("critical_alerts", [])
    assert len(alerts) == 2
    assert alerts[0]["indicator_name"] == "Kali"
    assert alerts[1]["indicator_name"] == "Glucose"


@pytest.mark.asyncio
async def test_potassium_unknown_from_reference_checker_can_still_be_critical():
    """Normal checker keeps pending Kali unknown; critical detector remains independent."""
    initial_state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Kali", "value": 7.0, "unit": "mmol/L"},
        ],
    }

    checked_state = await reference_range_checker_node(initial_state)
    checked_kali = checked_state["indicators"][0]
    assert checked_kali["status"] == "unknown"
    assert checked_kali["is_critical"] is False

    critical_state = await detect_critical_values_node({**initial_state, **checked_state})
    critical_kali = critical_state["indicators"][0]
    assert critical_kali["status"] == "critical_high"
    assert critical_kali["is_critical"] is True
    assert critical_state["has_critical_values"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [(2.5, "critical_low"), (6.5, "critical_high")],
)
async def test_potassium_exact_critical_boundaries_preserve_current_policy(value, expected_status):
    state: AgentState = {
        "raw_indicators": [
            {"name": "Potassium", "value": value, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)

    potassium = result["indicators"][0]
    assert potassium["status"] == expected_status
    assert potassium["is_critical"] is True
