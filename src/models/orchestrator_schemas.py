"""Shared Orchestrator V1 contracts.

This module is intentionally types-only. It defines the conversational
orchestrator boundary without adding routes, workflow nodes, services, medical
logic, or persistence.

Three distinct state surfaces must never be merged:
- LangGraph workflow checkpoint -> ``src/agents/state.py`` ``AgentState``
- persistent medical DB -> ``history_repository`` / SQLAlchemy
- conversational session context -> ``OrchestratorSessionContext`` in this file
"""

from __future__ import annotations

import time
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, computed_field, model_validator

from src.models.db import ROLE_PATIENT
from src.models.schemas import (
    CriticalAlertSchema,
    IndicatorResultSchema,
    TrendResponse,
    VerificationStatus,
)
from src.services.auth import ROLE_GUEST
from src.services.question_templates import GeneratedQuestion

ServerReference = Annotated[
    str,
    Field(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9_.% +-]+$",
    ),
]


class IntentEnum(StrEnum):
    UNSUPPORTED_OR_UNSAFE = "UNSUPPORTED_OR_UNSAFE"
    ANALYZE_REPORT = "ANALYZE_REPORT"
    EXPLAIN_CURRENT_RESULT = "EXPLAIN_CURRENT_RESULT"
    VIEW_HISTORY = "VIEW_HISTORY"
    ANALYZE_TREND = "ANALYZE_TREND"
    GET_DOCTOR_QUESTIONS = "GET_DOCTOR_QUESTIONS"
    SAFE_GENERAL = "SAFE_GENERAL"
    APP_HELP = "APP_HELP"


class OrchestratorRole(StrEnum):
    GUEST = ROLE_GUEST
    PATIENT = ROLE_PATIENT


class ResponseStatus(StrEnum):
    SUCCESS = "success"
    NEEDS_INPUT = "needs_input"
    BLOCKED = "blocked"
    ERROR = "error"


class ProgressStage(StrEnum):
    """Frozen patient-safe execution stages for the V1 event stream."""

    ROUTING = "routing"
    MEDICAL_CONTEXT = "medical_context"
    LONGITUDINAL_RETRIEVAL = "longitudinal_retrieval"
    RESPONSE_COMPOSITION = "response_composition"


class StreamEventType(StrEnum):
    MESSAGE_STARTED = "message.started"
    PROGRESS = "progress"
    MESSAGE_COMPLETED = "message.completed"
    ERROR = "error"


class ResponseStyle(StrEnum):
    CONCISE = "concise"
    SIMPLE = "simple"
    DETAILED = "detailed"


class ReasonCode(StrEnum):
    EMERGENCY_INPUT_SAFETY = "EMERGENCY_INPUT_SAFETY"
    ONBOARDING_REQUIRED = "ONBOARDING_REQUIRED"
    OCR_REVIEW_REQUIRED = "OCR_REVIEW_REQUIRED"
    OCR_CONFIRM_INVALID = "OCR_CONFIRM_INVALID"
    MEDICAL_DIAGNOSIS_REQUEST = "MEDICAL_DIAGNOSIS_REQUEST"
    MEDICAL_CAUSE_REQUEST = "MEDICAL_CAUSE_REQUEST"
    TREATMENT_REQUEST = "TREATMENT_REQUEST"
    PERSONAL_MEDICAL_ADVICE = "PERSONAL_MEDICAL_ADVICE"
    UNSUPPORTED_ANALYTE = "UNSUPPORTED_ANALYTE"
    UNSUPPORTED_CAPABILITY = "UNSUPPORTED_CAPABILITY"
    AMBIGUOUS_CONTEXT = "AMBIGUOUS_CONTEXT"
    AUTH_EXPIRED = "AUTH_EXPIRED"
    REPORT_NOT_FOUND_OR_UNAUTHORIZED = "REPORT_NOT_FOUND_OR_UNAUTHORIZED"
    DB_UNAVAILABLE = "DB_UNAVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    RAG_UNAVAILABLE = "RAG_UNAVAILABLE"
    TREND_INSUFFICIENT_POINTS = "TREND_INSUFFICIENT_POINTS"
    TREND_UNIT_INCONSISTENT = "TREND_UNIT_INCONSISTENT"
    UNKNOWN_INTENT = "UNKNOWN_INTENT"
    OUT_OF_SCOPE = "OUT_OF_SCOPE"
    SENSITIVE_SYSTEM_REQUEST = "SENSITIVE_SYSTEM_REQUEST"
    GUARDRAIL_BLOCKED = "GUARDRAIL_BLOCKED"
    INTERNAL_WORKFLOW_ERROR = "INTERNAL_WORKFLOW_ERROR"


