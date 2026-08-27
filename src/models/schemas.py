from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

IndicatorStatus = str

# "admin" nam trong day vi /auth/login tra ve role, va thieu no thi tai khoan
# admin dang nhap dung mat khau van an 500 o buoc dung response — trieu chung
# ("dang nhap that bai") khong he chi ve mot Literal thieu gia tri.
SessionRole = Literal["patient", "doctor", "guest", "admin"]
VerificationStatus = Literal["unverified", "pending_review", "verified"]
ReviewOutcome = Literal["pending", "agreed", "corrected", "skipped"]
ReviewFlagCode = Literal[
    "CRITICAL_VALUE",
    "LOW_OCR_CONFIDENCE",
    "PATIENT_HAS_QUESTIONS",
]
ReviewFlagSeverity = Literal["high", "medium"]


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    """Đăng nhập bằng tên đăng nhập HOẶC email.

    Giữ nguyên tên trường `username` dù nó nhận cả email: đổi tên trường là phá
    hợp đồng API với frontend đã deploy và với mọi test hiện có, đổi lấy một cái
    tên đẹp hơn. Backend tra cả hai cột trong một câu truy vấn.
    """

    username: str = Field(..., min_length=1, description="Tên đăng nhập hoặc email")
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
    # Không bắt buộc, có chủ ý. Bắt buộc email là chặn mọi người đang đăng ký
    # bình thường hôm nay, đổi lấy một tính năng chưa ai dùng. Ai không điền thì
    # đăng nhập bằng tên như cũ.
    email: str | None = Field(default=None, max_length=320)


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: SessionRole
    username: str


class RegisterResponse(BaseModel):
    id: int
    username: str
    role: Literal["patient"]
    email: str | None = None


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
        description=("Giới tính bệnh nhân — dùng để chọn khoảng tham chiếu phù hợp"),
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
    analyte_raw: str | None = None
    analyte_canonical: str | None = None
    section: str | None = None
    section_label: str | None = None
    raw_value: float | None = None
    raw_unit: str | None = None
    canonical_value: float | None = None
    canonical_unit: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None

    status: IndicatorStatus
    critical_status: str | None = None

    is_abnormal: bool
    is_critical: bool

    explanation: str = Field(
        default="",
        description="Giải thích bằng ngôn ngữ dễ hiểu",
    )

    rule_type: str | None = None
    band_id: str | None = None
    upper_operator: str | None = None
    evaluation_reason: str | None = None

    review_outcome: ReviewOutcome = "pending"
    doctor_note: str | None = None
    ai_text_snapshot: str | None = None
    reviewed_by_username: str | None = None
    reviewed_at: datetime | None = None

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
    out_of_scope_indicators: list[str] = Field(default_factory=list)
    saved: bool = False
    duplicate: bool = False
    report_id: int | None = None
    existing_report_id: int | None = None
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
        description=("ID phiếu đã lưu trong lịch sử bệnh nhân. None nếu phiên hiện tại không được lưu lịch sử."),
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
    result_count: int = 0
    status: str = "NORMAL"
    has_critical_values: bool
    summary: str
    created_at: datetime

    # History repository của Duy có thể populate các field enrichment này.
    # Optional để ORM LabReport của main vẫn có thể validate trực tiếp.
    patient_username: str | None = None
    indicator_count: int | None = None
    abnormal_count: int | None = None

    source: Literal["manual", "ocr"] | None = None

    # Danh sách lịch sử của cả hai phía thể hiện được phiếu nào đã có ý kiến bác
    # sĩ và phiếu nào chưa, không cần mở từng phiếu ra xem.
    reviewed_by_doctor: bool = False
    has_doctor_notes: bool = False
    verification_status: VerificationStatus = "unverified"
    verified_by_username: str | None = None
    verified_at: datetime | None = None

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
    """Một câu hỏi gợi ý hỏi bác sĩ.

    `indicator_id` nullable: câu dự phòng của Template Library (khi guardrail
    chặn) và câu gộp nhiều chỉ số không có một chỉ số duy nhất để trỏ vào.
    """

    id: int
    indicator_id: int | None = None
    question_text: str

    priority: Literal[
        "critical",
        "abnormal",
        "unknown",
        "fallback",
    ]

    status: Literal[
        "generated",
        "sent_to_doctor",
        "answered",
    ]

    display_order: int = 0

    # Bệnh nhân tick chọn câu này để mang đi khám.
    is_selected: bool = False

    # Câu trả lời của bác sĩ. Do người viết nên KHÔNG qua guardrail; frontend
    # phải hiển thị kèm tên bác sĩ, tách khỏi nội dung do hệ thống sinh.
    answer_text: str | None = None
    answered_at: datetime | None = None

    # Enrichment, không phải DB column.
    answered_by_username: str | None = None

    created_at: datetime

    model_config = {
        "from_attributes": True,
    }


