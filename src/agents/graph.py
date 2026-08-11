import inspect
from functools import wraps

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from src.agents.nodes.analyzer_node import analyzer_node
from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.guardrail_node import guardrail_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.agents.state import AgentState
from src.services.request_timing import timing_span


def ui_review_node(state: AgentState) -> dict:
    """
    Node đóng vai trò là điểm neo (Gate) để LangGraph ngắt luồng (interrupt).

    Thực tế node này không xử lý logic. LangGraph sẽ kích hoạt ngắt luồng
    (interrupt_before) ngay trước khi bước vào node này, giữ trạng thái chờ
    cho đến khi người dùng xác nhận và resume đồ thị (Human-in-the-loop).
    """
    return {}


def route_on_input(state: AgentState) -> str:
    """
    Điều kiện định tuyến (Conditional Edge) ngay tại Entry Point:
    - Nếu có bản nháp OCR (`ocr_drafts`) nhưng CHƯA ĐƯỢC DUYỆT (`is_ocr_reviewed` = False),
      luồng sẽ được chuyển hướng sang Gate chờ (`ui_review_gate`).
    - Nếu đã được duyệt hoặc nhập JSON bằng tay, tiếp tục luồng bình thường.
    """
    ocr_drafts = state.get("ocr_drafts")
    is_ocr_reviewed = state.get("is_ocr_reviewed", False)

    if ocr_drafts and not is_ocr_reviewed:
        return "ui_review_gate"

    return "reference_range_checker"


def _timed_node(metric_name, node):
    """Wrap a LangGraph node without changing its state contract."""

    @wraps(node)
    async def wrapped(state: AgentState) -> dict:
        with timing_span(metric_name):
            result = node(state)
            if inspect.isawaitable(result):
                return await result
            return result

    return wrapped


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Đăng ký các node
    graph.add_node(
        "reference_range_checker",
        _timed_node("analysis-reference-range", reference_range_checker_node),
    )
    graph.add_node(
        "critical_detector",
        _timed_node("analysis-critical-detector", detect_critical_values_node),
    )
    graph.add_node("analyzer", _timed_node("analysis-analyzer", analyzer_node))
    graph.add_node("guardrail", _timed_node("analysis-guardrail", guardrail_node))

    # Đăng ký Gate node chờ review (HITL)
    graph.add_node("ui_review_gate", _timed_node("analysis-ui-review-gate", ui_review_node))

    # Định tuyến ngay từ đầu bằng Conditional Entry Point
    graph.set_conditional_entry_point(
        route_on_input, {"ui_review_gate": "ui_review_gate", "reference_range_checker": "reference_range_checker"}
    )

    # Nối cạnh (Edges)
    # Sau khi người dùng resume luồng từ Gate, hệ thống sẽ chạy qua ui_review_node
    # và đi thẳng sang bước đối chiếu reference_range_checker
    graph.add_edge("ui_review_gate", "reference_range_checker")

    # Các cạnh thông thường
    graph.add_edge("reference_range_checker", "critical_detector")
    graph.add_edge("critical_detector", "analyzer")
    graph.add_edge("analyzer", "guardrail")
    graph.add_edge("guardrail", END)

    # Khởi tạo Checkpointer trong bộ nhớ để lưu State khi pause đồ thị
    memory = MemorySaver()

    # Compile graph, khai báo điểm ngắt (interrupt_before)
    return graph.compile(checkpointer=memory, interrupt_before=["ui_review_gate"])


agent = build_graph()
