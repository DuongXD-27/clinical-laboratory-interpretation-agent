from __future__ import annotations

import pytest

from src.agents.nodes import analyzer_node as analyzer_module
from src.agents.nodes.analyzer_node import ExplanationOutput, analyzer_node


class _HostileStructuredLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    async def ainvoke(self, _messages):
        return ExplanationOutput(explanation=self.text)


class _HostileLLM:
    def __init__(self, text: str) -> None:
        self.text = text

    def with_structured_output(self, _schema):
        return _HostileStructuredLLM(self.text)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("name", "analyte_id", "status", "unit", "hostile", "forbidden"),
    [
        (
            "HGB",
            "hgb",
            "low",
            "g/L",
            "HGB thấp nên bạn có thể bị khó thở.",
            "bạn có thể bị khó thở",
        ),
        (
            "RBC",
            "rbc",
            "normal",
            "10^12/L",
            "RBC bình thường nên cơ thể bạn được cung cấp oxy ổn định.",
            "cơ thể bạn được cung cấp oxy ổn định",
        ),
        (
            "HGB",
            "hgb",
            "low",
            "g/L",
            "Kết quả này cho thấy bạn bị thiếu máu.",
            "bạn bị thiếu máu",
        ),
        (
            "RBC",
            "rbc",
            "normal",
            "10^12/L",
            "Chỉ số này chứng tỏ cơ thể đang hoạt động bình thường.",
            "chứng tỏ cơ thể đang hoạt động bình thường",
        ),
    ],
)
async def test_analysis_path_removes_unsupported_patient_inferences(
    monkeypatch,
    name,
    analyte_id,
    status,
    unit,
    hostile,
    forbidden,
):
    monkeypatch.setattr(analyzer_module, "get_llm", lambda: _HostileLLM(hostile))
    monkeypatch.setattr(analyzer_module, "get_medical_knowledge_retriever", lambda: None)
    indicator = {
        "name": name,
        "analyte_id": analyte_id,
        "value": 100,
        "unit": unit,
        "status": status,
        "is_abnormal": status != "normal",
        "is_critical": False,
        "explanation": "",
    }

    result = await analyzer_node({"indicators": [indicator], "patient_gender": "female", "patient_age": 35})
    visible = result["indicators"][0]["explanation"]

    assert forbidden.casefold() not in visible.casefold()
    assert f"Kết quả {name} là 100 {unit}." in visible
    assert "không tự xác định bệnh, nguyên nhân hoặc triệu chứng" in visible
