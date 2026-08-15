"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import SourcesDisclosure from "@/components/patient/SourcesDisclosure";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";
import { formatDate, indicatorStatusText, reportStatusText, reportTone } from "@/lib/patientUi.mjs";
import type { CriticalAlert, IndicatorResult } from "@/types/analysis";
import type { ReportQuestion } from "@/types/history";

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
};

export default function PatientReportDetail() {
  const router = useRouter();
  const params = useParams<{ reportId: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
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
        if (response.status === 401) {
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
    if (!window.confirm("Bạn có chắc muốn xóa kết quả xét nghiệm này?")) return;
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
    return <section className="patient-card p-5 sm:p-7"><div className="loading-message" role="status">Đang tải phiếu xét nghiệm...</div></section>;
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

  return (
    <div className="report-detail-layout">
      <div className="page-section-heading report-detail-heading">
        <div>
          <span className="eyebrow">Phiếu đã lưu</span>
          <h2>Kết quả xét nghiệm</h2>
          <p>{formatDate(report.test_date)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/patient/history" className="secondary-button">Quay lại lịch sử</Link>
          <button type="button" onClick={deleteReport} disabled={deleting} className="text-danger-button">
            {deleting ? "Đang xóa..." : "Xóa phiếu"}
          </button>
        </div>
      </div>

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
            <span className={`status-badge status-${reportTone(report.status)}`}>{reportStatusText(report.status)}</span>
          </div>
        </div>

        {report.out_of_scope_entries.length > 0 && (
          <div className="info-message mt-5" role="status">
            <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
            <p className="mt-1">{report.out_of_scope_entries.map((entry) => entry.raw_indicator_name).join(", ")}</p>
          </div>
        )}

        <div className="mt-6 grid gap-3">
          {report.indicators.map((indicator, index) => {
            const tone = indicator.is_critical ? "critical" : indicator.is_abnormal ? "abnormal" : "normal";
            return (
              <article key={`${indicator.name}-${index}`} className={`result-card result-card-${tone}`}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-950">{indicator.analyte_canonical ?? indicator.name}</h3>
                    {indicator.analyte_raw && indicator.analyte_raw !== indicator.analyte_canonical && (
                      <p className="mt-1 text-xs text-slate-500">Tên gốc: {indicator.analyte_raw}</p>
                    )}
                    <p className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
                      {indicator.value} <span className="text-sm font-medium text-slate-500">{indicator.unit}</span>
                    </p>
                    {(indicator.reference_low !== null || indicator.reference_high !== null) && (
                      <p className="mt-1 text-xs text-slate-500">
                        Tham chiếu: {indicator.reference_low ?? "-"} – {indicator.reference_high ?? "-"}
                      </p>
                    )}
                  </div>
                  <span className={`status-badge status-${tone}`}>{indicatorStatusText(indicator.status)}</span>
                </div>
                {indicator.explanation && <p className="mt-4 text-sm leading-6 text-slate-600">{indicator.explanation}</p>}
                <SourcesDisclosure sources={indicator.sources} />
              </article>
            );
          })}
        </div>

        <div className="disclaimer-box mt-6" role="note" aria-label="Lưu ý y khoa">
          <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
          <p className="mt-1">{report.disclaimer}</p>
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
    </div>
  );
}
