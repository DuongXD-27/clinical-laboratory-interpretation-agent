from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

IndicatorStatus = str


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Đăng ký tài khoản mới — luôn tạo role patient.

    Doctor không tự đăng ký qua endpoint này (theo ma trận phân quyền:
    tài khoản doctor được cấp sẵn bởi admin/seed), nên không có field role.
    """

    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8, description="Tối thiểu 8 ký tự")


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: Literal["patient", "doctor"]
    username: str


class CurrentUserResponse(BaseModel):
    username: str
    role: Literal["patient", "doctor"]


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


class LabReportSummarySchema(BaseModel):
    """1 dòng trong danh sách lịch sử xét nghiệm — không kèm chi tiết chỉ số."""

    id: int
    test_date: date
    has_critical_values: bool
    summary: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ReportQuestionSchema(BaseModel):
    """1 câu hỏi gợi ý hỏi bác sĩ, gắn với 1 chỉ số cụ thể."""

    id: int
    indicator_id: int
    question_text: str
    priority: Literal["critical", "abnormal"]
    status: Literal["generated", "sent_to_doctor", "answered"]
    created_at: datetime

    model_config = {"from_attributes": True}


class OutOfScopeLogSchema(BaseModel):
    """1 dòng log cho 1 chỉ số ngoài phạm vi hỗ trợ trong report."""

    id: int
    raw_indicator_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DoctorNoteSchema(BaseModel):
    """Ghi chú của bác sĩ trên 1 chỉ số hoặc 1 câu hỏi (target_type/target_id)."""

    id: int
    doctor_id: int
    target_type: Literal["indicator", "report_question"]
    target_id: int
    note_text: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DoctorNoteCreateRequest(BaseModel):
    """Request tạo ghi chú mới — doctor_id lấy từ token, không nhận từ body."""

    target_type: Literal["indicator", "report_question"]
    target_id: int
    note_text: str = Field(..., min_length=1)


class LabReportDetailSchema(BaseModel):
    """1 phiếu xét nghiệm đầy đủ, dùng khi xem chi tiết 1 record lịch sử."""

    id: int
    patient_id: int
    test_date: date
    patient_age_at_test: int | None
    patient_gender_at_test: str | None
    language: str
    summary: str
    has_critical_values: bool
    guardrail_passed: bool
    disclaimer: str
    created_at: datetime
    indicators: list[IndicatorResultSchema]
    critical_alerts: list[CriticalAlertSchema]
    questions: list[ReportQuestionSchema]
    out_of_scope_entries: list[OutOfScopeLogSchema]

    model_config = {"from_attributes": True}