class QuestionSelectionRequest(BaseModel):
    """Bệnh nhân chốt danh sách câu hỏi mình muốn mang đi khám.

    Gửi đủ id của những câu được chọn; câu không có trong danh sách bị bỏ chọn.
    Danh sách rỗng là hợp lệ — nghĩa là bỏ chọn hết.
    """

    question_ids: list[int] = Field(default_factory=list)


class QuestionAnswerRequest(BaseModel):
    """Bác sĩ trả lời một câu hỏi cụ thể."""

    answer_text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )


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
    """Ghi chú của doctor trên report / indicator / report_question.

    `doctor_username` là thứ bệnh nhân đọc: mọi ghi chú phải hiển thị kèm tên
    người viết và thời điểm, trong khối tách bạch khỏi nội dung do hệ thống
    sinh. Nội dung này KHÔNG qua guardrail và KHÔNG được dán khuyến cáo "đây
    không phải chẩn đoán y khoa" — đây đúng là ý kiến chuyên môn của người có
    thẩm quyền, dán vào sẽ tạo mâu thuẫn.
    """

    id: int
    doctor_id: int

    target_type: Literal[
        "report",
        "indicator",
        "report_question",
    ]

    target_id: int
    note_text: str
    created_at: datetime

    # Enrichment, không phải DB column.
    doctor_username: str | None = None

    model_config = {
        "from_attributes": True,
    }


class DoctorNoteCreateRequest(BaseModel):
    """Request tạo doctor note.

    doctor_id lấy từ user/token authenticated, tuyệt đối không nhận từ body.
    Thời điểm ghi do máy chủ đặt, không nhận từ phía người dùng gửi lên.
    """

    target_type: Literal[
        "report",
        "indicator",
        "report_question",
    ] = "report"

    # None = ghi chú cho cả phiếu; id phiếu lấy từ URL.
    target_id: int | None = None

    note_text: str = Field(
        ...,
        min_length=1,
        max_length=4000,
    )


class ReportDoctorViewSchema(BaseModel):
    """Một bác sĩ đã chủ động đánh dấu đã xem phiếu."""

    doctor_id: int
    viewed_at: datetime

    doctor_username: str | None = None

    model_config = {
        "from_attributes": True,
    }


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
    status: str = "NORMAL"
    result_count: int = 0
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

    # Ghi chú của bác sĩ, mới nhất nằm trên. Chỉ thêm mới, không sửa đè và
    # không xoá: sửa một nhận xét bệnh nhân đã đọc và có thể đã làm theo mà
    # không để lại dấu là thay đổi thứ người khác đã hành động dựa trên đó.
    doctor_notes: list[DoctorNoteSchema] = Field(
        default_factory=list,
    )

    doctor_views: list[ReportDoctorViewSchema] = Field(
        default_factory=list,
    )

    # Enrichment của history API, không phải DB columns.
    patient_username: str | None = None
    indicator_count: int | None = None
    abnormal_count: int | None = None
    source: Literal["manual", "ocr"] | None = None

    # Hai trạng thái tách biệt, trả lời hai câu hỏi khác nhau của bệnh nhân.
    # "Đã có ai xem phiếu của tôi chưa" thường quan trọng hơn cả nội dung nhận
    # xét. Một phiếu có ghi chú thì hiển nhiên đã được xem; ngược lại thì không.
    reviewed_by_doctor: bool = False
    has_doctor_notes: bool = False
    verification_status: VerificationStatus = "unverified"
    verified_by_username: str | None = None
    verified_at: datetime | None = None

    model_config = {
        "from_attributes": True,
    }


