from typing import Literal

from pydantic import BaseModel, Field

IndicatorStatus = Literal["normal", "low", "high", "critical_low", "critical_high"]


class IndicatorInputSchema(BaseModel):
    """Một chỉ số thô trong phiếu xét nghiệm gửi lên từ client."""

    name: str = Field(..., min_length=1, description="Tên chỉ số, vd. WBC, Glucose, LDL")
    value: float = Field(..., description="Giá trị đo được")
    unit: str = Field(..., min_length=1, description="Đơn vị đo, vd. mg/dL, mmol/L")


class AnalyzeRequest(BaseModel):
    """Request phân tích một phiếu xét nghiệm mô phỏng (JSON)."""

    patient_age: int = Field(..., ge=0, le=120, description="Tuổi bệnh nhân")
    patient_gender: Literal["male", "female", "other"] = Field(
        ..., description="Giới tính bệnh nhân — dùng để chọn khoảng tham chiếu phù hợp"
    )
    test_date: str = Field(..., description="Ngày xét nghiệm, định dạng YYYY-MM-DD")
    language: str = Field(default="vi", description="Ngôn ngữ giải thích mong muốn")
    indicators: list[IndicatorInputSchema] = Field(
        ..., min_length=1, description="Danh sách chỉ số xét nghiệm cần giải thích"
    )


class IndicatorResultSchema(BaseModel):
    """Kết quả đối chiếu + giải thích cho một chỉ số."""

    name: str
    value: float
    unit: str
    reference_low: float | None = None
    reference_high: float | None = None
    status: IndicatorStatus
    is_abnormal: bool
    is_critical: bool
    explanation: str = Field(default="", description="Giải thích ngôn ngữ dễ hiểu")
    sources: list[str] = Field(default_factory=list, description="Nguồn tài liệu giáo dục y khoa")


class CriticalAlertSchema(BaseModel):
    indicator_name: str
    value: float
    unit: str
    message: str


class AnalyzeResponse(BaseModel):
    """Response trả về sau khi agent phân tích phiếu xét nghiệm."""

    indicators: list[IndicatorResultSchema]
    critical_alerts: list[CriticalAlertSchema] = Field(default_factory=list)
    has_critical_values: bool = False
    questions_for_doctor: list[str] = Field(default_factory=list)
    summary: str = ""
    disclaimer: str = (
        "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa. "
        "Vui lòng trao đổi với bác sĩ để được diễn giải chính xác cho tình trạng của bạn."
    )
    guardrail_passed: bool = True
    out_of_scope_indicators: list[str] = Field(default_factory=list)
    error: str = ""
