from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

IndicatorStatus = str

SessionRole = Literal["patient", "doctor", "guest"]


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Đăng ký tài khoản bệnh nhân.

    Không có trường `role`: tài khoản bác sĩ do admin cấp qua
    `python -m src.scripts.create_doctor`, không tự đăng ký được — nếu để client
    tự khai role thì bất kỳ ai cũng tự nâng quyền thành bác sĩ.
    """

    username: str = Field(..., min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(..., min_length=6, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: SessionRole
    username: str


class RegisterResponse(BaseModel):
    id: int
    username: str
    role: Literal["patient"]


class GuestSessionResponse(BaseModel):
    """Phiên khách: có token để gọi API, không có tài khoản trong DB."""

    access_token: str
    token_type: str = "bearer"
    role: Literal["guest"] = "guest"
    username: str
    session_id: str
    expires_in_seconds: int
    can_save_history: bool = False


class CurrentUserResponse(BaseModel):
    username: str
    role: SessionRole
    is_guest: bool = False


class IndicatorInputSchema(BaseModel):
    """Một chỉ số thô trong phiếu xét nghiệm gửi lên từ client."""

    name: str = Field(..., min_length=1, description="Tên chỉ số, vd. WBC, Glucose, LDL")
    value: float = Field(
        ...,
        allow_inf_nan=False,
        description="Giá trị đo được; bắt buộc là số hữu hạn",
    )
    unit: str = Field(..., min_length=1, description="Đơn vị đo, vd. mg/dL, mmol/L")


class AnalyzeRequest(BaseModel):
    """Request phân tích một phiếu xét nghiệm mô phỏng (JSON)."""

    # ge=0 để cho phép trẻ sơ sinh (0 tuổi) — logic tra khoảng tham chiếu theo
    # tuổi/giới tính (reference-range checker) phải xử lý đúng trường hợp này,
    # không dùng age làm mẫu số.
    patient_age: int = Field(..., ge=0, le=120, description="Tuổi bệnh nhân")
    patient_gender: Literal["male", "female", "other"] = Field(
        ..., description="Giới tính bệnh nhân — dùng để chọn khoảng tham chiếu phù hợp"
    )
    test_date: date = Field(..., description="Ngày xét nghiệm (YYYY-MM-DD)")
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
    is_placeholder: bool = Field(
        default=False,
        description=(
            "True nếu response chưa qua logic phân tích thật (reference-range/RAG/"
            "critical-value chưa cắm vào graph) — không được dùng để đánh giá lâm sàng."
        ),
    )
    saved_report_id: int | None = Field(
        default=None,
        description=(
            "ID phiếu đã lưu vào lịch sử bệnh nhân; None nếu phiên hiện tại không "
            "lưu lịch sử (khách, hoặc tài khoản bác sĩ)."
        ),
    )


class LabReportSummarySchema(BaseModel):
    """Một dòng trong danh sách lịch sử — đủ để hiển thị, chưa kèm giải thích dài."""

    id: int
    patient_username: str
    test_date: date
    created_at: datetime
    indicator_count: int
    abnormal_count: int
    has_critical_values: bool
    source: Literal["manual", "ocr"]
    summary: str = ""


class LabReportDetailSchema(LabReportSummarySchema):
    """Chi tiết một phiếu đã lưu, kèm toàn bộ chỉ số và giải thích."""

    patient_age: int
    patient_gender: str
    language: str
    guardrail_passed: bool
    indicators: list[IndicatorResultSchema] = Field(default_factory=list)


class LabReportListResponse(BaseModel):
    total: int
    items: list[LabReportSummarySchema] = Field(default_factory=list)
