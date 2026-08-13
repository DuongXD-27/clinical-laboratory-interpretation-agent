from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

IndicatorStatus = str

SessionRole = Literal["patient", "doctor", "guest"]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)


class RegisterRequest(BaseModel):
    """Đăng ký tài khoản mới — luôn tạo role patient.

    Client không được truyền `role`.

    Tài khoản doctor phải được tạo bởi admin/script riêng, tránh việc client
    tự nâng quyền thành doctor qua endpoint public.
    """

    username: str = Field(
        ...,
        min_length=1,
    )
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Tối thiểu 8 ký tự",
    )


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
    """Phiên guest chỉ tồn tại trong token, không có row persistent trong DB."""

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


# ---------------------------------------------------------------------------
# Analyze input
# ---------------------------------------------------------------------------


class IndicatorInputSchema(BaseModel):
    """Một chỉ số thô trong phiếu xét nghiệm gửi từ client."""

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
        description="Đơn vị đo, ví dụ mg/dL, mmol/L",
    )


class AnalyzeRequest(BaseModel):
    """Request phân tích một phiếu xét nghiệm mô phỏng."""

    # ge=0 cho phép trẻ sơ sinh.
    patient_age: int = Field(
        ...,
        ge=0,
        le=120,
        description="Tuổi bệnh nhân",
    )

    patient_gender: Literal["male", "female", "other"] = Field(
        ...,
        description=(
            "Giới tính bệnh nhân — dùng để chọn khoảng tham chiếu phù hợp"
        ),
    )

    test_date: date = Field(
        ...,
        description="Ngày xét nghiệm (YYYY-MM-DD)",
    )

    language: str = Field(
        default="vi",
        description="Ngôn ngữ giải thích mong muốn",
    )

    indicators: list[IndicatorInputSchema] = Field(
        ...,
        min_length=1,
        description="Danh sách chỉ số xét nghiệm cần giải thích",
    )


# ---------------------------------------------------------------------------
# Analyze output
# ---------------------------------------------------------------------------


class IndicatorResultSchema(BaseModel):
    """Kết quả đối chiếu + giải thích cho một chỉ số.

    `ReportIndicator` không lưu riêng is_abnormal/is_critical.
    Hai thuộc tính này được derive từ `status` bằng @property ở ORM model.

    from_attributes=True cho phép Pydantic đọc trực tiếp từ ORM object.
    """

    name: str
    value: float
    unit: str

    reference_low: float | None = None
    reference_high: float | None = None

    status: IndicatorStatus

    is_abnormal: bool
    is_critical: bool

    explanation: str = Field(
        default="",
        description="Giải thích bằng ngôn ngữ dễ hiểu",
    )

    sources: list[str] = Field(
        default_factory=list,
        description="Nguồn tài liệu giáo dục y khoa",
    )

    model_config = {
        "from_attributes": True,
    }


class CriticalAlertSchema(BaseModel):
    indicator_name: str
    value: float
    unit: str
    message: str

    model_config = {
        "from_attributes": True,
    }


class AnalyzeResponse(BaseModel):
    """Response sau khi agent phân tích phiếu xét nghiệm."""

    indicators: list[IndicatorResultSchema]

    critical_alerts: list[CriticalAlertSchema] = Field(
        default_factory=list,
    )

    has_critical_values: bool = False

    questions_for_doctor: list[str] = Field(
        default_factory=list,
    )

    summary: str = ""

    disclaimer: str = (
        "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa. "
        "Vui lòng trao đổi với bác sĩ để được diễn giải chính xác cho tình trạng của bạn."
    )

    guardrail_passed: bool = True

    out_of_scope_indicators: list[str] = Field(
        default_factory=list,
    )

    error: str = ""

    is_placeholder: bool = Field(
        default=False,
        description=(
            "True nếu response chưa qua logic phân tích thật "
            "(reference-range/RAG/critical-value chưa cắm vào graph) — "
            "không được dùng để đánh giá lâm sàng."
        ),
    )

    # Giữ từ TechDebt Duy.
    #
    # patient authenticated:
    #   → ID report vừa persistence
    #
    # guest / doctor / không persistence:
    #   → None
    saved_report_id: int | None = Field(
        default=None,
        description=(
            "ID phiếu đã lưu trong lịch sử bệnh nhân. "
            "None nếu phiên hiện tại không được lưu lịch sử."
        ),
    )


