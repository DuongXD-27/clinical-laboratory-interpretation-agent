from __future__ import annotations

from typing import TYPE_CHECKING
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from src.agents.state import IndicatorInput


class OCRIndicatorDraft(BaseModel):
    """Một chỉ số do Vision LLM đọc từ ảnh phiếu xét nghiệm.

    Đây là DRAFT tạm — KHÔNG bao giờ được ghi thẳng vào `AgentState`/
    `raw_indicators`. Chỉ dùng để hiển thị ở màn hình UI_Review để bệnh nhân
    xác nhận/sửa trước khi submit qua `/analyze` (luồng Adapter_JSON cũ).
    """

    name: str = Field(..., min_length=1, description="Tên chỉ số, vd. WBC, Glucose, LDL")
    value: float = Field(..., description="Giá trị đo được")
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

    def to_indicator_input(self) -> IndicatorInput:
        """Chuyển sang lược đồ nội bộ chuẩn — chỉ được gọi SAU khi người dùng duyệt."""
        return {"name": self.name, "value": self.value, "unit": self.unit}


class OCRReviewResponse(BaseModel):
    """Response của `POST /api/v1/ocr/upload` — bản nháp cần người dùng xác nhận."""

    source_image: str = Field(default="", description="Tên file ảnh gốc")
    model_used: str = Field(default="", description="Model Vision LLM đã dùng")
    metadata_hint: dict = Field(
        default_factory=dict,
        description="Thông tin bệnh nhân đọc được (nếu có) — mặc định trống, người dùng tự nhập",
    )
    indicators: list[OCRIndicatorDraft] = Field(
        default_factory=list,
        description="Danh sách chỉ số đọc được — cần bệnh nhân/bác sĩ xác nhận",
    )
