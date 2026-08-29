"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import IndicatorResultCard from "@/components/patient/IndicatorResultCard";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";
import ClinicalConfirmDialog from "@/components/common/ClinicalConfirmDialog";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { formatDate, reportTone } from "@/lib/patientUi.mjs";
import { groupBySection } from "@/lib/trendUi.mjs";
import type { CriticalAlert, IndicatorResult } from "@/types/analysis";
import type { ReportQuestion } from "@/types/history";
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import { ArrowLeft, Trash2 } from "lucide-react";

type ReportDetail = {
  id: number;
  test_date: string;
  status: string;
  result_count: number;
  summary: string;
  disclaimer: string;
  created_at: string;
  indicators: (IndicatorResult & {
    analyte_raw?: string | null;
    analyte_canonical?: string | null;
  })[];
  critical_alerts: CriticalAlert[];
  questions: ReportQuestion[];
  out_of_scope_entries: { id: number; raw_indicator_name: string; created_at: string }[];
  verification_status: "unverified" | "pending_review" | "verified";
  verified_by_username: string | null;
  verified_at: string | null;
};

export default function PatientReportDetail() {
  const router = useRouter();
  const params = useParams<{ reportId: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [confirmDeleteOpen, setConfirmDeleteOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/login");
      return;
    }
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await authFetch(`/api/v1/patient/me/lab-reports/${params.reportId}`);
        if (response.status === 401 || response.status === 403) {
          clearSession();
          router.replace("/login");
          return;
        }
        if (!response.ok) throw new Error("Không tìm thấy phiếu xét nghiệm.");
        setReport(await response.json());
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "Không tải được phiếu xét nghiệm.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [params.reportId, router]);

  async function deleteReport() {
    setDeleting(true);
    setError(null);
    try {
      const response = await authFetch(`/api/v1/patient/me/lab-reports/${params.reportId}`, { method: "DELETE" });
      if (!response.ok) throw new Error("Chưa xóa được phiếu xét nghiệm.");
      router.replace("/patient/history");
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Chưa xóa được phiếu xét nghiệm.");
      setDeleting(false);
    }
  }

  if (loading) {
    return (
      <section className="patient-card p-5 sm:p-7">
        <div className="loading-message" role="status">Đang tải phiếu xét nghiệm...</div>
      </section>
    );
  }

  if (error || !report) {
    return (
      <section className="patient-card p-5 sm:p-7">
        <div role="alert" className="error-message">{error ?? "Không tìm thấy phiếu xét nghiệm."}</div>
        <Link href="/patient/history" className="secondary-button mt-4 inline-flex">Quay lại lịch sử</Link>
      </section>
    );
  }

  const abnormalCount = report.indicators.filter((indicator) => indicator.is_abnormal).length;
  const indicatorGroups = groupBySection(report.indicators);
  const reportSeverity = reportTone(report.status) as "critical" | "abnormal" | "normal";

  return (
    <div className="patient-page-layout report-detail-layout">
      <PatientPageHeader
        eyebrow="Phiếu đã lưu"
        title="Kết quả xét nghiệm"
        description={formatDate(report.test_date)}
        className="report-detail-heading"
        actions={(
          <div className="report-action-cluster">
            <Link href="/patient/history" className="patient-btn-secondary">
              <ArrowLeft aria-hidden="true" />
              Quay lại lịch sử
            </Link>
            <button
              type="button"
              onClick={() => setConfirmDeleteOpen(true)}
              disabled={deleting}
              className="patient-btn-danger"
            >
              <Trash2 aria-hidden="true" />
              {deleting ? "Đang xóa..." : "Xóa phiếu"}
            </button>
          </div>
        )}
      />

      {report.critical_alerts?.length > 0 && (
        <div className="critical-report-notice" role="alert">
          <strong>Cần chú ý ngay</strong>
          {report.critical_alerts.map((alert, index) => <p key={index}>{alert.message}</p>)}
        </div>
      )}

      <section className="patient-card p-5 sm:p-7" aria-labelledby="report-summary-title">
        <div className="report-summary-row">
          <div>
            <h3 id="report-summary-title">Tóm tắt phiếu</h3>
            <p>{report.summary}</p>
          </div>
          <div className="report-summary-stats">
            <div><strong>{report.result_count}</strong><span>chỉ số</span></div>
            <div><strong>{abnormalCount}</strong><span>bất thường</span></div>
            <SeverityBadge level={reportSeverity} />
            <VerificationBadge status={report.verification_status} />
          </div>
        </div>

        {report.out_of_scope_entries.length > 0 && (
          <div className="info-message mt-5" role="status">
            <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
            <p className="mt-1">{report.out_of_scope_entries.map((entry) => entry.raw_indicator_name).join(", ")}</p>
          </div>
        )}

        <div className="mt-6 flex flex-col gap-6">
          {indicatorGroups.map((group) => (
            <div key={group.label}>
              <h4 className="indicator-group-title text-sm font-semibold text-slate-800">{group.label}</h4>
              <div className="indicator-card-grid mt-2">
                {group.items.map((indicator, index) => (
                  <IndicatorResultCard key={`${indicator.name}-${index}`} indicator={indicator} />
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="disclaimer-box mt-6" role="note" aria-label="Lưu ý y khoa">
          <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
          {report.verification_status === "verified" ? (
            <p className="mt-1">
              Kết quả đã được bác sĩ kiểm chứng trong phạm vi phiếu này.
              {report.verified_by_username || report.verified_at ? (
                <>
                  {" "}Đã được kiểm chứng bởi {report.verified_by_username || "bác sĩ"}
                  {report.verified_at ? ` ngày ${formatDate(report.verified_at)}` : ""}.
                </>
              ) : null}
            </p>
          ) : (
            <p className="mt-1">{report.disclaimer}</p>
          )}
        </div>
      </section>

      <QuestionsForDoctorPanel
        questions={report.questions?.map((question) => question.question_text) ?? []}
        reportId={report.id}
        onUnauthorized={() => {
          clearSession();
          router.replace("/login");
        }}
      />

      <ClinicalConfirmDialog
        open={confirmDeleteOpen}
        onOpenChange={setConfirmDeleteOpen}
        title="Xóa kết quả xét nghiệm"
        description="Bạn có chắc muốn xóa kết quả xét nghiệm này khỏi lịch sử của bạn? Hành động này không thể hoàn tác."
        confirmLabel="Xóa kết quả"
        cancelLabel="Quay lại"
        tone="critical"
        loading={deleting}
        onConfirm={deleteReport}
      />
    </div>
  );
}
