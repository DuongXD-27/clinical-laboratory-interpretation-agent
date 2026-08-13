from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.api.deps import CurrentUser, get_current_user
from src.config import get_settings
from src.models.db import get_db
from src.models.ocr_schemas import (
    OCRConfirmRequest,
    OCRReviewResponse,
    OCRSampleItem,
    OCRUploadPolicyResponse,
)
from src.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    IndicatorInputSchema,
)
from src.services.image_processor import (
    ImageProcessor,
    ImageProcessorError,
)
from src.services.ocr_review_gate import (
    OCRReviewGateError,
    prepare_review,
    validate_review,
)
from src.services.ocr_sample_library import (
    get_sample,
    is_known_sample,
    load_samples,
)

router = APIRouter()

CONSENT_TEXT = (
    "Tôi xác nhận đây là dữ liệu mô phỏng, không phải phiếu xét nghiệm "
    "thật của tôi hay của người khác."
)


def _clean_source_filename(filename: str | None) -> str:
    if not filename:
        return "upload"

    normalized = filename.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or "upload"


def _get_dependencies() -> tuple[ImageProcessor, VisionAdapter]:
    """Factory lỏng — dễ thay mock trong test."""

    if not get_settings().openrouter_api_key.strip():
        raise VisionAdapterError(
            "OCR chưa được cấu hình: thiếu OPENROUTER_API_KEY trên backend."
        )

    return ImageProcessor(), VisionAdapter()


@router.get(
    "/ocr/policy",
    response_model=OCRUploadPolicyResponse,
    summary="Chính sách nhận ảnh hiện hành + danh sách ảnh mẫu",
)
async def ocr_policy() -> OCRUploadPolicyResponse:
    """Trả cấu hình OCR public để UI biết policy trước khi upload."""

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
                sample_id=sample.sample_id,
                label=sample.label,
                description=sample.description,
                size_bytes=sample.size_bytes,
            )
            for sample in load_samples()
        ],
    )


@router.get(
    "/ocr/samples/{sample_id}",
    summary="Tải một ảnh phiếu mẫu để thử OCR",
    response_class=FileResponse,
)
async def ocr_sample_image(
    sample_id: str,
) -> FileResponse:
    sample = get_sample(sample_id)

    if sample is None:
        raise HTTPException(
            status_code=404,
            detail="Không có ảnh mẫu này",
        )

    return FileResponse(
        sample.path,
        media_type="image/png",
        filename=f"{sample.sample_id}.png",
    )


@router.post(
    "/ocr/upload",
    response_model=OCRReviewResponse,
    summary="Upload ảnh phiếu xét nghiệm, OCR trả bản nháp cần xác nhận",
    description=(
        "Bước 1 của luồng UI_Review (ADR-006): nhận ảnh, tiền xử lý, "
        "dùng Vision LLM đọc chỉ số rồi trả về bản nháp + confidence. "
        "Bản nháp chưa được đưa vào AgentState. Người dùng phải xác nhận "
        "hoặc sửa rồi gọi /ocr/confirm."
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

    # ------------------------------------------------------------------
    # Gate 1: feature flag
    # ------------------------------------------------------------------
    if settings.ocr_upload_mode == "internal_only":
        raise HTTPException(
            status_code=503,
            detail="Tính năng tải ảnh phiếu đang tạm tắt.",
        )

    # ------------------------------------------------------------------
    # Gate 2: consent bắt buộc ở server
    # ------------------------------------------------------------------
    if not consent_acknowledged:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cần xác nhận trước khi tải ảnh: {CONSENT_TEXT}"
            ),
        )

    # Ảnh gốc chỉ tồn tại trong RAM trong vòng đời request.
    # Không ghi file, không persistence vào DB, không log nội dung.
    raw = await file.read()

    # ------------------------------------------------------------------
    # Gate 3: public demo chỉ cho phép ảnh mẫu
    # ------------------------------------------------------------------
    if (
        settings.ocr_upload_mode == "demo_only"
        and not is_known_sample(raw)
    ):
        raise HTTPException(
            status_code=403,
            detail=(
                "Bản demo công khai chỉ nhận ảnh phiếu mẫu có sẵn, "
                "không nhận ảnh tự tải lên. "
                "Vui lòng chọn một ảnh mẫu để thử."
            ),
        )

    # Không khởi tạo external Vision client trước khi request vượt qua
    # toàn bộ policy gates.
    try:
        processor, adapter = _get_dependencies()
    except VisionAdapterError as exc:
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        ) from exc

    try:
        processed = processor.process(
            raw,
            filename=file.filename,
        )
    except ImageProcessorError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    from src.adapters.vision_adapter import image_to_data_url

    try:
        drafts = adapter.extract(
            image_to_data_url(
                processed.bytes,
                processed.mime_type,
            )
        )
    except VisionAdapterError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    if not drafts:
        raise HTTPException(
            status_code=422,
            detail=(
                "Không tìm thấy chỉ số xét nghiệm trong ảnh. "
                "Hãy dùng ảnh chụp rõ toàn bộ phiếu xét nghiệm, "
                "không dùng ảnh chụp màn hình của ứng dụng."
            ),
        )

    source_image = _clean_source_filename(file.filename)

    # Quan trọng:
    # source_image được bind vào signed review evidence cùng drafts/user.
    # /ocr/confirm sẽ lấy lại giá trị này từ token, không tin filename
    # do client tự gửi sau đó.
    prepared_drafts, review_token = prepare_review(
        drafts,
        username=current_user.username,
        source_image=source_image,
    )

    return OCRReviewResponse(
        source_image=source_image,
        model_used=adapter.model,
        review_token=review_token,
        low_confidence_threshold=(
            settings.ocr_low_confidence_threshold
        ),
        expires_in_seconds=(
            settings.ocr_review_token_expire_minutes * 60
        ),
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
    db: Session = Depends(get_db),
) -> AnalyzeResponse:
    """Server-side gate chặn OCR review thiếu hoặc bị giả mạo."""

    try:
        (
            reviewed_drafts,
            included_inputs,
            source_image,
        ) = validate_review(
            request.review_token,
            request.indicators,
            username=current_user.username,
        )
    except OCRReviewGateError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    analyze_request = AnalyzeRequest(
        patient_age=request.patient_age,
        patient_gender=request.patient_gender,
        test_date=request.test_date,
        language=request.language,
        indicators=[
            IndicatorInputSchema(**item)
            for item in included_inputs
        ],
    )

    # Local import tránh module cycle và đảm bảo manual/OCR cùng dùng
    # một LangGraph instance + một response/persistence path.
    from src.api.routes import run_analysis

    return await run_analysis(
        analyze_request,
        current_user=current_user,
        db=db,
        ocr_drafts=reviewed_drafts,
        ocr_source_filename=source_image,
    )
