import logging
import time

from fastapi import APIRouter, Depends

from src.agents.graph import build_graph
from src.api.deps import CurrentUser, get_current_user
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema
from src.services.request_timing import timing_span

logger = logging.getLogger(__name__)

router = APIRouter()
agent = build_graph()


async def run_analysis(
    request: AnalyzeRequest,
    *,
    username: str,
    ocr_drafts: list[OCRIndicatorDraft] | None = None,
) -> AnalyzeResponse:
    """Run the shared analysis pipeline for manual or reviewed OCR input."""
    initial_state = {
        "patient_age": request.patient_age,
        "patient_gender": request.patient_gender,
        "test_date": request.test_date.isoformat(),
        "language": request.language,
        "raw_indicators": [i.model_dump() for i in request.indicators],
    }
    if ocr_drafts is not None:
        # OCR input can only reach this branch through POST /ocr/confirm.
        initial_state["ocr_drafts"] = ocr_drafts
        initial_state["is_ocr_reviewed"] = True

    import uuid

    # Chạy qua luồng LangGraph — ghi log độ trễ làm baseline cho giám sát (V2)
    started_at = time.perf_counter()
    config = {"configurable": {"thread_id": uuid.uuid4().hex}}

    with timing_span("analysis-graph-total"):
        final_state = await agent.ainvoke(initial_state, config=config)

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "analyze completed user=%s indicators=%d elapsed_ms=%.1f",
        username,
        len(request.indicators),
        elapsed_ms,
    )

    with timing_span("analysis-response-map"):
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
            summary=final_state.get("summary", ""),
            is_placeholder=False,
        )


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """Nhận dữ liệu nhập tay/mô phỏng và trả kết quả giải thích.

    Dữ liệu có nguồn OCR phải dùng `/ocr/confirm`; endpoint này không nhận
    review token và không được frontend OCR gọi trực tiếp.
    """
    return await run_analysis(request, username=current_user.username)
