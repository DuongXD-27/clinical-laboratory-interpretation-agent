from fastapi import APIRouter

from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Nhận phiếu xét nghiệm (JSON mô phỏng), trả kết quả giải thích.

    Khung API — chuyển request thành AgentState và trả response theo đúng
    schema đã chốt. Logic đối chiếu tham chiếu / RAG / guardrail / câu hỏi cho
    bác sĩ sẽ được cắm vào agent graph (src/agents/graph.py) bởi các node
    tương ứng; hiện tại các field đó trả về giá trị mặc định/rỗng.

    Không bắt Exception ở đây: lỗi ngoài dự kiến (bug, crash) nên để FastAPI
    trả 500 mặc định thay vì lộ chi tiết nội bộ (str(e)) ra client.
    """
    # TODO: thay bằng agent.ainvoke(initial_state) khi graph.py có đủ node
    # (parse -> reference check -> critical detect -> RAG -> personalize
    # -> guardrail -> generate_questions -> summary).
    initial_state = {
        "patient_age": request.patient_age,
        "patient_gender": request.patient_gender,
        "test_date": request.test_date,
        "language": request.language,
        "raw_indicators": [i.model_dump() for i in request.indicators],
    }

    indicators = [
        IndicatorResultSchema(
            name=i["name"],
            value=i["value"],
            unit=i["unit"],
            status="normal",
            is_abnormal=False,
            is_critical=False,
        )
        for i in initial_state["raw_indicators"]
    ]

    return AnalyzeResponse(indicators=indicators)
