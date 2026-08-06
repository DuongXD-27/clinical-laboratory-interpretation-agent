import logging
import time

from fastapi import APIRouter, Depends

from src.agents.graph import build_graph
from src.api.deps import CurrentUser, get_current_user
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema

logger = logging.getLogger(__name__)

router = APIRouter()
agent = build_graph()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """Nhận phiếu xét nghiệm (JSON mô phỏng), trả kết quả giải thích.

    Khung API — chuyển request thành AgentState và chạy qua các node (Graph).
    Yêu cầu JWT hợp lệ (patient/doctor). Không bắt Exception ở đây — để
    handler chung trong main.py xử lý, tránh lộ chi tiết lỗi nội bộ ra client.
    """
    initial_state = {
        "patient_age": request.patient_age,
        "patient_gender": request.patient_gender,
        "test_date": request.test_date.isoformat(),
        "language": request.language,
        "raw_indicators": [i.model_dump() for i in request.indicators],
    }

    import uuid

    # Chạy qua luồng LangGraph — ghi log độ trễ làm baseline cho giám sát (V2)
    started_at = time.perf_counter()
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}
    
    final_state = await agent.ainvoke(initial_state, config=config)
    
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "analyze completed user=%s indicators=%d elapsed_ms=%.1f",
        current_user.username,
        len(request.indicators),
        elapsed_ms,
    )
    
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
