from fastapi import APIRouter

from src.agents.graph import build_graph
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema

router = APIRouter()
agent = build_graph()

@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Nhận phiếu xét nghiệm (JSON mô phỏng), trả kết quả giải thích.

    Khung API — chuyển request thành AgentState và chạy qua các node (Graph).
    Không bắt Exception ở đây để FastAPI tự trả 500 nếu lỗi.
    """
    initial_state = {
        "patient_age": request.patient_age,
        "patient_gender": request.patient_gender,
        "test_date": request.test_date.isoformat(),
        "language": request.language,
        "raw_indicators": [i.model_dump() for i in request.indicators],
    }

    # Chạy qua luồng LangGraph
    final_state = await agent.ainvoke(initial_state)

    # Convert dữ liệu về Response Schema
    indicators = [
        IndicatorResultSchema(**ind)
        for ind in final_state.get("indicators", [])
    ]

    return AnalyzeResponse(
        indicators=indicators,
        has_critical_values=final_state.get("has_critical_values", False),
        critical_alerts=final_state.get("critical_alerts", []),
        guardrail_passed=final_state.get("guardrail_passed", True),
        disclaimer=final_state.get("disclaimer", ""),
        questions_for_doctor=final_state.get("questions_for_doctor", []),
        out_of_scope_indicators=final_state.get("out_of_scope_indicators", []),
        is_placeholder=False,
    )
