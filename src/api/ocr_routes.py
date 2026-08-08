from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.api.deps import CurrentUser, get_current_user
from src.config import get_settings
from src.models.ocr_schemas import (
    OCRConfirmRequest,
    OCRReviewResponse,
    OCRSampleItem,
    OCRUploadPolicyResponse,
)
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorInputSchema
from src.services.image_processor import ImageProcessor, ImageProcessorError
from src.services.ocr_review_gate import (
    OCRReviewGateError,
    prepare_review,
    validate_review,
)
from src.services.ocr_sample_library import get_sample, is_known_sample, load_samples

router = APIRouter()

CONSENT_TEXT = (
    "Tôi xác nhận đây là dữ liệu mô phỏng, không phải phiếu xét nghiệm thật "
    "của tôi hay của người khác."
)


def _get_dependencies() -> tuple[ImageProcessor, VisionAdapter]:
    """Factory lỏng — dễ thay mock trong test."""
    return ImageProcessor(), VisionAdapter()


@router.get(
    "/ocr/policy",
    response_model=OCRUploadPolicyResponse,
    summary="Chính sách nhận ảnh hiện hành + danh sách ảnh mẫu",
)
async def ocr_policy() -> OCRUploadPolicyResponse:
    """Không yêu cầu đăng nhập: giao diện cần biết chính sách trước cả màn login.

    Chỉ trả về cấu hình chính sách (đã là thông tin công khai trên UI), không
    kèm dữ liệu người dùng nào.
    """
    settings = get_settings()
    mode = settings.ocr_upload_mode
    return OCRUploadPolicyResponse(
        mode=mode,
        upload_enabled=mode != "internal_only",
        consent_required=True,
        custom_image_allowed=mode == "open_with_consent",
        consent_text=CONSENT_TEXT,
        samples=[
            OCRSampleItem(
                sample_id=s.sample_id,
                label=s.label,
                description=s.description,
                size_bytes=s.size_bytes,
            )
            for s in load_samples()
        ],
    )


@router.get(
    "/ocr/samples/{sample_id}",
    summary="Tải một ảnh phiếu mẫu để thử OCR",
    response_class=FileResponse,
)
async def ocr_sample_image(sample_id: str) -> FileResponse:
    sample = get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Không có ảnh mẫu này")
    return FileResponse(sample.path, media_type="image/png", filename=f"{sample.sample_id}.png")


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
    consent_acknowledged: bool = Form(
        False,
        description="Người dùng đã tick xác nhận đây là dữ liệu mô phỏng",
    ),
    current_user: CurrentUser = Depends(get_current_user),
) -> OCRReviewResponse:
    settings = get_settings()

    # --- Lớp bảo vệ 1: feature flag tắt hẳn tính năng ---
    if settings.ocr_upload_mode == "internal_only":
        raise HTTPException(
            status_code=503,
            detail="Tính năng tải ảnh phiếu đang tạm tắt.",
        )

    # --- Lớp bảo vệ 2: consent bắt buộc, chặn ở SERVER ---
    # Checkbox ở giao diện chỉ là trải nghiệm; ai gọi thẳng API vẫn bỏ qua được.
    # Không có cờ này thì không đọc ảnh, dừng trước cả bước tiền xử lý.
    if not consent_acknowledged:
        raise HTTPException(
            status_code=400,
            detail=f"Cần xác nhận trước khi tải ảnh: {CONSENT_TEXT}",
        )

    # Ảnh chỉ tồn tại trong RAM suốt vòng đời request — không ghi ra đĩa, không
    # đưa vào DB, không log nội dung. Hết request là mất, đúng cam kết
    # "không lưu ảnh gốc" (V3).
    raw = await file.read()

    # --- Lớp bảo vệ 3: demo_only chỉ nhận đúng bộ ảnh mẫu ---
    if settings.ocr_upload_mode == "demo_only" and not is_known_sample(raw):
        raise HTTPException(
            status_code=403,
            detail=(
                "Bản demo công khai chỉ nhận ảnh phiếu mẫu có sẵn, không nhận "
                "ảnh tự tải lên. Vui lòng chọn một ảnh mẫu để thử."
            ),
        )

    # Dựng Vision client SAU khi qua hết cổng kiểm tra: request bị từ chối
    # không nên tốn công khởi tạo client gọi dịch vụ ngoài.
    processor, adapter = _get_dependencies()

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
