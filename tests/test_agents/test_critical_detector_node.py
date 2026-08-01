import pytest
from src.agents.state import AgentState
from src.agents.nodes.critical_detector_node import detect_critical_values_node

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