class PatientProfileSchema(BaseModel):
    patient_id: int
    username: str
    full_name: str | None = None
    date_of_birth: date | None = None
    sex: str | None = None
    email: str | None = None
    response_style: Literal["concise", "simple", "detailed"] = "simple"
    created_at: datetime
    updated_at: datetime


class PatientProfileUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    date_of_birth: date | None = None
    sex: Literal["male", "female", "other"] | None = None
    email: str | None = Field(default=None, max_length=320)
    response_style: Literal["concise", "simple", "detailed"] | None = None


class PatientDashboardReportSchema(BaseModel):
    report_id: int
    test_date: date
    result_count: int
    status: str
    created_at: datetime
    verification_status: VerificationStatus = "unverified"
    verified_at: datetime | None = None


class PatientDashboardSchema(BaseModel):
    total_reports: int
    latest_test_date: date | None = None
    recent_reports: list[PatientDashboardReportSchema] = Field(default_factory=list)
    newly_verified_count: int = 0


class ReviewFlagSchema(BaseModel):
    code: ReviewFlagCode
    detail: str
    severity: ReviewFlagSeverity
    finding_id: int | None = None

    model_config = {
        "from_attributes": True,
    }


class DoctorQueueItemSchema(BaseModel):
    report_id: int
    patient_name: str
    patient_id: int
    test_date: date
    severity_level: Literal["critical", "abnormal", "normal"]
    flags: list[ReviewFlagSchema] = Field(default_factory=list)
    findings_reviewed: int = 0
    findings_total: int = 0
    queued_at: datetime | None = None


class DoctorQueueCountsSchema(BaseModel):
    critical: int = 0
    ocr: int = 0
    questions: int = 0
    pending: int = 0
    verified: int = 0


class DoctorQueueResponse(BaseModel):
    items: list[DoctorQueueItemSchema] = Field(default_factory=list)
    counts: DoctorQueueCountsSchema
    page: int
    page_size: int
    total: int


class DoctorPatientSchema(BaseModel):
    id: int
    name: str
    age: int | None = None
    gender: str | None = None


class DoctorReportSchema(BaseModel):
    id: int
    test_date: date
    verification_status: VerificationStatus
    verified_by: str | None = None
    verified_at: datetime | None = None
    input_method: Literal["manual", "ocr"]
    original_image_url: str | None = None


class DoctorFindingSchema(BaseModel):
    id: int
    metric_code: str | None = None
    metric_name: str
    value: float
    unit: str
    reference_range: str
    classification: Literal["critical", "abnormal", "normal"]
    ai_text: str
    review_outcome: ReviewOutcome
    doctor_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


class DoctorReportDetailResponse(BaseModel):
    report: DoctorReportSchema
    patient: DoctorPatientSchema
    flags: list[ReviewFlagSchema] = Field(default_factory=list)
    findings: list[DoctorFindingSchema] = Field(default_factory=list)
    questions: list[ReportQuestionSchema] = Field(default_factory=list)


class FindingReviewRequest(BaseModel):
    outcome: Literal["agreed", "corrected", "skipped"]
    doctor_note: str | None = Field(default=None, max_length=4000)


class ReportProgressSchema(BaseModel):
    reviewed: int
    total: int


class FindingReviewResponse(BaseModel):
    finding: DoctorFindingSchema
    report_progress: ReportProgressSchema


class DoctorCompleteReportResponse(BaseModel):
    report: DoctorReportSchema


class PatientLabReportListResponse(BaseModel):
    reports: list[PatientDashboardReportSchema] = Field(default_factory=list)


class SaveReportRequest(BaseModel):
    patient_age: int | None = Field(default=None, ge=0, le=120)
    patient_gender: Literal["male", "female", "other"] | None = None
    test_date: date | None = None
    language: str = "vi"
    source_image: str | None = None
    analysis: AnalyzeResponse


class SaveReportResponse(BaseModel):
    saved: bool
    duplicate: bool = False
    report_id: int | None = None
    existing_report_id: int | None = None
    requires_date_confirmation: bool = False
    message: str = ""


