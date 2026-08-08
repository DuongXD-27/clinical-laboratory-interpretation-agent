from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.api.deps import CurrentUser, get_current_user
from src.config import get_settings
from src.models.ocr_schemas import OCRConfirmRequest, OCRReviewResponse
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorInputSchema
from src.services.image_processor import ImageProcessor, ImageProcessorError
from src.services.ocr_review_gate import (
    OCRReviewGateError,
    prepare_review,
    validate_review,
)

router = APIRouter()


def _get_dependencies() -> tuple[ImageProcessor, VisionAdapter]:
    """Factory lỏng — dễ thay mock trong test."""
    return ImageProcessor(), VisionAdapter()


@router.post(
    "/ocr/upload",
    response_model=OCRReviewResponse,
    summary="Upload ảnh phiếu xét nghiệm, OCR trả bản nháp cần xác nhận",
    description=(
        "Bước 1 của luồng UI_Review (ADR-006): nhận ảnh, tiền xử lý, dùng Vision "
        "LLM đọc chỉ số rồi trả về bản nháp + confidence. Bản nháp KHÔNG được đưa "
        "vào AgentState — người dùng phải xác nhận/sửa ở UI rồi gọi /analyze."
    ),
)
async def ocr_upload(
    file: UploadFile = File(...),
    current_user: CurrentUser = Depends(get_current_user),
) -> OCRReviewResponse:
    processor, adapter = _get_dependencies()

    raw = await file.read()
    try:
        processed = processor.process(raw, filename=file.filename)
    except ImageProcessorError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from src.adapters.vision_adapter import image_to_data_url

    try:
        drafts = adapter.extract(image_to_data_url(processed.bytes, processed.mime_type))
    except VisionAdapterError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    prepared_drafts, review_token = prepare_review(
        drafts,
        username=current_user.username,
    )
    settings = get_settings()
    return OCRReviewResponse(
        source_image=file.filename or "upload",
        model_used=adapter.model,
        review_token=review_token,
        low_confidence_threshold=settings.ocr_low_confidence_threshold,
        expires_in_seconds=settings.ocr_review_token_expire_minutes * 60,
        metadata_hint={},
        indicators=prepared_drafts,
    )


@router.post(
    "/ocr/confirm",
    response_model=AnalyzeResponse,
    summary="Xác nhận thủ công bản nháp OCR rồi mới chạy phân tích",
)
async def ocr_confirm(
    request: OCRConfirmRequest,
    current_user: CurrentUser = Depends(get_current_user),
) -> AnalyzeResponse:
    """Server-side gate: rejects incomplete or forged OCR review evidence."""
    try:
        reviewed_drafts, included_inputs = validate_review(
            request.review_token,
            request.indicators,
            username=current_user.username,
        )
    except OCRReviewGateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    analyze_request = AnalyzeRequest(
        patient_age=request.patient_age,
        patient_gender=request.patient_gender,
        test_date=request.test_date,
        language=request.language,
        indicators=[IndicatorInputSchema(**item) for item in included_inputs],
    )

    # Local import avoids a module cycle while keeping one graph instance and
    # one response mapping for both manual and OCR flows.
    from src.api.routes import run_analysis

    return await run_analysis(
        analyze_request,
        username=current_user.username,
        ocr_drafts=reviewed_drafts,
    )
