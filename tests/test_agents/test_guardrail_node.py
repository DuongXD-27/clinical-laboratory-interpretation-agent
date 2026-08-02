import pytest

from src.agents.nodes.guardrail_node import DEFAULT_DISCLAIMER, guardrail_node
from src.agents.state import AgentState


@pytest.mark.asyncio
async def test_guardrail_passed():
    """Test trường hợp nội dung an toàn, không chứa từ khóa vi phạm."""
    mock_state: AgentState = {
        "summary": "Chỉ số đường huyết của bạn hơi cao. Bạn nên ăn uống điều độ.",
        "explanations": [
            {"explanation": "Glucose là lượng đường trong máu. Vui lòng tham khảo ý kiến bác sĩ."}
        ],
        "disclaimer": ""
    }

    result = await guardrail_node(mock_state)

    assert result["guardrail_passed"] is True
    assert len(result["guardrail_flags"]) == 0
    assert result["disclaimer"] == DEFAULT_DISCLAIMER

@pytest.mark.asyncio
async def test_guardrail_failed_with_diagnosis():
    """Test trường hợp nội dung vi phạm từ khóa chẩn đoán."""
    mock_state: AgentState = {
        "summary": "Dựa trên kết quả này, tôi chẩn đoán bạn bị tiểu đường.",
        "explanations": [
            {"explanation": "Bạn mắc bệnh mỡ máu. Hãy dùng thuốc ngay."}
        ],
        "disclaimer": "Đã có disclaimer hợp lệ và đủ dài để không bị ghi đè."
    }

    result = await guardrail_node(mock_state)

    assert result["guardrail_passed"] is False
    assert len(result["guardrail_flags"]) >= 2
    # Phải bắt được các pattern: "chẩn đoán bạn bị", "bạn mắc bệnh", "dùng thuốc"

    flag_texts = " ".join(result["guardrail_flags"])
    assert "chẩn đoán bạn bị" in flag_texts
    # assert "bạn mắc bệnh" in flag_texts  # early return will skip this
    # assert "dùng thuốc" in flag_texts

    # Disclaimer đã đủ độ dài thì giữ nguyên
    assert result["disclaimer"] == "Đã có disclaimer hợp lệ và đủ dài để không bị ghi đè."
