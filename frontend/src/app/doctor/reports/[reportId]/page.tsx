"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DoctorFindingCard from "@/components/doctor/DoctorFindingCard";
import DoctorReportSidebar from "@/components/doctor/DoctorReportSidebar";
import DoctorReviewProgressBar from "@/components/doctor/DoctorReviewProgressBar";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";
import {
  clearSession,
  completeDoctorReport,
  fetchDoctorReport,
  reviewDoctorFinding,
  UnauthorizedError,
} from "@/lib/api";
import { formatDate, formatMoment } from "@/lib/patientUi.mjs";
import type { DoctorFinding, DoctorReportDetail } from "@/types/doctor";
import type { ReportQuestion } from "@/types/history";

function genderText(value: string | null) {
  if (value === "male") return "Nam";
  if (value === "female") return "Nữ";
  if (value === "other") return "Khác";
  return "Khác";
}

export default function DoctorReportPage() {
  const params = useParams<{ reportId: string }>();
  const router = useRouter();
  const reportId = Number(params.reportId);
  const [detail, setDetail] = useState<DoctorReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completeBusy, setCompleteBusy] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [backTab, setBackTab] = useState("pending");

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- query string is client-only in this page.
    setBackTab(new URLSearchParams(window.location.search).get("tab") || "pending");
  }, []);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        setDetail(await fetchDoctorReport(reportId));
      } catch (caught) {
        if (caught instanceof UnauthorizedError) {
          clearSession();
          router.replace("/");
          return;
        }
        setError(caught instanceof Error ? caught.message : "Không mở được phiếu.");
      } finally {
        setLoading(false);
      }
    }
    if (Number.isFinite(reportId)) void load();
  }, [reportId, router]);

  const progress = useMemo(() => {
    const findings = detail?.findings ?? [];
    return {
      total: findings.length,
      reviewed: findings.filter((finding) => finding.review_outcome !== "pending").length,
    };
  }, [detail]);

  async function handleReview(
    findingId: number,
    outcome: "agreed" | "corrected" | "skipped",
    note?: string,
  ) {
    const updated = await reviewDoctorFinding(findingId, outcome, note);
    setDetail((current) => {
      if (!current) return current;
      return {
        ...current,
        findings: current.findings.map((finding) =>
          finding.id === findingId ? updated.finding : finding,
        ),
      };
    });
  }

  function updateQuestion(question: ReportQuestion) {
    setDetail((current) => {
      if (!current) return current;
      return {
        ...current,
        questions: current.questions.map((item) => item.id === question.id ? question : item),
      };
    });
  }

  async function handleComplete() {
    if (!detail) return;
    const confirmed = window.confirm(
      "Xác nhận hoàn tất kiểm chứng phiếu này? Bệnh nhân sẽ thấy phiếu đã được bác sĩ kiểm chứng.",
    );
    if (!confirmed) return;
    setCompleteBusy(true);
    setError(null);
    try {
      await completeDoctorReport(detail.report.id);
      setToast("Phiếu đã được kiểm chứng.");
      router.replace(`/doctor?tab=${backTab}`);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không hoàn tất được phiếu.");
    } finally {
      setCompleteBusy(false);
    }
  }

  if (loading) {
    return (
      <main className="doctor-portal">
        <section className="doctor-report-shell">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </section>
      </main>
    );
  }

  if (error || !detail) {
    return (
      <main className="doctor-portal">
        <section className="doctor-report-shell">
          <div className="doctor-error-state" role="alert">
            <p>{error || "Không tìm thấy phiếu xét nghiệm."}</p>
            <Link href={`/doctor?tab=${backTab}`}>Quay lại hàng đợi</Link>
          </div>
        </section>
      </main>
    );
  }

  const readOnly = detail.report.verification_status === "verified";
  const severity = detail.findings.some((finding) => finding.classification === "critical")
    ? "critical"
    : detail.findings.some((finding) => finding.classification === "abnormal")
      ? "abnormal"
      : "normal";
  const flagsByFinding = new Map<number, typeof detail.flags>();
  for (const flag of detail.flags) {
    if (flag.finding_id === null) continue;
    flagsByFinding.set(flag.finding_id, [...(flagsByFinding.get(flag.finding_id) ?? []), flag]);
  }

  return (
    <main className="doctor-portal">
      {toast && <div className="doctor-toast" role="status">{toast}</div>}
      <section className="doctor-report-shell">
        <header className="doctor-report-header">
          <Link href={`/doctor?tab=${backTab}`}>‹ Hàng đợi</Link>
          <div className="doctor-report-header__row">
            <div>
              <h1>{detail.patient.name}</h1>
              <p>
                {genderText(detail.patient.gender)} · {detail.patient.age ?? "-"} tuổi · Xét nghiệm{" "}
                {formatDate(detail.report.test_date)} · {detail.report.input_method === "ocr" ? "OCR" : "nhập tay"}
              </p>
            </div>
            <div className="doctor-report-header__badges">
              <SeverityBadge level={severity} />
              <VerificationBadge status={detail.report.verification_status} />
            </div>
          </div>
        </header>

        {readOnly && (
          <div className="doctor-verified-banner">
            <span aria-hidden="true">✓</span>
            Phiếu đã được kiểm chứng bởi {detail.report.verified_by || "bác sĩ"}
            {detail.report.verified_at ? ` lúc ${formatMoment(detail.report.verified_at)}` : ""}.
          </div>
        )}

        {error && <div className="doctor-error-state" role="alert">{error}</div>}

        <div className="doctor-report-grid">
          <section className="doctor-finding-list" aria-label="Danh sách luận điểm">
            {detail.findings.map((finding: DoctorFinding) => (
              <DoctorFindingCard
                key={finding.id}
                finding={finding}
                flags={flagsByFinding.get(finding.id) ?? []}
                readOnly={readOnly}
                onReview={handleReview}
              />
            ))}
          </section>
          <DoctorReportSidebar detail={detail} readOnly={readOnly} onQuestionUpdated={updateQuestion} />
        </div>
      </section>
      <DoctorReviewProgressBar
        reviewed={progress.reviewed}
        total={progress.total}
        busy={completeBusy}
        readOnly={readOnly}
        onComplete={() => void handleComplete()}
      />
    </main>
  );
}
