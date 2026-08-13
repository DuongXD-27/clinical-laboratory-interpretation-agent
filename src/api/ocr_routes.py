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
from src.services.reference_repository import (
    ReferenceRepository,
    ReferenceRepositoryError,
)
from src.services.request_timing import timing_span

router = APIRouter()

CONSENT_TEXT = (
    "Tôi xác nhận đây là dữ liệu mô phỏng, không phải phiếu xét nghiệm "
    "thật của tôi hay của người khác."
)


def _clean_source_filename(filename: str | None) -> str:
    """Chỉ giữ tên file, không lưu client-side path."""
    if not filename:
        return "upload"

    normalized = filename.replace("\\", "/")
    return normalized.rsplit("/", 1)[-1] or "upload"


def _get_dependencies() -> tuple[ImageProcessor, VisionAdapter]:
    """Khởi tạo OCR dependencies sau khi request vượt qua policy gates."""

    if not get_settings().google_api_key.strip():
        raise VisionAdapterError(
            "OCR chưa được cấu hình: thiếu GOOGLE_API_KEY trên backend."
        )

    with timing_span("image-processor-init"):
        processor = ImageProcessor()

    with timing_span("vision-client-init"):
        adapter = VisionAdapter()

    return processor, adapter


def _split_supported_inputs(
    included_inputs: list[dict],
) -> tuple[list[dict], list[str]]:
    """Tách chỉ số được hỗ trợ khỏi chỉ số ngoài thư viện tham chiếu."""

    try:
        repository = ReferenceRepository.from_default_files()
    except ReferenceRepositoryError:
        # Không làm hỏng OCR flow chỉ vì reference repository không khởi tạo
        # được ở bước pre-filter. Pipeline phía sau vẫn có guard riêng.
        return included_inputs, []

    supported: list[dict] = []
    out_of_scope: list[str] = []

    for item in included_inputs:
        name = str(item.get("name", "")).strip()

        if not name:
            continue

        canonical = repository.resolve_analyte(name)

        if canonical in repository.approved_analytes:
            supported.append(item)
        else:
            out_of_scope.append(name)

    return supported, list(dict.fromkeys(out_of_scope))


@router.get(
    "/ocr/policy",
    response_model=OCRUploadPolicyResponse,
    summary="Chính sách nhận ảnh hiện hành + danh sách ảnh mẫu",
)
async def ocr_policy() -> OCRUploadPolicyResponse:
    """Trả chính sách OCR công khai để frontend cấu hình upload."""

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
    # Không ghi file, không persistence vào DB, không log nội dung ảnh.
    with timing_span("ocr-file-read"):
        raw = await file.read()

    # ------------------------------------------------------------------
    # Gate 3: demo_only chỉ nhận ảnh mẫu
    # ------------------------------------------------------------------
    with timing_span("ocr-sample-policy-check"):
        known_sample = (
            is_known_sample(raw)
            if settings.ocr_upload_mode == "demo_only"
            else True
        )

    if (
        settings.ocr_upload_mode == "demo_only"
        and not known_sample
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
        with timing_span("ocr-preprocess"):
            processed = processor.process(
                raw,
                filename=file.filename,
            )
    except ImageProcessorError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    try:
        with timing_span("ocr-vision-extract"):
            drafts = await adapter.extract(
                processed.bytes,
                processed.mime_type,
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

    # source_image + confidence + raw_text được bind vào signed review
    # evidence. Client không được tự cung cấp lại provenance ở confirm.
    with timing_span("ocr-review-prepare"):
        prepared_drafts, review_token = prepare_review(
            drafts,
            username=current_user.username,
            source_image=source_image,
        )

    return OCRReviewResponse(
        source_image=source_image,
        model_used=getattr(
            adapter,
            "last_model",
            adapter.model,
        ),
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
        with timing_span("ocr-review-validate"):
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

    # Chỉ đưa analyte có reference support vào LangGraph.
    # Những analyte còn lại vẫn được báo cho người dùng dưới dạng
    # out_of_scope_indicators.
    (
        supported_inputs,
        out_of_scope_indicators,
    ) = _split_supported_inputs(included_inputs)

    if not supported_inputs:
        raise HTTPException(
            status_code=400,
            detail=(
                "Phiếu này chưa có chỉ số nào nằm trong "
                "danh sách hiện được hỗ trợ."
            ),
        )

    with timing_span("ocr-build-analysis-request"):
        analyze_request = AnalyzeRequest(
            patient_age=request.patient_age,
            patient_gender=request.patient_gender,
            test_date=request.test_date,
            language=request.language,
            indicators=[
                IndicatorInputSchema(**item)
                for item in supported_inputs
            ],
        )

    # Local import tránh module cycle và đảm bảo manual/OCR dùng chung
    # LangGraph, response mapping và persistence path.
    from src.api.routes import run_analysis

    response = await run_analysis(
        analyze_request,
        current_user=current_user,
        db=db,
        ocr_drafts=reviewed_drafts,
        ocr_source_filename=source_image,
    )

    response.out_of_scope_indicators = list(
        dict.fromkeys(
            [
                *response.out_of_scope_indicators,
                *out_of_scope_indicators,
            ]
        )
    )

    return response
