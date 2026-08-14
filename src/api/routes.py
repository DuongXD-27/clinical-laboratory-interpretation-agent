import logging
import time
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.agents.graph import build_graph
from src.api.deps import CurrentUser, get_current_user
from src.models.db import ROLE_PATIENT, get_db
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    IndicatorResultSchema,
)
from src.services import history_repository
from src.services.lab_history_service import save_analyzed_report
from src.services.question_templates import (
    GeneratedQuestion,
    reconcile_after_guardrail,
)
from src.services.request_timing import timing_span

logger = logging.getLogger(__name__)

router = APIRouter()
agent = build_graph()


async def run_analysis(
    request: AnalyzeRequest,
    *,
    current_user: CurrentUser,
    db: Session | None = None,
    ocr_drafts: list[OCRIndicatorDraft] | None = None,
    ocr_source_filename: str | None = None,
) -> AnalyzeResponse:
    """Run shared analysis pipeline for manual or reviewed OCR input.

    Persistence rule:
    - authenticated patient -> save report
    - doctor                -> do not save patient history
    - guest                 -> do not create any DB row
    """

    username = current_user.username

    initial_state = {
        "patient_age": request.patient_age,
        "patient_gender": request.patient_gender,
        "test_date": request.test_date.isoformat(),
        "language": request.language,
        "raw_indicators": [
            indicator.model_dump()
            for indicator in request.indicators
        ],
    }

    if ocr_drafts is not None:
        # OCR data may only reach this branch after the review/confirm flow.
        initial_state["ocr_drafts"] = ocr_drafts
        initial_state["is_ocr_reviewed"] = True

    # Một analysis invocation dùng thread_id riêng để LangGraph không chia sẻ
    # state ngoài ý muốn giữa các request.
    config = {
        "configurable": {
            "thread_id": uuid.uuid4().hex,
        }
    }

    started_at = time.perf_counter()

    with timing_span("analysis-graph-total"):
        final_state = await agent.ainvoke(
            initial_state,
            config=config,
        )

    elapsed_ms = (time.perf_counter() - started_at) * 1000

    logger.info(
        "analyze completed user=%s indicators=%d elapsed_ms=%.1f",
        username,
        len(request.indicators),
        elapsed_ms,
    )

    # Chỉ map kết quả ở span này.
    # KHÔNG return tại đây vì patient persistence còn nằm phía dưới.
    with timing_span("analysis-response-map"):
        indicators = [
            IndicatorResultSchema(**indicator)
            for indicator in final_state.get("indicators", [])
        ]

        response = AnalyzeResponse(
            indicators=indicators,
            has_critical_values=final_state.get(
                "has_critical_values",
                False,
            ),
            critical_alerts=final_state.get(
                "critical_alerts",
                [],
            ),
            guardrail_passed=final_state.get(
                "guardrail_passed",
                True,
            ),
            disclaimer=final_state.get(
                "disclaimer",
                "",
            ),
            questions_for_doctor=final_state.get(
                "questions_for_doctor",
                [],
            ),
            out_of_scope_indicators=final_state.get(
                "out_of_scope_indicators",
                [],
            ),
            summary=final_state.get(
                "summary",
                "",
            ),
            is_placeholder=False,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------
    #
    # Chỉ patient authenticated mới được tạo history.
    #
    # guest:
    #   user_id is None -> không tạo row
    #
    # doctor:
    #   role != patient -> không tạo patient history
    #
    # Đây là gate ở application layer; DB phía dưới cũng bắt buộc
    # lab_reports.patient_id NOT NULL -> users.id.
    if (
        db is not None
        and current_user.role == ROLE_PATIENT
        and current_user.user_id is not None
    ):
        # Ghép danh sách câu hỏi SAU guardrail trở lại metadata lúc sinh, để lưu
        # được mức ưu tiên và nối câu hỏi về đúng dòng chỉ số. Guardrail có thể
        # đã viết lại từng câu hoặc thay cả bộ bằng câu dự phòng.
        questions = reconcile_after_guardrail(
            response.questions_for_doctor,
            [
                GeneratedQuestion(
                    text="",
                    priority=str(meta.get("priority") or "abnormal"),
                    display_order=int(meta.get("display_order") or 0),
                    analyte_id=meta.get("analyte_id"),
                    indicator_name=meta.get("indicator_name"),
                )
                for meta in final_state.get("doctor_question_meta", [])
            ],
        )

        saved_report = history_repository.save_report(
            db,
            patient_id=current_user.user_id,
            request=request,
            response=response,
            questions=questions,
            ocr_drafts=ocr_drafts,
            ocr_source_filename=ocr_source_filename,
        )

        response.saved_report_id = saved_report.id

    return response


@router.post(
    "/analyze",
    response_model=AnalyzeResponse,
)
async def analyze(
    request: AnalyzeRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """Phân tích dữ liệu xét nghiệm nhập tay/mô phỏng.

    Dữ liệu từ OCR phải đi qua `/ocr/confirm`; endpoint này không nhận
    review token và frontend OCR không được gọi trực tiếp endpoint này.
    """

    return await run_analysis(
        request,
        current_user=current_user,
        db=db,
    )