TrendFilter = Literal["latest5", "three_months"]
ObservedDirection = Literal["increasing", "decreasing"]


class TrendAnalyteSummary(BaseModel):
    analyte_canonical: str
    display_name: str
    canonical_unit: str
    result_count: int
    trend_available: bool
    section: str | None = None
    section_label: str | None = None


class TrendAnalyteListResponse(BaseModel):
    analytes: list[TrendAnalyteSummary] = Field(default_factory=list)


class TrendPointResponse(BaseModel):
    report_id: int
    test_date: date
    value: float
    assessment: str


class TrendResponse(BaseModel):
    analyte_canonical: str
    display_name: str
    canonical_unit: str
    filter: TrendFilter
    result_count: int
    trend_available: bool
    points: list[TrendPointResponse] = Field(default_factory=list)
    observed_direction: ObservedDirection | None = None
    reason: str | None = None
    section: str | None = None
    section_label: str | None = None
    critical_status: str | None = None
    approaching_critical: bool = False
    critical_alert: CriticalAlertSchema | None = None
    # ADR-010 CRIT-TREND-02: khoảng "bình thường" khớp theo sex/age tại lần đo gần nhất, dùng để vẽ vùng tham chiếu trên biểu đồ.
    reference_low: float | None = None
    reference_high: float | None = None
    # ADR-010 CRIT-TREND-03/05: ngưỡng nguy kịch active (chỉ khi đã escalate và cùng đơn vị hiển thị), dùng để vẽ đường ngưỡng trên biểu đồ.
    critical_low: float | None = None
    critical_high: float | None = None


class TrendExplanationResponse(BaseModel):
    explanation: str
    fallback: bool = False
    reason: str | None = None


class SectionTrendsResponse(BaseModel):
    """Response wrapping all analyte trends within a functional section."""

    section: str
    section_label: str
    trends: list[TrendResponse] = Field(default_factory=list)


TrendReviewStatus = Literal["PENDING", "REVIEWED", "CANCELLED", "REJECTED"]
TrendReviewAssessment = Literal["confirmed", "corrected", "needs_follow_up"]


class TrendReviewCreateRequest(BaseModel):
    """Patient request to send the currently visible trend explanation for review."""

    trend_filter: TrendFilter = "latest5"
    llm_explanation: str = Field(..., min_length=1, max_length=8000)


class TrendReviewSchema(BaseModel):
    id: int
    patient_id: int
    analyte_canonical: str
    display_name: str
    canonical_unit: str
    trend_filter: TrendFilter
    trend_snapshot: TrendResponse
    trend_snapshot_hash: str
    llm_explanation_snapshot: str
    status: TrendReviewStatus
    requested_at: datetime
    reviewed_by_doctor_id: int | None = None
    reviewed_by_username: str | None = None
    reviewed_at: datetime | None = None
    doctor_assessment: TrendReviewAssessment | None = None
    doctor_comment: str | None = None


class TrendReviewPatientStateResponse(BaseModel):
    latest_review: TrendReviewSchema | None = None
    latest_historical_review: TrendReviewSchema | None = None
    pending_request: TrendReviewSchema | None = None
    can_request_review: bool
    reason: str | None = None
    current_trend_hash: str | None = None
    history_count: int = 0


class TrendReviewRequestResponse(BaseModel):
    review: TrendReviewSchema
    created: bool = True


class TrendReviewHistoryResponse(BaseModel):
    total: int
    items: list[TrendReviewSchema] = Field(default_factory=list)


class DoctorTrendReviewSummary(BaseModel):
    id: int
    patient_id: int
    patient_name: str
    analyte_canonical: str
    display_name: str
    trend_filter: TrendFilter
    point_count: int
    status: TrendReviewStatus
    requested_at: datetime
    reviewed_at: datetime | None = None
    reviewed_by_username: str | None = None


class DoctorTrendReviewListResponse(BaseModel):
    total: int
    items: list[DoctorTrendReviewSummary] = Field(default_factory=list)


class DoctorTrendReviewDetailResponse(BaseModel):
    review: TrendReviewSchema
    patient: DoctorPatientSchema


