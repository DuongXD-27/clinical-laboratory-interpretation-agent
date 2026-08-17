import type { ReportQuestion } from "./history";

export type VerificationStatus = "unverified" | "pending_review" | "verified";
export type ReviewOutcome = "pending" | "agreed" | "corrected" | "skipped";
export type SeverityLevel = "critical" | "abnormal" | "normal";

export type ReviewFlag = {
  code: "CRITICAL_VALUE" | "LOW_OCR_CONFIDENCE" | "PATIENT_HAS_QUESTIONS";
  detail: string;
  severity: "high" | "medium";
  finding_id: number | null;
};

export type DoctorQueueItem = {
  report_id: number;
  patient_name: string;
  patient_id: number;
  test_date: string;
  severity_level: SeverityLevel;
  flags: ReviewFlag[];
  findings_reviewed: number;
  findings_total: number;
  queued_at: string | null;
};

export type DoctorQueueCounts = {
  critical: number;
  ocr: number;
  questions: number;
  pending: number;
  verified: number;
};

export type DoctorQueueResponse = {
  items: DoctorQueueItem[];
  counts: DoctorQueueCounts;
  page: number;
  page_size: number;
  total: number;
};

export type DoctorReport = {
  id: number;
  test_date: string;
  verification_status: VerificationStatus;
  verified_by: string | null;
  verified_at: string | null;
  input_method: "manual" | "ocr";
  original_image_url: string | null;
};

export type DoctorPatient = {
  id: number;
  name: string;
  age: number | null;
  gender: string | null;
};

export type DoctorFinding = {
  id: number;
  metric_code: string | null;
  metric_name: string;
  value: number;
  unit: string;
  reference_range: string;
  classification: SeverityLevel;
  ai_text: string;
  review_outcome: ReviewOutcome;
  doctor_note: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
};

export type DoctorReportDetail = {
  report: DoctorReport;
  patient: DoctorPatient;
  flags: ReviewFlag[];
  findings: DoctorFinding[];
  questions: ReportQuestion[];
};

export type FindingReviewResponse = {
  finding: DoctorFinding;
  report_progress: {
    reviewed: number;
    total: number;
  };
};
