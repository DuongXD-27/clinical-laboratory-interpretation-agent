export type CriticalAlert = {
  indicator_name: string;
  value: number;
  unit: string;
  message: string;
};

export type IndicatorResult = {
  name: string;
  value: number;
  unit: string;
  reference_low?: number | null;
  reference_high?: number | null;
  status: string;
  critical_status?: "critical_low" | "critical_high" | null;
  is_abnormal: boolean;
  is_critical: boolean;
  explanation?: string;
  review_outcome?: "pending" | "agreed" | "corrected" | "skipped";
  doctor_note?: string | null;
  ai_text_snapshot?: string | null;
  reviewed_by_username?: string | null;
  reviewed_at?: string | null;
  sources?: string[];
  /** Nhóm chức năng (ADR-010 CRIT-TREND-06) — null khi chỉ số chưa khớp được nhóm nào. */
  section?: string | null;
  section_label?: string | null;
  rule_type?: string | null;
  band_id?: string | null;
  upper_operator?: string | null;
  evaluation_reason?: string | null;
};

export type AnalysisResult = {
  indicators: IndicatorResult[];
  critical_alerts: CriticalAlert[];
  has_critical_values?: boolean;
  summary?: string;
  disclaimer?: string;
  out_of_scope_indicators?: string[];
  saved?: boolean;
  duplicate?: boolean;
  report_id?: number | null;
  existing_report_id?: number | null;
  /** Câu hỏi gợi ý mang đi hỏi bác sĩ. Rỗng khi mọi chỉ số đều bình thường. */
  questions_for_doctor?: string[];
  /** null với khách và bác sĩ — không có phiếu nào được lưu. */
  saved_report_id?: number | null;
  patient_info?: {
    name?: string;
    age?: number;
    gender?: string;
  };
};

export type TrendFilter = "latest5" | "three_months";

export type TrendAnalyteSummary = {
  analyte_canonical: string;
  display_name: string;
  canonical_unit: string;
  result_count: number;
  trend_available: boolean;
  section?: string | null;
  section_label?: string | null;
};

export type TrendPoint = {
  report_id: number;
  test_date: string;
  value: number;
  assessment: string;
};

export type TrendResponse = {
  analyte_canonical: string;
  display_name: string;
  canonical_unit: string;
  filter: TrendFilter;
  result_count: number;
  trend_available: boolean;
  points: TrendPoint[];
  observed_direction?: "increasing" | "decreasing" | "stable" | null;
  reason?: string | null;
  section?: string | null;
  section_label?: string | null;
  /** ADR-010 CRIT-TREND-03: điểm mới nhất đã vượt ngưỡng nguy kịch (chỉ glucose/potassium). */
  critical_status?: "critical_low" | "critical_high" | null;
  /** ADR-010 CRIT-TREND-03: điểm mới nhất đang tiến gần ngưỡng nguy kịch (trong 10%). */
  approaching_critical?: boolean;
  critical_alert?: CriticalAlert | null;
  /** ADR-010 CRIT-TREND-02: khoảng "bình thường" khớp theo sex/age tại lần đo gần nhất. */
  reference_low?: number | null;
  reference_high?: number | null;
  /** ADR-010 CRIT-TREND-03/05: ngưỡng nguy kịch active, cùng đơn vị với `canonical_unit`. */
  critical_low?: number | null;
  critical_high?: number | null;
};

export type HeatmapColumn = {
  report_id: number;
  test_date: string;
};

export type HeatmapCell = {
  report_id: number;
  test_date: string;
  value: number;
  unit: string;
  status: string;
  critical_status?: string | null;
  reference_low?: number | null;
  reference_high?: number | null;
};

export type HeatmapRow = {
  analyte_canonical: string;
  /** Cùng độ dài/thứ tự với `SectionHeatmapResponse.columns`; null = phiếu đó không đo chỉ số này. */
  cells: (HeatmapCell | null)[];
};

export type SectionHeatmapResponse = {
  section: string;
  section_label: string;
  columns: HeatmapColumn[];
  rows: HeatmapRow[];
};

export type TrendExplanationResponse = {
  explanation: string;
  fallback: boolean;
  reason?: string | null;
};

export type TrendReviewStatus = "PENDING" | "REVIEWED" | "CANCELLED" | "REJECTED";
export type TrendReviewAssessment = "confirmed" | "corrected" | "needs_follow_up";

export type TrendReview = {
  id: number;
  patient_id: number;
  analyte_canonical: string;
  display_name: string;
  canonical_unit: string;
  trend_filter: TrendFilter;
  trend_snapshot: TrendResponse;
  trend_snapshot_hash: string;
  llm_explanation_snapshot: string;
  status: TrendReviewStatus;
  requested_at: string;
  reviewed_by_doctor_id?: number | null;
  reviewed_by_username?: string | null;
  reviewed_at?: string | null;
  doctor_assessment?: TrendReviewAssessment | null;
  doctor_comment?: string | null;
};

export type TrendReviewPatientState = {
  latest_review: TrendReview | null;
  latest_historical_review: TrendReview | null;
  pending_request: TrendReview | null;
  can_request_review: boolean;
  reason?: string | null;
  current_trend_hash?: string | null;
  history_count: number;
};

export type TrendReviewRequestResponse = {
  review: TrendReview;
  created: boolean;
};

export type TrendReviewHistoryResponse = {
  total: number;
  items: TrendReview[];
};

export type DoctorTrendReviewSummary = {
  id: number;
  patient_id: number;
  patient_name: string;
  analyte_canonical: string;
  display_name: string;
  trend_filter: TrendFilter;
  point_count: number;
  status: TrendReviewStatus;
  requested_at: string;
  reviewed_at?: string | null;
  reviewed_by_username?: string | null;
};

export type DoctorTrendReviewListResponse = {
  total: number;
  items: DoctorTrendReviewSummary[];
};

export type DoctorTrendReviewDetail = {
  review: TrendReview;
  patient: {
    id: number;
    name: string;
    age: number | null;
    gender: string | null;
  };
};
