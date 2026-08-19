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
  reason?: string | null;
  section?: string | null;
  section_label?: string | null;
  /** ADR-010 CRIT-TREND-03: điểm mới nhất đã vượt ngưỡng nguy kịch (chỉ glucose/potassium). */
  critical_status?: "critical_low" | "critical_high" | null;
  /** ADR-010 CRIT-TREND-03: điểm mới nhất đang tiến gần ngưỡng nguy kịch (trong 10%). */
  approaching_critical?: boolean;
};

export type TrendExplanationResponse = {
  explanation: string;
  fallback: boolean;
  reason?: string | null;
};
