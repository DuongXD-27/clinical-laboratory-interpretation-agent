from __future__ import annotations

from typing import Literal, TypedDict

from src.models.ocr_schemas import OCRIndicatorDraft

IndicatorStatus = Literal["unknown", "normal", "low", "high", "critical_low", "critical_high"]



class IndicatorInput(TypedDict, total=False):
    """Một chỉ số thô lấy từ phiếu xét nghiệm (JSON mock hoặc OCR)."""

    name: str
    value: float
    unit: str


class IndicatorAssessment(TypedDict, total=False):
    """Kết quả sau khi đối chiếu khoảng tham chiếu (rule-based, không dùng LLM)."""

    name: str
    analyte_id: str
    value: float
    unit: str
    reference_low: float | None
    reference_high: float | None
    status: IndicatorStatus
    # Nhãn phân loại chi tiết, riêng theo từng chỉ số — vd "borderline_high",
    # "fasting_prediabetes", "critical_high". `status` ở trên chỉ là cờ THÔ
    # (dùng để tô màu badge / kích hoạt Gate 3), `category` mới là nhãn hiển
    # thị thật cho người dùng — không giới hạn Literal vì mỗi chỉ số có bộ
    # mức phân loại khác nhau (LDL có 5 mức, Glucose có mức tiền tiểu đường...).
    category: str
    is_abnormal: bool
    is_critical: bool


class RetrievedChunk(TypedDict, total=False):
    """Một đoạn tài liệu giáo dục y khoa lấy từ RAG cho một chỉ số."""

    indicator_name: str
    text: str
    source: str
    sources: list[str]
    score: float


class IndicatorExplanation(TypedDict, total=False):
    """Giải thích cá nhân hóa, thân thiện cho một chỉ số — grounded trên RetrievedChunk."""

    indicator_name: str
    status: IndicatorStatus
    category: str  # đồng bộ với IndicatorAssessment.category, hiển thị lên UI
    is_abnormal: bool
    is_critical: bool
    explanation: str
    sources: list[str]


class DoctorQuestionMeta(TypedDict, total=False):
    """Metadata của một câu hỏi gợi ý, đi song song với chuỗi câu hỏi."""

    # "critical" | "abnormal" | "unknown" | "fallback"
    priority: str
    display_order: int
    analyte_id: str | None
    # Tên chỉ số đúng như bệnh nhân nhập, dùng để nối câu hỏi về đúng dòng.
    indicator_name: str | None


class CriticalAlert(TypedDict, total=False):
    """Cảnh báo khẩn khi một chỉ số ở mức nguy kịch (vd. Kali, Glucose cực đoan)."""

    indicator_name: str
    value: float
    unit: str
    message: str


class AgentState(TypedDict, total=False):
    """State schema cho LangGraph agent giải thích phiếu xét nghiệm (VMEC-05).

    Luồng node dự kiến:
        parse_report -> check_reference_range -> detect_critical_values
        -> retrieve_explanation -> personalize_explanation -> generate_questions
        -> guardrail_check -> build_summary

    guardrail_check được đặt SAU generate_questions (không phải trước) vì
    guardrail bắt buộc phải kiểm duyệt CẢ giải thích lẫn câu hỏi gợi ý cho
    bác sĩ trước khi trả về người dùng — đúng ADR-004 (guardrail luôn là
    lớp cuối cùng của luồng, không có ngoại lệ cho bất kỳ nội dung nào do
    LLM sinh ra).

    total=False: mỗi node chỉ đọc/ghi các field liên quan đến bước của mình.
    """

    # --- Input phiếu xét nghiệm (đã de-identify PHI trước khi vào state) ---
    patient_age: int
    patient_gender: Literal["male", "female", "other"]
    test_date: str
    language: str
    raw_indicators: list[IndicatorInput]

    # --- OCR & Gate UI_Review: Bản nháp trích xuất từ ảnh & trạng thái kiểm duyệt ---
    # ocr_drafts: Danh sách các bản nháp chỉ số trích xuất từ Vision LLM Adapter (Vũ).
    # Có thể null (None) nếu đầu vào là JSON nhập trực tiếp hoặc rỗng khi OCR không bóc tách được.
    ocr_drafts: list[OCRIndicatorDraft] | None

    # is_ocr_reviewed: Cờ đánh dấu dữ liệu OCR đã được kiểm duyệt thủ công tại Gate UI_Review
    # (bệnh nhân/bác sĩ xem lại và xác nhận) trước khi đưa vào pipeline chính. Mặc định là False.
    is_ocr_reviewed: bool

    # --- Rule-based: reference range checker + critical value detector ---
    indicators: list[IndicatorAssessment]
    critical_alerts: list[CriticalAlert]
    has_critical_values: bool

    # --- RAG: tra cứu tài liệu giải thích chỉ số có nguồn ---
    retrieved_contexts: list[RetrievedChunk]
    out_of_scope_indicators: list[str]

    # --- Cá nhân hóa lời giải thích (LLM, grounded trên retrieved_contexts) ---
    explanations: list[IndicatorExplanation]

    # --- Câu hỏi gợi ý cho bác sĩ (LLM) — SINH RA TRƯỚC guardrail_check,
    # để guardrail có thể kiểm duyệt cả nội dung này trước khi trả ra ngoài ---
    questions_for_doctor: list[str]

    # Metadata song song với `questions_for_doctor`, cùng thứ tự và cùng độ dài.
    # Tách khỏi danh sách chuỗi vì nhánh kiểm duyệt câu hỏi của guardrail nhận
    # `list[str]` từ V2 và không nên phải đổi kiểu. Sau guardrail, hai danh sách
    # được ghép lại bằng `reconcile_after_guardrail()`.
    doctor_question_meta: list[DoctorQuestionMeta]

    # --- Guardrail: chống chẩn đoán / kê đơn / kết luận nguyên nhân.
    # Chạy SAU CÙNG, kiểm duyệt cả `explanations` lẫn `questions_for_doctor` ---
    guardrail_passed: bool
    guardrail_flags: list[str]

    # --- Tóm tắt thân thiện, trả về sau khi guardrail đã duyệt ---
    summary: str
    disclaimer: str

    # --- Vận hành ---
    # error: chỉ dùng nội bộ để debug/log. TUYỆT ĐỐI KHÔNG trả nguyên văn
    # field này ra API/UI cho người dùng cuối (đã từng xảy ra: thông báo
    # "Do thiếu API Key..." bị lộ thẳng ra giao diện bệnh nhân). Trước khi
    # response ra ngoài, luôn thay bằng câu an toàn dạng "Hệ thống đang
    # bận, vui lòng thử lại".
    error: str
    metadata: dict
