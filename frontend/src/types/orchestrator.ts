import type { CriticalAlert, IndicatorResult, TrendResponse } from "./analysis";

export type OrchestratorStatus = "success" | "needs_input" | "blocked" | "error";

export type OrchestratorReasonCode =
  | "ONBOARDING_REQUIRED"
  | "OCR_REVIEW_REQUIRED"
  | "OCR_CONFIRM_INVALID"
  | "MEDICAL_DIAGNOSIS_REQUEST"
  | "MEDICAL_CAUSE_REQUEST"
  | "TREATMENT_REQUEST"
  | "UNSUPPORTED_ANALYTE"
  | "UNSUPPORTED_CAPABILITY"
  | "AMBIGUOUS_CONTEXT"
  | "AUTH_EXPIRED"
  | "REPORT_NOT_FOUND_OR_UNAUTHORIZED"
  | "DB_UNAVAILABLE"
  | "LLM_UNAVAILABLE"
  | "RAG_UNAVAILABLE"
  | "TREND_INSUFFICIENT_POINTS"
  | "TREND_UNIT_INCONSISTENT"
  | "UNKNOWN_INTENT"
  | "GUARDRAIL_BLOCKED"
  | "INTERNAL_WORKFLOW_ERROR";

export type OrchestratorIntent =
  | "UNSUPPORTED_OR_UNSAFE"
  | "ANALYZE_REPORT"
  | "EXPLAIN_CURRENT_RESULT"
  | "VIEW_HISTORY"
  | "ANALYZE_TREND"
  | "GET_DOCTOR_QUESTIONS"
  | "SAFE_GENERAL"
  | "APP_HELP";

export type OrchestratorDataType =
  | "analysis"
  | "explanation"
  | "history_summary"
  | "trend"
  | "doctor_questions"
  | "blocked"
  | "needs_input";

export type OrchestratorUiContext = {
  screen?: string;
  view?: string;
  candidate_analyte?: string;
  candidate_report_ref?: string;
};

export type SuggestedAction =
  | { action: "OPEN_REPORT"; report_ref: string }
  | { action: "VIEW_ABNORMAL"; report_ref?: string | null }
  | { action: "VIEW_HISTORY" }
  | { action: "VIEW_TREND"; analyte_id: string }
  | { action: "VIEW_DOCTOR_QUESTIONS"; report_ref?: string | null }
  | { action: "CONFIRM_OCR"; review_ref: string }
  | { action: "RETRY"; reason_code?: OrchestratorReasonCode | null };

export type AnalysisPayload = {
  data_type: "analysis";
  indicators: IndicatorResult[];
  critical_alerts?: CriticalAlert[];
  has_critical_values?: boolean;
};

export type ExplanationPayload = {
  data_type: "explanation";
  explanation: string;
  sources?: string[];
};

export type HistorySummaryPayload = {
  data_type: "history_summary";
  report_ref: string;
  test_date: string;
  summary: string;
  status: string;
  has_critical_values: boolean;
  result_count: number;
  reviewed_by_doctor?: boolean;
  verification_status?: string;
};

export type TrendPayload = {
  data_type: "trend";
  trend: TrendResponse;
};

export type DoctorQuestionPayload = {
  data_type: "doctor_questions";
  questions: Array<{
    text?: string;
    question_text?: string;
    priority?: string;
    display_order?: number;
  }>;
};

export type BlockedPayload = {
  data_type: "blocked";
  safety_notice: string;
  disclaimer?: string | null;
  reason_code?: OrchestratorReasonCode | null;
};

export type NeedsInputPayload = {
  data_type: "needs_input";
  missing_fields?: string[];
  prompt: string;
};

export type OrchestratorPayload =
  | AnalysisPayload
  | ExplanationPayload
  | HistorySummaryPayload
  | TrendPayload
  | DoctorQuestionPayload
  | BlockedPayload
  | NeedsInputPayload;

export type OrchestratorResponse = {
  intent: OrchestratorIntent;
  status: OrchestratorStatus;
  message: string;
  data_type: OrchestratorDataType;
  data: OrchestratorPayload;
  reason_code?: OrchestratorReasonCode | null;
  suggested_actions?: SuggestedAction[];
  sources?: string[];
  safety_notice?: string | null;
};

export type OrchestratorProgressStage =
  | "routing"
  | "medical_context"
  | "longitudinal_retrieval"
  | "response_composition";

export type OrchestratorStreamEventType =
  | "message.started"
  | "progress"
  | "message.completed"
  | "error";

type StreamEnvelope<TType extends OrchestratorStreamEventType, TPayload> = {
  contract_version: "1.0";
  event_id: string;
  event_type: TType;
  turn_id: string;
  sequence: number;
  occurred_at: string;
  payload: TPayload;
};

export type MessageStartedEvent = StreamEnvelope<"message.started", Record<string, never>>;
export type ProgressEvent = StreamEnvelope<"progress", { stage: OrchestratorProgressStage }>;
export type MessageCompletedEvent = StreamEnvelope<"message.completed", { response: OrchestratorResponse }>;
export type StreamErrorEvent = StreamEnvelope<"error", { message: string }>;

export type OrchestratorStreamEvent =
  | MessageStartedEvent
  | ProgressEvent
  | MessageCompletedEvent
  | StreamErrorEvent;