class DoctorTrendReviewSubmitRequest(BaseModel):
    doctor_assessment: TrendReviewAssessment
    doctor_comment: str = Field(..., min_length=1, max_length=8000)


class HeatmapColumnSchema(BaseModel):
    report_id: int
    test_date: date


class HeatmapCellSchema(BaseModel):
    report_id: int
    test_date: date
    value: float
    unit: str
    status: str
    critical_status: str | None = None
    reference_low: float | None = None
    reference_high: float | None = None


class HeatmapRowSchema(BaseModel):
    analyte_canonical: str
    # Cùng độ dài và cùng thứ tự với `SectionHeatmapResponse.columns` — None ở vị trí
    # nào nghĩa là phiếu đó (cột đó) không đo chỉ số này, không phải "chưa xác định".
    cells: list[HeatmapCellSchema | None] = Field(default_factory=list)


class SectionHeatmapResponse(BaseModel):
    """Ma trận chỉ số × phiếu xét nghiệm cho một nhóm chức năng.

    Khác với `SectionTrendsResponse`: không áp ngưỡng MIN_TREND_POINTS (mọi chỉ số có
    ít nhất 1 kết quả trong phạm vi đều xuất hiện), và không nội suy dữ liệu thiếu —
    cột nào chỉ số đó không có kết quả thì cell tương ứng là None.
    """

    section: str
    section_label: str
    columns: list[HeatmapColumnSchema] = Field(default_factory=list)
    rows: list[HeatmapRowSchema] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Admin — trace vận hành
#
# Không schema nào dưới đây mang dữ liệu bệnh nhân. Cùng nguyên tắc đã khiến
# listener SQLAlchemy không bao giờ log `statement`/`parameters`: người lo hạ
# tầng cần biết cái gì chậm và cái gì hỏng, không cần biết ai khám gì.
# ---------------------------------------------------------------------------
class RequestTraceSchema(BaseModel):
    model_config = {
        "from_attributes": True,
    }

    request_id: str
    created_at: datetime
    method: str
    path: str
    status_code: int
    duration_ms: float
    db_query_count: int
    db_ms: float
    llm_call_count: int
    llm_ms: float
    llm_error_count: int
    user_role: str | None = None
    server_timing: str | None = None


class RequestTraceListResponse(BaseModel):
    total: int
    items: list[RequestTraceSchema] = Field(default_factory=list)


class TraceSummarySchema(BaseModel):
    """Vài con số tổng hợp cho đầu màn admin.

    Cố ý không có ngưỡng cảnh báo nào. Ngưỡng phải chọn từ số đo thật; đặt bừa
    rồi tô đỏ theo nó chỉ dạy người xem bỏ qua màu đỏ.
    """

    request_count: int
    avg_duration_ms: float
    max_duration_ms: float
    llm_call_count: int
    llm_error_count: int
    server_error_count: int
    window_hours: int


class TracingStatusSchema(BaseModel):
    """Langfuse đang bật hay tắt, và có che dữ liệu không.

    Cần thiết vì "trace trống" có hai nguyên nhân hoàn toàn khác nhau: chưa cấu
    hình key, hay đã cấu hình mà không có traffic. Không phơi key ra, chỉ phơi
    trạng thái và host.
    """

    langfuse_configured: bool
    langfuse_host: str
    masked: bool
    trace_persistence_enabled: bool
    retention_days: int


class GoogleLoginRequest(BaseModel):
    """ID token do Google Identity Services trả cho trình duyệt.

    Không có trường `email`, `role` hay bất cứ thứ gì mô tả người dùng: mọi
    thông tin danh tính phải lấy từ token đã được server xác minh chữ ký. Nhận
    thêm bất kỳ trường nào từ client là mở đường cho việc tự khai mình là ai.
    """

    credential: str = Field(..., min_length=1)


class GoogleStatusResponse(BaseModel):
    """Có bật đăng nhập bằng Google không, và client id nào.

    Client id là thông tin công khai — nó nằm sẵn trong mã nguồn mọi trang dùng
    Google Sign-In. Trả qua API thay vì nhúng vào bundle lúc build: biến
    NEXT_PUBLIC_* bị Next.js dán cứng vào JS nên đổi là phải build lại.
    """

    enabled: bool
    client_id: str | None = None
