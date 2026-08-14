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
