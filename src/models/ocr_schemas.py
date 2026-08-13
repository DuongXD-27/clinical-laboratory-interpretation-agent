from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.agents.state import IndicatorInput


class OCRIndicatorDraft(BaseModel):
    """Một chỉ số do Vision LLM đọc từ ảnh phiếu xét nghiệm.

    Đây là DRAFT tạm — KHÔNG bao giờ được ghi thẳng vào `AgentState`/
    `raw_indicators`. Chỉ dùng để hiển thị ở màn hình UI_Review để bệnh nhân
    xác nhận/sửa trước khi submit qua `/analyze` (luồng Adapter_JSON cũ).
    """

    draft_id: str = Field(
        default_factory=lambda: uuid4().hex,
        description="Định danh ngắn hạn của dòng OCR trong phiên review",
    )
    name: str = Field(..., min_length=1, description="Tên chỉ số, vd. WBC, Glucose, LDL")
    value: float = Field(
        ...,
        allow_inf_nan=False,
        description="Giá trị đo được; bắt buộc là số hữu hạn",
    )
    unit: str = Field(..., min_length=1, description="Đơn vị đo")
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Độ tin cậy 0-1 do Vision LLM tự đánh giá cho chỉ số này",
    )
    raw_text: str = Field(
        default="",
        description="Chuỗi văn bản thô tương ứng trên ảnh (phục vụ đối chiếu ở UI_Review)",
    )
    needs_review: bool = Field(
        default=False,
        description="True nếu confidence thấp — bắt buộc người dùng xác nhận/sửa",
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
        """Chuyển sang lược đồ nội bộ chuẩn — chỉ được gọi SAU khi người dùng duyệt."""
        return {"name": self.name, "value": self.value, "unit": self.unit}


class OCRReviewResponse(BaseModel):
    """Response của `POST /api/v1/ocr/upload` — bản nháp cần người dùng xác nhận."""

    source_image: str = Field(default="", description="Tên file ảnh gốc")
    model_used: str = Field(default="", description="Model Vision LLM đã dùng")
    review_token: str = Field(
        ...,
        description="Token ký ngắn hạn buộc bước xác nhận dùng đúng confidence do server cấp",
    )
    low_confidence_threshold: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Ngưỡng confidence áp dụng cho phiên review này",
    )
    expires_in_seconds: int = Field(..., ge=1)
    metadata_hint: dict = Field(
        default_factory=dict,
        description="Thông tin bệnh nhân đọc được (nếu có) — mặc định trống, người dùng tự nhập",
    )
    indicators: list[OCRIndicatorDraft] = Field(
        default_factory=list,
        description="Danh sách chỉ số đọc được — cần bệnh nhân/bác sĩ xác nhận",
    )


class OCRSampleItem(BaseModel):
    """Một ảnh phiếu mẫu mà giao diện có thể cho người dùng thử ngay."""

    sample_id: str
    label: str
    description: str = ""
    size_bytes: int = Field(..., ge=0)


class OCRUploadPolicyResponse(BaseModel):
    """Chính sách nhận ảnh hiện hành — giao diện đọc cái này để tự điều chỉnh.

    Giao diện KHÔNG được tự đoán chính sách; backend là nơi quyết định và cũng
    là nơi thực thi. Trả về đây chỉ để UI hiển thị đúng (ẩn nút chọn file khi
    `demo_only`, báo tắt tính năng khi `internal_only`).
    """

    mode: Literal["internal_only", "demo_only", "open_with_consent"]
    upload_enabled: bool = Field(..., description="False khi mode=internal_only")
    consent_required: bool = Field(default=True)
    custom_image_allowed: bool = Field(
        ...,
        description="False khi mode=demo_only — chỉ nhận đúng ảnh trong bộ mẫu",
    )
    consent_text: str
    samples: list[OCRSampleItem] = Field(default_factory=list)


class OCRReviewedIndicator(BaseModel):
    """Một dòng OCR cùng bằng chứng xác nhận thủ công của người dùng."""

    draft_id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    value: float = Field(..., allow_inf_nan=False)
    unit: str = Field(..., min_length=1)
    included: bool = True
    reviewed: bool = Field(
        ...,
        description="Người dùng đã đối chiếu dòng này với ảnh gốc",
    )
    low_confidence_acknowledged: bool = Field(
        default=False,
        description="Xác nhận tăng cường, bắt buộc nếu confidence gốc dưới ngưỡng",
    )


class OCRConfirmRequest(BaseModel):
    """Bước 2 của OCR Review Gate; chỉ request hợp lệ mới được vào graph."""

    review_token: str = Field(..., min_length=1)
    patient_age: int = Field(..., ge=0, le=120)
    patient_gender: Literal["male", "female", "other"]
    test_date: date
    language: str = "vi"
    indicators: list[OCRReviewedIndicator] = Field(..., min_length=1)
