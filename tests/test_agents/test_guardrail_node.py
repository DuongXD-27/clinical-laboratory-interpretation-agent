import pytest

from src.agents.nodes.guardrail_node import DEFAULT_DISCLAIMER, guardrail_node
from src.agents.state import AgentState
from src.services.medical_safety_validator import MedicalSafetyValidator
from src.services.template_loader import load_templates


@pytest.mark.asyncio
async def test_guardrail_passed():
    """Test trường hợp nội dung an toàn, không chứa từ khóa vi phạm."""
    mock_state: AgentState = {
        "summary": "Chỉ số đường huyết của bạn hơi cao. Bạn nên ăn uống điều độ.",
        "explanations": [{"explanation": "Glucose là lượng đường trong máu. Vui lòng tham khảo ý kiến bác sĩ."}],
        "disclaimer": "",
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
        "explanations": [{"explanation": "Bạn mắc bệnh mỡ máu. Hãy dùng thuốc ngay."}],
        "disclaimer": "Đã có disclaimer hợp lệ và đủ dài để không bị ghi đè.",
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
    # Trả về AIMessage thật thay vì object chỉ có `.content`: stub quá đơn giản
    # là lý do lỗi "đổ nguyên content block ra màn hình" từng lọt qua bộ test.
    from langchain_core.messages import AIMessage

    safe_text = "Chỉ số này cần được bác sĩ giải thích thêm."

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return AIMessage(content=safe_text)

    llm = FakeLLM()
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: llm)
    result = await guardrail_node({"summary": "Bạn nên uống thuốc này.", "disclaimer": ""})

    assert llm.calls == 1
    assert result["summary"] == safe_text
    assert result["guardrail_passed"] is False


@pytest.mark.asyncio
async def test_blank_retry_uses_template_fallback(monkeypatch):
    from langchain_core.messages import AIMessage

    class FakeLLM:
        def __init__(self):
            self.calls = 0

        async def ainvoke(self, _messages):
            self.calls += 1
            return AIMessage(content="   ")

    llm = FakeLLM()
    templates = load_templates()
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: llm)

    result = await guardrail_node({"summary": "Ban nen su dung thuoc nay.", "disclaimer": ""})

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
    result = await guardrail_node({"summary": "Ban nen su dung thuoc nay moi ngay.", "disclaimer": ""})

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


class _StubLLM:
    """LLM giả trả về đúng shape content mà nhà cung cấp thật trả."""

    def __init__(self, content):
        self._content = content

    async def ainvoke(self, _messages):
        from langchain_core.messages import AIMessage

        return AIMessage(content=self._content)


# Gemini trả content dưới dạng danh sách content block. `str(content)` sẽ đổ cả
# repr Python lẫn chữ ký nội bộ của model ra màn hình bệnh nhân — đã gặp thật ở
# bản chạy local ngày 12/08/2026 với chỉ số Creatinine.
GEMINI_CONTENT_BLOCKS = [
    {
        "type": "text",
        "text": "Creatinine là sản phẩm thải từ quá trình phân hủy mô cơ.",
        "extras": {"signature": "EtYwCtMwARFNMg+0tz777d+BJ9EBOsgF7"},
    }
]


@pytest.mark.asyncio
async def test_rewrite_reads_text_from_content_blocks():
    from src.agents.nodes.guardrail_node import rewrite_with_llm

    result = await rewrite_with_llm(_StubLLM(GEMINI_CONTENT_BLOCKS), "văn bản gốc")

    assert result == "Creatinine là sản phẩm thải từ quá trình phân hủy mô cơ."
    assert "signature" not in result
    assert "'type'" not in result


@pytest.mark.asyncio
async def test_rewrite_still_reads_plain_string_content():
    from src.agents.nodes.guardrail_node import rewrite_with_llm

    result = await rewrite_with_llm(_StubLLM("  Đoạn văn đã biên tập.  "), "văn bản gốc")

    assert result == "Đoạn văn đã biên tập."


@pytest.mark.asyncio
async def test_rewrite_drops_thinking_blocks():
    """Block suy luận nội bộ của model không được lọt ra ngoài."""
    from src.agents.nodes.guardrail_node import rewrite_with_llm

    content = [
        {"type": "thinking", "thinking": "Người dùng đang hỏi về creatinine..."},
        {"type": "text", "text": "Phần hiển thị cho người dùng."},
    ]

    result = await rewrite_with_llm(_StubLLM(content), "văn bản gốc")

    assert result == "Phần hiển thị cho người dùng."


