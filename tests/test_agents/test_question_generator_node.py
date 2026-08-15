"""Node sinh câu hỏi + vị trí của nó trong graph.

Nhánh kiểm duyệt câu hỏi của guardrail tồn tại từ V2 nhưng luôn nhận danh sách
rỗng, nên chưa có bằng chứng nào cho thấy nó hoạt động đúng với nội dung thật.
Bộ test này coi nhánh đó là code mới.
"""

import pytest

from src.agents.graph import agent, build_graph
from src.agents.nodes.guardrail_node import guardrail_node
from src.agents.nodes.question_generator_node import question_generator_node

ABNORMAL_STATE = {
    "indicators": [
        {
            "name": "LDL-Cholesterol",
            "analyte_id": "ldl_cholesterol",
            "value": 4.2,
            "unit": "mmol/L",
            "reference_low": 0.0,
            "reference_high": 3.4,
            "status": "high",
        },
        {
            "name": "Kali",
            "analyte_id": "kali",
            "value": 7.1,
            "unit": "mmol/L",
            "reference_low": 3.5,
            "reference_high": 5.0,
            "status": "critical_high",
        },
    ]
}


def test_node_writes_texts_and_metadata_in_the_same_order():
    result = question_generator_node(ABNORMAL_STATE)

    texts = result["questions_for_doctor"]
    meta = result["doctor_question_meta"]

    assert len(texts) == len(meta) == 2
    assert [entry["display_order"] for entry in meta] == [0, 1]
    assert [entry["priority"] for entry in meta] == ["critical", "abnormal"]
    assert [entry["indicator_name"] for entry in meta] == ["Kali", "LDL-Cholesterol"]


def test_node_returns_empty_for_a_report_with_nothing_abnormal():
    state = {
        "indicators": [
            {
                "name": "Glucose",
                "analyte_id": "glucose",
                "value": 5.2,
                "unit": "mmol/L",
                "reference_low": 3.9,
                "reference_high": 6.4,
                "status": "normal",
            }
        ]
    }

    result = question_generator_node(state)

    assert result["questions_for_doctor"] == []
    assert result["doctor_question_meta"] == []


def test_node_handles_missing_indicators_key():
    result = question_generator_node({})

    assert result["questions_for_doctor"] == []


def test_node_never_raises_when_generation_fails(monkeypatch):
    """Câu hỏi là phần bổ sung giá trị, không phải phần cốt lõi.

    Người bệnh không được nhìn thấy màn hình lỗi chỉ vì phần câu hỏi không chạy.
    """

    def boom(*_args, **_kwargs):
        raise RuntimeError("bo mau hong")

    monkeypatch.setattr(
        "src.agents.nodes.question_generator_node.generate_questions",
        boom,
    )

    result = question_generator_node(ABNORMAL_STATE)

    assert result == {"questions_for_doctor": [], "doctor_question_meta": []}


def test_graph_runs_generate_questions_between_analyzer_and_guardrail():
    """Guardrail phải là lớp cuối cùng (ADR-004), nên câu hỏi sinh trước nó."""
    graph = build_graph()
    nodes = set(graph.get_graph().nodes)

    assert "generate_questions" in nodes

    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}

    assert ("analyzer", "generate_questions") in edges
    assert ("generate_questions", "guardrail") in edges
    assert ("analyzer", "guardrail") not in edges


@pytest.mark.asyncio
async def test_shipped_questions_pass_guardrail_untouched(monkeypatch):
    """Câu hỏi sinh từ bộ mẫu phải qua được guardrail nguyên văn.

    Nếu một câu mẫu bị guardrail chặn thì bệnh nhân sẽ nhận bộ dự phòng chung
    thay vì câu hỏi bám vào chỉ số của mình — đúng thứ chức năng này muốn tránh.
    Đây là lần đầu nhánh kiểm duyệt câu hỏi chạy với nội dung thật.
    """
    generated = question_generator_node(ABNORMAL_STATE)

    monkeypatch.setattr("src.agents.nodes.guardrail_node.get_llm", lambda: None)

    result = await guardrail_node(
        {
            "summary": "Có chỉ số cao hơn khoảng tham chiếu, bạn nên tham khảo ý kiến bác sĩ.",
            "explanations": [{"explanation": "Chỉ số cao hơn khoảng tham chiếu."}],
            "disclaimer": "Đây là thông tin giáo dục chung, không thay thế ý kiến bác sĩ.",
            "questions_for_doctor": generated["questions_for_doctor"],
        }
    )

    assert result["questions_for_doctor"] == generated["questions_for_doctor"]
    assert result["guardrail_passed"] is True


@pytest.mark.asyncio
async def test_full_graph_produces_questions_for_an_abnormal_report(monkeypatch):
    """Chạy cả graph thật để chắc node được nối đúng, không chỉ khai báo."""
    monkeypatch.setattr("src.agents.nodes.analyzer_node.get_llm", lambda: None)

    result = await agent.ainvoke(
        {
            "patient_age": 40,
            "patient_gender": "female",
            "test_date": "2026-08-13",
            "language": "vi",
            "raw_indicators": [
                {"name": "Kali", "value": 7.1, "unit": "mmol/L"},
            ],
        },
        {"configurable": {"thread_id": "test-questions-full-graph"}},
    )

    assert result["questions_for_doctor"], "phiếu có chỉ số nguy kịch phải có câu hỏi"
    assert len(result["questions_for_doctor"]) == len(result["doctor_question_meta"])


@pytest.mark.asyncio
async def test_full_graph_produces_no_questions_when_everything_is_normal(monkeypatch):
    monkeypatch.setattr("src.agents.nodes.analyzer_node.get_llm", lambda: None)

    result = await agent.ainvoke(
        {
            "patient_age": 30,
            "patient_gender": "male",
            "test_date": "2026-08-13",
            "language": "vi",
            "raw_indicators": [
                {"name": "Fasting plasma glucose", "value": 5.0, "unit": "mmol/L"},
            ],
        },
        {"configurable": {"thread_id": "test-questions-normal-only"}},
    )

    assert result["questions_for_doctor"] == []