# ---------------------------------------------------------------------------
# History
# ---------------------------------------------------------------------------


class LabReportSummarySchema(BaseModel):
    """Một dòng trong danh sách lịch sử xét nghiệm.

    Các field lõi map trực tiếp với LabReport của schema Vũ.

    Các field patient_username / indicator_count / abnormal_count / source
    là dữ liệu presentation của endpoint history và có thể được repository
    tính thêm.

    `source` KHÔNG phải cột DB:
        ocr_source_filename != None -> "ocr"
        otherwise                   -> "manual"
    """

    id: int
    test_date: date
    has_critical_values: bool
    summary: str
    created_at: datetime

    # History repository của Duy có thể populate các field enrichment này.
    # Optional để ORM LabReport của main vẫn có thể validate trực tiếp.
    patient_username: str | None = None
    indicator_count: int | None = None
    abnormal_count: int | None = None

    source: Literal["manual", "ocr"] | None = None

    model_config = {
        "from_attributes": True,
    }


class LabReportListResponse(BaseModel):
    """Response của GET /api/v1/history."""

    total: int

    items: list[LabReportSummarySchema] = Field(
        default_factory=list,
    )


# ---------------------------------------------------------------------------
# Report children
# ---------------------------------------------------------------------------


class ReportQuestionSchema(BaseModel):
    """Một câu hỏi gợi ý hỏi bác sĩ, gắn với một indicator cụ thể."""

    id: int
    indicator_id: int
    question_text: str

    priority: Literal[
        "critical",
        "abnormal",
    ]

    status: Literal[
        "generated",
        "sent_to_doctor",
        "answered",
    ]

    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class OutOfScopeLogSchema(BaseModel):
    """Một chỉ số ngoài phạm vi thư viện hỗ trợ."""

    id: int
    raw_indicator_name: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


# ---------------------------------------------------------------------------
# Doctor HITL
# ---------------------------------------------------------------------------


class DoctorNoteSchema(BaseModel):
    """Ghi chú của doctor trên indicator hoặc report_question."""

    id: int
    doctor_id: int

    target_type: Literal[
        "indicator",
        "report_question",
    ]

    target_id: int
    note_text: str
    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class DoctorNoteCreateRequest(BaseModel):
    """Request tạo doctor note.

    doctor_id lấy từ user/token authenticated, tuyệt đối không nhận từ body.
    """

    target_type: Literal[
        "indicator",
        "report_question",
    ]

    target_id: int

    note_text: str = Field(
        ...,
        min_length=1,
    )


# ---------------------------------------------------------------------------
# Full report detail
# ---------------------------------------------------------------------------


class LabReportDetailSchema(BaseModel):
    """Chi tiết đầy đủ một report lịch sử.

    Field persistence sử dụng naming chuẩn từ schema Vũ:
    - patient_id
    - patient_age_at_test
    - patient_gender_at_test
    """

    id: int
    patient_id: int

    test_date: date

    patient_age_at_test: int | None = None
    patient_gender_at_test: str | None = None

    language: str

    summary: str
    has_critical_values: bool
    guardrail_passed: bool

    disclaimer: str

    created_at: datetime

    indicators: list[IndicatorResultSchema] = Field(
        default_factory=list,
    )

    critical_alerts: list[CriticalAlertSchema] = Field(
        default_factory=list,
    )

    questions: list[ReportQuestionSchema] = Field(
        default_factory=list,
    )

    out_of_scope_entries: list[OutOfScopeLogSchema] = Field(
        default_factory=list,
    )

    # Enrichment của history API, không phải DB columns.
    patient_username: str | None = None
    indicator_count: int | None = None
    abnormal_count: int | None = None
    source: Literal["manual", "ocr"] | None = None

    model_config = {
        "from_attributes": True,
    }
