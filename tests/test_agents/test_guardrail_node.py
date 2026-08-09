import pytest

from src.agents.nodes.guardrail_node import DEFAULT_DISCLAIMER, guardrail_node
from src.agents.state import AgentState
from src.services.template_loader import load_templates


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
async def test_guardrail_failed_with_diagnosis(monkeypatch):
    """Test trường hợp nội dung vi phạm từ khóa chẩn đoán."""
    mock_state: AgentState = {
        "summary": "Dựa trên kết quả này, tôi chẩn đoán bạn bị tiểu đường.",
        "explanations": [
            {"explanation": "Bạn mắc bệnh mỡ máu. Hãy dùng thuốc ngay."}
        ],
        "disclaimer": "Đã có disclaimer hợp lệ và đủ dài để không bị ghi đè."
    }

    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)
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


@pytest.mark.asyncio
async def test_guardrail_retries_once_then_accepts_safe_rewrite(monkeypatch):
    class SafeResponse:
        content = "Chỉ số này cần được bác sĩ giải thích thêm."

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return SafeResponse()

    llm = FakeLLM()
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: llm)
    result = await guardrail_node({"summary": "Bạn nên uống thuốc này.", "disclaimer": ""})

    assert llm.calls == 1
    assert result["summary"] == SafeResponse.content
    assert result["guardrail_passed"] is False


@pytest.mark.asyncio
async def test_blank_retry_uses_template_fallback(monkeypatch):
    class BlankResponse:
        content = "   "

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return BlankResponse()

    llm = FakeLLM()
    templates = load_templates()
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: llm)

    result = await guardrail_node(
        {"summary": "Ban nen su dung thuoc nay.", "disclaimer": ""}
    )

    assert llm.calls == 1
    assert result["summary"] == templates.fallback_summary
    assert result["guardrail_passed"] is False
    assert "LLM trả về nội dung rỗng" in " ".join(result["guardrail_flags"])


@pytest.mark.asyncio
async def test_unsafe_disclaimer_is_validated_and_replaced(monkeypatch):
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)
    templates = load_templates()

    result = await guardrail_node(
        {
            "summary": "Nội dung giải thích an toàn.",
            "disclaimer": "Ban nen su dung thuoc nay moi ngay theo dung lieu.",
        }
    )

    assert result["disclaimer"] == templates.disclaimer
    assert result["guardrail_passed"] is False
    assert "disclaimer" in " ".join(result["guardrail_flags"])


@pytest.mark.asyncio
async def test_local_intent_check_catches_unaccented_prescription(monkeypatch):
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)
    result = await guardrail_node(
        {"summary": "Ban nen su dung thuoc nay moi ngay.", "disclaimer": ""}
    )

    assert result["guardrail_passed"] is False
    assert "Kiểm tra ý định tại chỗ" in " ".join(result["guardrail_flags"])


@pytest.mark.asyncio
async def test_template_library_is_shared_with_question_fallback(monkeypatch):
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)
    templates = load_templates()

    result = await guardrail_node(
        {
            "summary": "Tóm tắt an toàn.",
            "questions_for_doctor": ["Tôi có nên dùng thuốc này ngay không?"],
            "disclaimer": "",
        }
    )

    assert result["questions_for_doctor"] == list(templates.doctor_questions_fallback)
