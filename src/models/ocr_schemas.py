from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.agents.state import IndicatorInput


class OCRIndicatorDraft(BaseModel):
    """Một chỉ số do Vision LLM đọc từ ảnh phiếu xét nghiệm.

    Đây là draft tạm, chưa được đưa thẳng vào AgentState.
    Người dùng phải review/xác nhận trước khi phân tích.
    """

    draft_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Định danh ngắn hạn của dòng OCR trong phiên review",
    )

    name: str = Field(
        ...,
        min_length=1,
        description="Tên chỉ số, ví dụ WBC, Glucose, LDL",
    )

    value: float = Field(
        ...,
        allow_inf_nan=False,
        description="Giá trị đo được; bắt buộc là số hữu hạn",
    )

    unit: str = Field(
        ...,
        min_length=1,
        description="Đơn vị đo",
    )

    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy 0-1 do Vision LLM đánh giá",
    )

    raw_text: str = Field(
        default="",
        description=("Chuỗi văn bản thô tương ứng trên ảnh, dùng để đối chiếu trong UI review"),
    )

    needs_review: bool = Field(
        default=False,
        description=("True nếu confidence thấp và cần người dùng review kỹ"),
    )
    supported: bool = Field(
        default=True,
        description="False nếu chỉ số OCR đọc được hiện chưa nằm trong danh sách hỗ trợ",
    )
    unsupported_reason: str = Field(
        default="",
        description="Lý do ngắn gọn để UI hiển thị khi chỉ số chưa được hỗ trợ",
    )

    def to_indicator_input(self) -> IndicatorInput:
        """Chuyển sang input chuẩn sau khi người dùng đã review."""
        return {
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
        }


class OCRReviewResponse(BaseModel):
    """Response của POST /api/v1/ocr/upload."""

    source_image: str = Field(
        default="",
        description="Tên file ảnh gốc",
    )

    model_used: str = Field(
        default="",
        description="Vision model đã sử dụng",
    )

    review_token: str = Field(
        ...,
        description=("Token ký ngắn hạn dùng để kiểm chứng phiên OCR review"),
    )

    low_confidence_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ngưỡng confidence của phiên review",
    )

    expires_in_seconds: int = Field(
        ...,
        ge=1,
    )

    metadata_hint: dict = Field(
        default_factory=dict,
        description=("Metadata bệnh nhân đọc được nếu có; mặc định trống"),
    )

    indicators: list[OCRIndicatorDraft] = Field(
        default_factory=list,
        description="Danh sách OCR draft cần người dùng xác nhận",
    )


class OCRSampleItem(BaseModel):
    """Một ảnh mẫu OCR được frontend hiển thị."""

    sample_id: str
    label: str
    description: str = ""

    size_bytes: int = Field(
        ...,
        ge=0,
    )


class OCRUploadPolicyResponse(BaseModel):
    """Chính sách upload OCR hiện hành."""

    mode: Literal[
        "internal_only",
        "demo_only",
        "open_with_consent",
    ]

    upload_enabled: bool = Field(
        ...,
        description="False khi mode=internal_only",
    )

    consent_required: bool = Field(
        default=True,
    )

    custom_image_allowed: bool = Field(
        ...,
        description=("False khi mode=demo_only; chỉ nhận ảnh mẫu"),
    )

    consent_text: str

    samples: list[OCRSampleItem] = Field(
        default_factory=list,
    )


class OCRReviewedIndicator(BaseModel):
    """Một dòng OCR sau khi người dùng review."""

    draft_id: str = Field(
        ...,
        min_length=1,
    )

    name: str = Field(
        ...,
        min_length=1,
    )

    value: float = Field(
        ...,
        allow_inf_nan=False,
    )

    unit: str = Field(
        ...,
        min_length=1,
    )

    included: bool = True

    reviewed: bool = Field(
        ...,
        description="Người dùng đã đối chiếu dòng này với ảnh",
    )

    low_confidence_acknowledged: bool = Field(
        default=False,
        description=("Bắt buộc nếu confidence gốc dưới ngưỡng"),
    )


class OCRConfirmRequest(BaseModel):
    """Bước 2 của OCR Review Gate."""

    review_token: str = Field(
        ...,
        min_length=1,
    )

    patient_age: int = Field(
        ...,
        ge=0,
        le=120,
    )

    patient_gender: Literal[
        "male",
        "female",
        "other",
    ]

    test_date: date

    language: str = "vi"

    indicators: list[OCRReviewedIndicator] = Field(
        ...,
        min_length=1,
    )
