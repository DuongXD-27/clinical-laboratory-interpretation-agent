"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import DoctorFindingCard from "@/components/doctor/DoctorFindingCard";
import DoctorReportSidebar from "@/components/doctor/DoctorReportSidebar";
import DoctorReviewProgressBar from "@/components/doctor/DoctorReviewProgressBar";
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import DoctorSection from "@/components/doctor/DoctorSection";
import DoctorStatePanel from "@/components/doctor/DoctorStatePanel";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";
import ClinicalConfirmDialog from "@/components/common/ClinicalConfirmDialog";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CheckCircle2, ClipboardCheck } from "lucide-react";
import { motionElementName } from "@/lib/motion";
import {
  clearSession,
  completeDoctorReport,
  fetchDoctorReport,
  reviewDoctorFinding,
  UnauthorizedError,
} from "@/lib/api";
import { formatDate, formatMoment, formatPatientDemographics } from "@/lib/patientUi.mjs";
import type { DoctorFinding, DoctorReportDetail } from "@/types/doctor";
import type { ReportQuestion } from "@/types/history";

export default function DoctorReportPage() {
  const params = useParams<{ reportId: string }>();
  const router = useRouter();
  const reportId = Number(params.reportId);
  const [detail, setDetail] = useState<DoctorReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [completeBusy, setCompleteBusy] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
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
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Kiểm chứng báo cáo" title="Đang tải phiếu xét nghiệm…" />
        <section className="doctor-detail-skeleton" aria-label="Đang tải phiếu xét nghiệm" role="status">
          <Skeleton className="doctor-detail-skeleton__progress" />
          <div className="doctor-detail-skeleton__grid">
            <div className="doctor-detail-skeleton__primary">
              <Skeleton />
              <Skeleton />
            </div>
            <Skeleton className="doctor-detail-skeleton__sidebar" />
          </div>
        </section>
      </div>
    );
  }

  if (error || !detail) {
    return (
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Kiểm chứng báo cáo" title="Không mở được phiếu xét nghiệm" />
        <DoctorStatePanel
          kind="error"
          title="Không mở được phiếu xét nghiệm"
          description={error || "Không tìm thấy phiếu xét nghiệm."}
          action={(
            <Button render={<Link href={`/doctor?tab=${backTab}`} transitionTypes={["nav-back"]} />} nativeButton={false} variant="outline">
              Quay lại hàng đợi
            </Button>
          )}
        />
      </div>
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
    <div className="doctor-page doctor-detail-page">
      {toast && <div className="doctor-toast" role="status">{toast}</div>}
      <DoctorPageHeader
        eyebrow={`Kiểm chứng báo cáo · Phiếu #${detail.report.id}`}
        title={detail.patient.name}
        description={
          <p>
            {formatPatientDemographics(detail.patient.gender, detail.patient.age)} · Xét nghiệm{" "}
            {formatDate(detail.report.test_date)} · {detail.report.input_method === "ocr" ? "OCR" : "nhập tay"}
          </p>
        }
        actions={<><SeverityBadge level={severity} /><VerificationBadge status={detail.report.verification_status} /></>}
        backHref={`/doctor?tab=${backTab}`}
        backLabel="Hàng đợi đánh giá"
        transitionName={motionElementName("doctor-report", detail.report.id)}
      />

      {readOnly && (
        <div className="doctor-verified-banner">
          <CheckCircle2 aria-hidden="true" />
          Phiếu đã được kiểm chứng bởi {detail.report.verified_by || "bác sĩ"}
          {detail.report.verified_at ? ` lúc ${formatMoment(detail.report.verified_at)}` : ""}.
        </div>
      )}

      {error && <div className="doctor-error-state" role="alert">{error}</div>}

      <DoctorReviewProgressBar
        reviewed={progress.reviewed}
        total={progress.total}
        busy={completeBusy}
        readOnly={readOnly}
        onComplete={() => setConfirmOpen(true)}
      />

      <div className="doctor-report-grid">
        <DoctorSection
          className="doctor-results-section"
          title="Kết quả lâm sàng"
          description={`${progress.total} luận điểm cần đối chiếu với dữ liệu xét nghiệm và diễn giải AI.`}
          icon={ClipboardCheck}
          meta={<span className="doctor-section-count">{progress.reviewed}/{progress.total} đã xử lý</span>}
        >
          <div className="doctor-finding-list" aria-label="Danh sách luận điểm">
            {detail.findings.map((finding: DoctorFinding) => (
              <DoctorFindingCard
                key={finding.id}
                finding={finding}
                flags={flagsByFinding.get(finding.id) ?? []}
                readOnly={readOnly}
                onReview={handleReview}
              />
            ))}
          </div>
        </DoctorSection>
        <DoctorReportSidebar detail={detail} readOnly={readOnly} onQuestionUpdated={updateQuestion} />
      </div>

      <ClinicalConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Hoàn tất kiểm chứng"
        description="Sau khi hoàn tất, bệnh nhân sẽ thấy phiếu này đã được bác sĩ kiểm chứng."
        confirmLabel="Hoàn tất kiểm chứng"
        cancelLabel="Quay lại"
        tone="neutral"
        loading={completeBusy}
        onConfirm={handleComplete}
      />
    </div>
  );
}
