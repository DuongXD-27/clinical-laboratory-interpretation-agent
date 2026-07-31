from __future__ import annotations

from typing import Literal, TypedDict

IndicatorStatus = Literal["normal", "low", "high", "critical_low", "critical_high"]


class IndicatorInput(TypedDict, total=False):
    """Một chỉ số thô lấy từ phiếu xét nghiệm (JSON mock hoặc OCR)."""

    name: str
    value: float
    unit: str


class IndicatorAssessment(TypedDict, total=False):
    """Kết quả sau khi đối chiếu khoảng tham chiếu (rule-based, không dùng LLM)."""

    name: str
    value: float
    unit: str
    reference_low: float | None
    reference_high: float | None
    status: IndicatorStatus
    is_abnormal: bool
    is_critical: bool


class RetrievedChunk(TypedDict, total=False):
    """Một đoạn tài liệu giáo dục y khoa lấy từ RAG cho một chỉ số."""

    indicator_name: str
    text: str
    source: str
    score: float


class IndicatorExplanation(TypedDict, total=False):
    """Giải thích cá nhân hóa, thân thiện cho một chỉ số — grounded trên RetrievedChunk."""

    indicator_name: str
    status: IndicatorStatus
    is_abnormal: bool
    is_critical: bool
    explanation: str
    sources: list[str]


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
        -> retrieve_explanation -> personalize_explanation -> guardrail_check
        -> generate_questions -> build_summary

    total=False: mỗi node chỉ đọc/ghi các field liên quan đến bước của mình.
    """

    # --- Input phiếu xét nghiệm (đã de-identify PHI trước khi vào state) ---
    patient_age: int
    patient_gender: Literal["male", "female", "other"]
    test_date: str
    language: str
    raw_indicators: list[IndicatorInput]

    # --- Rule-based: reference range checker + critical value detector ---
    indicators: list[IndicatorAssessment]
    critical_alerts: list[CriticalAlert]
    has_critical_values: bool

    # --- RAG: tra cứu tài liệu giải thích chỉ số có nguồn ---
    retrieved_contexts: list[RetrievedChunk]
    out_of_scope_indicators: list[str]

    # --- Cá nhân hóa lời giải thích (LLM, grounded trên retrieved_contexts) ---
    explanations: list[IndicatorExplanation]

    # --- Guardrail: chống chẩn đoán / kê đơn / kết luận nguyên nhân ---
    guardrail_passed: bool
    guardrail_flags: list[str]

    # --- Câu hỏi gợi ý cho bác sĩ + tóm tắt thân thiện ---
    questions_for_doctor: list[str]
    summary: str
    disclaimer: str

    # --- Vận hành ---
    error: str
    metadata: dict
