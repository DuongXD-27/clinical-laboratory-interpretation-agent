import type { IndicatorResult } from "./analysis";

type VerificationStatus = "unverified" | "pending_review" | "verified";

export type ReportQuestion = {
  id: number;
  /** null với câu dự phòng hoặc câu gộp nhiều chỉ số. */
  indicator_id: number | null;
  question_text: string;
  priority: "critical" | "abnormal" | "unknown" | "fallback";
  status: "generated" | "sent_to_doctor" | "answered";
  display_order: number;
  /** Bệnh nhân đã tick chọn mang câu này đi khám. */
  is_selected: boolean;
  /** Do bác sĩ viết — hiển thị kèm tên, KHÔNG dán khuyến cáo tự động. */
  answer_text: string | null;
  answered_at: string | null;
  answered_by_username: string | null;
  created_at: string;
};

export type DoctorNote = {
  id: number;
  doctor_id: number;
  target_type: "report" | "indicator" | "report_question";
  target_id: number;
  note_text: string;
  created_at: string;
  doctor_username: string | null;
};

export type ReportDoctorView = {
  doctor_id: number;
  viewed_at: string;
  doctor_username: string | null;
};

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
  /** Đã có bác sĩ xem (bấm nút) hoặc đã có ghi chú. */
  reviewed_by_doctor: boolean;
  has_doctor_notes: boolean;
  verification_status: VerificationStatus;
  verified_by_username: string | null;
  verified_at: string | null;
};

export type LabReportDetail = LabReportSummary & {
  // Snapshot lúc xét nghiệm. Tên field theo schema đã gộp vào main; bản trước
  // đọc `patient_age`/`patient_gender` nên render ra "undefined tuổi".
  patient_age_at_test: number | null;
  patient_gender_at_test: string | null;
  language: string;
  guardrail_passed: boolean;
  disclaimer?: string;
  indicators: IndicatorResult[];
  questions: ReportQuestion[];
  doctor_notes: DoctorNote[];
  doctor_views: ReportDoctorView[];
};

export type LabReportListResponse = {
  total: number;
  items: LabReportSummary[];
};