class UIContext(BaseModel):
    """Untrusted client UI hints.

    This is a hint only. It never grants authority, never changes role, and
    never selects a report the user does not own.
    """

    model_config = ConfigDict(extra="forbid")

    screen: ServerReference | None = None
    view: ServerReference | None = None
    candidate_analyte: ServerReference | None = None
    candidate_report_ref: ServerReference | None = None
    response_style: ResponseStyle | Literal["concise", "simple", "detailed"] | None = None


class ConversationState(BaseModel):
    model_config = ConfigDict(extra="forbid")
    pending_question: str | None = None
    pending_question_timestamp: float | None = None
    expected_entity: str | None = None
    ttl_seconds: float = 300.0

    def is_expired(self, current_time: float | None = None) -> bool:
        if not self.pending_question:
            return False
        if self.pending_question_timestamp is None:
            return False
        now = time.time() if current_time is None else current_time
        return (now - self.pending_question_timestamp) > self.ttl_seconds

    def get_active_pending_question(self, current_time: float | None = None) -> str | None:
        if self.is_expired(current_time):
            return None
        return self.pending_question


class OrchestratorSessionContext(BaseModel):
    """Server-constructed conversational context; never accepted from clients."""

    model_config = ConfigDict(extra="forbid")

    session_id: ServerReference
    user_role: OrchestratorRole
    onboarding_acknowledged: bool = False
    current_report_ref: ServerReference | None = None
    current_analyte: ServerReference | None = None
    last_intent: IntentEnum | None = None
    transient_ui_context: UIContext | None = None
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    response_style: ResponseStyle = ResponseStyle.SIMPLE

    _pending_ocr_review: bool = PrivateAttr(default=False)

    @computed_field
    @property
    def pending_ocr_review(self) -> bool:
        """Derived from the OCR review gate; not parseable from client data."""

        return self._pending_ocr_review

    @classmethod
    def from_server(
        cls,
        *,
        session_id: str,
        user_role: OrchestratorRole,
        onboarding_acknowledged: bool = False,
        current_report_ref: str | None = None,
        current_analyte: str | None = None,
        last_intent: IntentEnum | None = None,
        pending_ocr_review: bool = False,
        transient_ui_context: UIContext | None = None,
        conversation_state: ConversationState | None = None,
        response_style: ResponseStyle | str = ResponseStyle.SIMPLE,
    ) -> OrchestratorSessionContext:
        resolved_style = (
            response_style
            if isinstance(response_style, ResponseStyle)
            else ResponseStyle(response_style) if response_style in set(ResponseStyle) else ResponseStyle.SIMPLE
        )
        context = cls(
            session_id=session_id,
            user_role=user_role,
            onboarding_acknowledged=onboarding_acknowledged,
            current_report_ref=current_report_ref,
            current_analyte=current_analyte,
            last_intent=last_intent,
            transient_ui_context=transient_ui_context,
            conversation_state=conversation_state or ConversationState(),
            response_style=resolved_style,
        )
        context._pending_ocr_review = bool(pending_ocr_review)
        return context


class SuggestedActionType(StrEnum):
    OPEN_REPORT = "OPEN_REPORT"
    VIEW_ABNORMAL = "VIEW_ABNORMAL"
    VIEW_HISTORY = "VIEW_HISTORY"
    VIEW_TREND = "VIEW_TREND"
    VIEW_DOCTOR_QUESTIONS = "VIEW_DOCTOR_QUESTIONS"
    CONFIRM_OCR = "CONFIRM_OCR"
    RETRY = "RETRY"


class _ActionBase(BaseModel):
    @model_validator(mode="before")
    @classmethod
    def _reject_executable_strings(cls, data: object) -> object:
        if isinstance(data, dict):
            for key, value in data.items():
                if key == "action":
                    continue
                if isinstance(value, str) and value.strip().casefold().startswith("javascript:"):
                    raise ValueError("executable string values are not allowed")
        return data


class OpenReportAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.OPEN_REPORT] = SuggestedActionType.OPEN_REPORT
    report_ref: ServerReference


class ViewAbnormalAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.VIEW_ABNORMAL] = SuggestedActionType.VIEW_ABNORMAL
    report_ref: ServerReference | None = None


class ViewHistoryAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.VIEW_HISTORY] = SuggestedActionType.VIEW_HISTORY


class ViewTrendAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.VIEW_TREND] = SuggestedActionType.VIEW_TREND
    analyte_id: ServerReference


class ViewDoctorQuestionsAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.VIEW_DOCTOR_QUESTIONS] = SuggestedActionType.VIEW_DOCTOR_QUESTIONS
    report_ref: ServerReference | None = None


class ConfirmOcrAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.CONFIRM_OCR] = SuggestedActionType.CONFIRM_OCR
    review_ref: ServerReference


class RetryAction(_ActionBase):
    model_config = ConfigDict(extra="forbid")

    action: Literal[SuggestedActionType.RETRY] = SuggestedActionType.RETRY
    reason_code: ReasonCode | None = None


SuggestedAction = Annotated[
    (
        OpenReportAction
        | ViewAbnormalAction
        | ViewHistoryAction
        | ViewTrendAction
        | ViewDoctorQuestionsAction
        | ConfirmOcrAction
        | RetryAction
    ),
    Field(discriminator="action"),
]


class DataType(StrEnum):
    ANALYSIS = "analysis"
    EXPLANATION = "explanation"
    HISTORY_SUMMARY = "history_summary"
    TREND = "trend"
    DOCTOR_QUESTIONS = "doctor_questions"
    BLOCKED = "blocked"
    NEEDS_INPUT = "needs_input"


class AnalysisDataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.ANALYSIS] = DataType.ANALYSIS
    indicators: list[IndicatorResultSchema]
    critical_alerts: list[CriticalAlertSchema] = Field(default_factory=list)
    has_critical_values: bool = False


# ORCH-V1.4C amendments 2 & 4: canonical critical verdicts emitted by the
# approved critical detector (critical_detector_node). This is the ONLY
# critical authority consulted by single-analyte composition. Plain HIGH/LOW
# are abnormal but never critical; a missing verdict is never inferred.
CANONICAL_CRITICAL_STATUSES = frozenset({"critical_low", "critical_high"})


def canonical_critical_side(critical_status):
    """Resolve THE canonical critical verdict for one indicator.

    Single critical authority: the current detector output carried in
    ``critical_status``. HIGH != CRITICAL, LOW != CRITICAL, and a missing
    verdict is never inferred as critical.
    """
    if critical_status in CANONICAL_CRITICAL_STATUSES:
        return critical_status
    return None


class ExplanationIndicatorFacts(BaseModel):
    """Atomic deterministic fact block for ONE analyte.

    Built exclusively by the dispatcher from the authoritative
    ``IndicatorResultSchema`` of the stored report. The response composer
    renders these facts verbatim; neither the composer LLM nor any other
    component may rewrite value, unit, reference status, range or critical
    facts. ``critical_status`` is the canonical output of the approved
    critical detector.
    """

    model_config = ConfigDict(extra="forbid")

    analyte_name: str = Field(min_length=1)
    value: float = Field(allow_inf_nan=False)
    unit: str = Field(min_length=1)
    status: str = Field(min_length=1)
    reference_low: float | None = Field(default=None, allow_inf_nan=False)
    reference_high: float | None = Field(default=None, allow_inf_nan=False)
    # True ONLY when BOTH authoritative bounds exist; one-sided/banded rules
    # must never receive a fabricated two-sided range (ORCH-V1.4C amendment 3).
    has_two_sided_reference_range: bool = False
    critical_status: Literal["critical_low", "critical_high"] | None = None
    # Approved critical-alert message copied VERBATIM from the same
    # detector run (report.critical_alerts). DISPLAY projection only -
    # never used to infer or alter the canonical verdict above.
    approved_critical_message: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def _two_sided_flag_must_match_bounds(self) -> ExplanationIndicatorFacts:
        both_present = self.reference_low is not None and self.reference_high is not None
        if self.has_two_sided_reference_range != both_present:
            raise ValueError(
                "has_two_sided_reference_range must be true if and only if both reference bounds are present"
            )
        return self


class ExplanationDataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.EXPLANATION] = DataType.EXPLANATION
    explanation: str
    sources: list[str] = Field(default_factory=list)
    presentation_mode: Literal[
        "current_fact_first",
        "status_first",
        "education_first",
        "mixed_explanation",
    ] = "mixed_explanation"
    # Deterministic fact block; None preserves the legacy prose-only contract.
    facts: ExplanationIndicatorFacts | None = None


class HistorySummaryPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.HISTORY_SUMMARY] = DataType.HISTORY_SUMMARY
    report_ref: ServerReference
    test_date: str
    summary: str
    status: str
    has_critical_values: bool
    result_count: int = Field(ge=0)
    reviewed_by_doctor: bool = False
    verification_status: VerificationStatus = "unverified"


class TrendDataPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.TREND] = DataType.TREND
    trend: TrendResponse


class DoctorQuestionsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.DOCTOR_QUESTIONS] = DataType.DOCTOR_QUESTIONS
    questions: list[GeneratedQuestion] = Field(default_factory=list)


class BlockedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.BLOCKED] = DataType.BLOCKED
    safety_notice: str
    disclaimer: str | None = None
    reason_code: ReasonCode | None = None


class NeedsInputPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_type: Literal[DataType.NEEDS_INPUT] = DataType.NEEDS_INPUT
    missing_fields: list[str] = Field(default_factory=list)
    prompt: str


DataPayload = Annotated[
    (
        AnalysisDataPayload
        | ExplanationDataPayload
        | HistorySummaryPayload
        | TrendDataPayload
        | DoctorQuestionsPayload
        | BlockedPayload
        | NeedsInputPayload
    ),
    Field(discriminator="data_type"),
]


class OrchestratorRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str
    ui_context: UIContext | None = None
    client_request_id: ServerReference | None = None

    # Hoi thoai dang noi. Optional CO CHU Y: ban frontend da deploy goi
    # `/orchestrator/message` khong kem id, va no phai tiep tuc chay chu khong
    # duoc 422. Thieu id thi server dung hoi thoai gan nhat cua benh nhan.
    #
    # Day chi la mot GOI Y ve hoi thoai, khong phai bang chung so huu: route
    # van tra id nay qua `conversation_repository` kem `patient_id` lay tu JWT.
    # Gui id cua nguoi khac se ra 404, khong phai doc duoc hoi thoai do.
    conversation_id: int | None = None


class OrchestratorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: IntentEnum
    status: ResponseStatus
    message: str
    data_type: DataType
    data: DataPayload
    reason_code: ReasonCode | None = None
    suggested_actions: list[SuggestedAction] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    safety_notice: str | None = None

    @model_validator(mode="after")
    def _data_type_must_match_payload(self) -> OrchestratorResponse:
        if self.data_type != self.data.data_type:
            raise ValueError("response data_type must match payload data_type")
        return self


class MessageStartedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ProgressPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: ProgressStage


class MessageCompletedPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    response: OrchestratorResponse


class StreamErrorPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str


StreamPayload = MessageStartedPayload | ProgressPayload | MessageCompletedPayload | StreamErrorPayload


class OrchestratorStreamEvent(BaseModel):
    """Public SSE event; intentionally excludes internal execution metadata."""

    model_config = ConfigDict(extra="forbid")

    contract_version: Literal["1.0"] = "1.0"
    event_id: ServerReference
    event_type: StreamEventType
    turn_id: ServerReference
    sequence: int = Field(ge=1)
    occurred_at: datetime
    payload: StreamPayload

    @model_validator(mode="after")
    def _payload_must_match_event_type(self) -> OrchestratorStreamEvent:
        expected_payload = {
            StreamEventType.MESSAGE_STARTED: MessageStartedPayload,
            StreamEventType.PROGRESS: ProgressPayload,
            StreamEventType.MESSAGE_COMPLETED: MessageCompletedPayload,
            StreamEventType.ERROR: StreamErrorPayload,
        }[self.event_type]
        if not isinstance(self.payload, expected_payload):
            raise ValueError("stream payload must match event_type")
        return self


__all__ = [
    "AnalysisDataPayload",
    "BlockedPayload",
    "canonical_critical_side",
    "ConfirmOcrAction",
    "ConversationState",
    "DataPayload",
    "DataType",
    "DoctorQuestionsPayload",
    "ExplanationDataPayload",
    "ExplanationIndicatorFacts",
    "HistorySummaryPayload",
    "IntentEnum",
    "NeedsInputPayload",
    "OpenReportAction",
    "OrchestratorRequest",
    "OrchestratorResponse",
    "OrchestratorStreamEvent",
    "OrchestratorRole",
    "OrchestratorSessionContext",
    "MessageCompletedPayload",
    "MessageStartedPayload",
    "ProgressPayload",
    "ProgressStage",
    "ReasonCode",
    "ResponseStatus",
    "RetryAction",
    "StreamErrorPayload",
    "StreamEventType",
    "StreamPayload",
    "SuggestedAction",
    "SuggestedActionType",
    "TrendDataPayload",
    "UIContext",
    "ViewAbnormalAction",
    "ViewDoctorQuestionsAction",
    "ViewHistoryAction",
    "ViewTrendAction",
]