@pytest.mark.asyncio
async def test_question_rewrite_reads_text_from_content_blocks():
    from src.agents.nodes.guardrail_node import rewrite_questions_with_llm

    content = [
        {
            "type": "text",
            "text": "- Chỉ số này có ý nghĩa gì?\n- Tôi cần theo dõi thêm gì?",
            "extras": {"signature": "abc123"},
        }
    ]

    result = await rewrite_questions_with_llm(_StubLLM(content), ["câu hỏi gốc"])

    assert result == ["Chỉ số này có ý nghĩa gì?", "Tôi cần theo dõi thêm gì?"]


@pytest.mark.asyncio
async def test_urea_retry_reuses_safe_grounding_then_falls_back_to_safe_facts(monkeypatch):
    from langchain_core.messages import AIMessage

    unsafe = "Ure máu tăng có thể do suy giảm chức năng bài tiết của thận."
    safe = "Ure là sản phẩm chuyển hóa của protein."

    class UnsafeRewriteLLM:
        def __init__(self):
            self.prompts = []

        async def ainvoke(self, messages):
            self.prompts.append(messages[0].content)
            return AIMessage(content=unsafe)

    llm = UnsafeRewriteLLM()
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: llm)
    result = await guardrail_node(
        {
            "indicators": [
                {
                    "name": "Urea",
                    "value": 7.9,
                    "unit": "mmol/L",
                    "status": "high",
                    "is_critical": False,
                    "explanation": unsafe,
                }
            ],
            "explanations": [
                {
                    "indicator_name": "Urea",
                    "status": "high",
                    "is_critical": False,
                    "explanation": unsafe,
                }
            ],
            "retrieved_contexts": [
                {
                    "indicator_name": "Urea",
                    "text": f"{unsafe} {safe}",
                    "source": "https://trusted.test/urea",
                    "sources": ["https://trusted.test/urea"],
                    "score": 0.9,
                }
            ],
            "disclaimer": "",
        }
    )

    explanation = result["explanations"][0]["explanation"]
    assert result["guardrail_passed"] is False
    assert all("có thể do" not in prompt.split("<context>", 1)[1] for prompt in llm.prompts)
    assert "Giá trị Urea là 7.9 mmol/L" in explanation
    assert "cao so với khoảng tham chiếu được hệ thống sử dụng" in explanation
    assert safe in explanation
    assert unsafe not in explanation
    assert explanation != load_templates().fallback_explanation
    assert MedicalSafetyValidator().validate(explanation) == []


@pytest.mark.asyncio
async def test_all_unsafe_grounding_without_llm_keeps_deterministic_facts(monkeypatch):
    unsafe = "Ure máu tăng có thể do nhiều nguyên nhân."
    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)

    result = await guardrail_node(
        {
            "indicators": [
                {
                    "name": "Urea",
                    "value": 7.9,
                    "unit": "mmol/L",
                    "status": "high",
                    "is_critical": False,
                    "explanation": unsafe,
                }
            ],
            "explanations": [
                {
                    "indicator_name": "Urea",
                    "status": "high",
                    "is_critical": False,
                    "explanation": unsafe,
                }
            ],
            "retrieved_contexts": [
                {
                    "indicator_name": "Urea",
                    "text": unsafe,
                    "source": "https://trusted.test/urea",
                    "sources": ["https://trusted.test/urea"],
                    "score": 0.9,
                }
            ],
            "disclaimer": "",
        }
    )

    explanation = result["explanations"][0]["explanation"]
    assert "Giá trị Urea là 7.9 mmol/L" in explanation
    assert "cao so với khoảng tham chiếu được hệ thống sử dụng" in explanation
    assert unsafe not in explanation
    assert MedicalSafetyValidator().validate(explanation) == []


@pytest.mark.asyncio
async def test_plt_policy_control_keeps_risk_oriented_explanation():
    risk_text = "Số lượng tiểu cầu giảm có thể làm tăng nguy cơ xuất huyết."
    result = await guardrail_node(
        {
            "indicators": [{"name": "PLT", "explanation": risk_text}],
            "explanations": [{"indicator_name": "PLT", "explanation": risk_text}],
            "disclaimer": "",
        }
    )

    assert result["guardrail_passed"] is True
    assert result["explanations"][0]["explanation"] == risk_text
    assert MedicalSafetyValidator().validate(risk_text) == []
