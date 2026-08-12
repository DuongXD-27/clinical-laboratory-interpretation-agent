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
  patient_info?: {
    name?: string;
    age?: number;
    gender?: string;
  };
};
