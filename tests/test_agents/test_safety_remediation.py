from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage

from src.agents.nodes import guardrail_node as guardrail_module
from src.agents.nodes.guardrail_node import guardrail_node, rewrite_with_llm
from src.services.medical_safety_assets import (
    GENERATION_SAFETY_CONTRACT,
)
from src.services.medical_safety_validator import MedicalSafetyValidator
from src.services.template_loader import load_templates


def test_safe_01_and_05_generation_contract_covers_actual_failures():
    assert "NORMAL chỉ có nghĩa là giá trị nằm trong khoảng tham chiếu" in GENERATION_SAFETY_CONTRACT
    assert 'Không gọi giá trị là "mức tối ưu"' in GENERATION_SAFETY_CONTRACT
    assert "không khẳng định tim, gan, thận, miễn dịch" in GENERATION_SAFETY_CONTRACT
    assert (
        "mọi triệu chứng, ảnh hưởng, liên hệ hoặc nội dung y khoa phải được nêu trực tiếp trong context"
        in GENERATION_SAFETY_CONTRACT
    )
    assert "Context không nêu thì phải bỏ" in GENERATION_SAFETY_CONTRACT
    assert "không dùng kiến thức sẵn có của mô hình" in GENERATION_SAFETY_CONTRACT
    assert 'Giữ nguyên ngôn ngữ điều kiện của context như "có thể"' in GENERATION_SAFETY_CONTRACT


@pytest.mark.parametrize(
    "unsafe_text",
    [
        "Nồng độ kali trong máu đang ở mức tối ưu.",
        "Mức kali này đảm bảo hoạt động điện của tim diễn ra bình thường.",
        "Kết quả cho thấy tình trạng miễn dịch của bệnh nhân đang ở mức ổn định.",
        "Kết quả cho thấy không có dấu hiệu của viêm nhiễm.",
        "Kết quả cho thấy không có dấu hiệu nhiễm trùng.",
        "Kết quả cho thấy không có vấn đề liên quan đến bạch cầu.",
        "Chức năng thận của bệnh nhân đang bình thường.",
        "Kali máu bình thường có thể không gây ra triệu chứng hay ảnh hưởng gì đến cơ thể.",
        "Kết quả bình thường không gây ra triệu chứng.",
    ],
)
def test_safe_02_validator_rejects_actual_disease_exclusion_and_physiology_spans(unsafe_text):
    assert MedicalSafetyValidator().validate(unsafe_text)


@pytest.mark.parametrize(
    "warning",
    [
        "CẢNH BÁO: Potassium tăng tới ngưỡng nguy kịch (6.5 > 6.1 mmol/L).",
        "CẢNH BÁO: Fasting plasma glucose giảm tới ngưỡng nguy kịch (54.9475495 < 55 mg/dL). Yêu cầu can thiệp y tế.",
    ],
)
def test_safe_04_validator_does_not_overblock_deterministic_critical_warnings(warning):
    assert MedicalSafetyValidator().validate(warning) == []


@pytest.mark.asyncio
async def test_safe_02_guardrail_rejects_known_wbc_false_negative(monkeypatch):
    unsafe = (
        "Kết quả này cho thấy tình trạng miễn dịch của bệnh nhân đang ở mức ổn định "
        "và không có dấu hiệu của viêm nhiễm hay các vấn đề liên quan đến bạch cầu."
    )
    monkeypatch.setattr(guardrail_module, "get_llm", lambda: None)

    result = await guardrail_node(
        {
            "indicators": [{"name": "WBC", "explanation": unsafe}],
            "explanations": [{"indicator_name": "WBC", "explanation": unsafe}],
            "disclaimer": "",
        }
    )

    assert result["guardrail_passed"] is False
    assert result["indicators"][0]["explanation"] == load_templates().fallback_explanation
    assert "khong co dau hieu" in " ".join(result["guardrail_flags"])


@pytest.mark.asyncio
async def test_safe_05_rewrite_contract_forbids_new_unsupported_fpg_content():
    class CapturingLLM:
        def __init__(self):
            self.prompt = ""

        async def ainvoke(self, messages):
            self.prompt = messages[0].content
            return AIMessage(
                content=(
                    "Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình. "
                    "Context mô tả run rẩy có thể liên quan đến đường huyết thấp."
                )
            )

    llm = CapturingLLM()
    result = await rewrite_with_llm(
        llm,
        "Đường huyết thấp có thể gây run rẩy, mệt mỏi và ảnh hưởng sức khỏe nếu không xử lý kịp thời.",
        "Ý nghĩa khi giảm thấp: Context chỉ mô tả triệu chứng run rẩy.",
    )

    assert "Không thêm định nghĩa chỉ số, triệu chứng" in llm.prompt
    assert "Context chỉ mô tả triệu chứng run rẩy" in llm.prompt
    assert "không được theo dõi và xử lý kịp thời" not in result
    assert "mệt mỏi" not in result
    assert "run rẩy" in result


@pytest.mark.asyncio
async def test_safe_06_disclaimer_remains_present(monkeypatch):
    monkeypatch.setattr(guardrail_module, "get_llm", lambda: None)

    result = await guardrail_node({"summary": "Nội dung an toàn.", "disclaimer": ""})

    assert result["disclaimer"] == load_templates().disclaimer
