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
  sources?: string[];
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
};

export type TrendExplanationResponse = {
  explanation: string;
  fallback: boolean;
  reason?: string | null;
};
