from fastapi import APIRouter, File, HTTPException, UploadFile

from src.adapters.vision_adapter import VisionAdapter, VisionAdapterError
from src.models.ocr_schemas import OCRReviewResponse
from src.services.image_processor import ImageProcessor, ImageProcessorError

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
async def ocr_upload(file: UploadFile = File(...)) -> OCRReviewResponse:
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

    return OCRReviewResponse(
        source_image=file.filename or "upload",
        model_used=adapter.model,
        metadata_hint={},
        indicators=drafts,
    )
