from langgraph.graph import END, StateGraph

from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.guardrail_node import guardrail_node
from src.agents.state import AgentState

def build_graph() -> StateGraph:
    graph = StateGraph(AgentState)

    # Đăng ký các node hiện có
    graph.add_node("critical_detector", detect_critical_values_node)
    graph.add_node("guardrail", guardrail_node)

    # Cấu hình luồng chạy (Tạm thời V0.1)
    graph.set_entry_point("critical_detector")
    graph.add_edge("critical_detector", "guardrail")
    graph.add_edge("guardrail", END)

    return graph.compile()


agent = build_graph()
