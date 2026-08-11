import logging
import time

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.agents.graph import build_graph
from src.api.deps import CurrentUser, get_current_user
from src.models.db import ROLE_PATIENT, get_db
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema
from src.services import history_repository

logger = logging.getLogger(__name__)

router = APIRouter()
agent = build_graph()


async def run_analysis(
    request: AnalyzeRequest,
    *,
    current_user: CurrentUser,
    db: Session | None = None,
    ocr_drafts: list[OCRIndicatorDraft] | None = None,
) -> AnalyzeResponse:
    """Run the shared analysis pipeline for manual or reviewed OCR input."""
    username = current_user.username
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

    final_state = await agent.ainvoke(initial_state, config=config)

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "analyze completed user=%s indicators=%d elapsed_ms=%.1f",
        username,
        len(request.indicators),
        elapsed_ms,
    )

    # Convert dữ liệu về Response Schema
    indicators = [IndicatorResultSchema(**ind) for ind in final_state.get("indicators", [])]

    response = AnalyzeResponse(
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

    # Chỉ bệnh nhân đã đăng nhập mới có lịch sử. Khách (user_id=None) và bác sĩ
    # đều đi tiếp bình thường, chỉ là không sinh bản ghi nào.
    if db is not None and current_user.role == ROLE_PATIENT and current_user.user_id is not None:
        saved = history_repository.save_report(
            db,
            patient_user_id=current_user.user_id,
            request=request,
            response=response,
            source="ocr" if ocr_drafts is not None else "manual",
        )
        response.saved_report_id = saved.id

    return response


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: AnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """Nhận dữ liệu nhập tay/mô phỏng và trả kết quả giải thích.

    Dữ liệu có nguồn OCR phải dùng `/ocr/confirm`; endpoint này không nhận
    review token và không được frontend OCR gọi trực tiếp.
    """
    return await run_analysis(request, current_user=current_user, db=db)
