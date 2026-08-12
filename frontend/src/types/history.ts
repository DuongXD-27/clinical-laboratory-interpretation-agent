import type { IndicatorResult } from "./analysis";

export type LabReportSummary = {
  id: number;
  patient_username: string;
  test_date: string;
  created_at: string;
  indicator_count: number;
  abnormal_count: number;
  has_critical_values: boolean;
  source: "manual" | "ocr";
  summary?: string;
};

export type LabReportDetail = LabReportSummary & {
  patient_age: number;
  patient_gender: string;
  language: string;
  guardrail_passed: boolean;
  indicators: IndicatorResult[];
};

export type LabReportListResponse = {
  total: number;
  items: LabReportSummary[];
};
