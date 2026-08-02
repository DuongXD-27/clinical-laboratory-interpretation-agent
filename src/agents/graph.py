from langgraph.graph import END, StateGraph

from src.agents.nodes.analyzer_node import analyzer_node
from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.guardrail_node import guardrail_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.agents.state import AgentState


def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Đăng ký các node hiện có
    graph.add_node("reference_range_checker", reference_range_checker_node)
    graph.add_node("critical_detector", detect_critical_values_node)
    graph.add_node("analyzer", analyzer_node)
    graph.add_node("guardrail", guardrail_node)

    # Cấu hình luồng chạy
    graph.set_entry_point("reference_range_checker")
    graph.add_edge("reference_range_checker", "critical_detector")
    graph.add_edge("critical_detector", "analyzer")
    graph.add_edge("analyzer", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()


agent = build_graph()
