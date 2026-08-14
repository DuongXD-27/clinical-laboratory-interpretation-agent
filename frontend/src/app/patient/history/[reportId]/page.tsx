"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";

type ReportIndicator = {
  name: string;
  value: number;
  unit: string;
  analyte_raw?: string | null;
  analyte_canonical?: string | null;
  raw_value?: number | null;
  raw_unit?: string | null;
  canonical_value?: number | null;
  canonical_unit?: string | null;
  reference_low?: number | null;
  reference_high?: number | null;
  status: string;
  is_abnormal: boolean;
  is_critical: boolean;
  explanation?: string;
  sources?: string[];
};

type ReportDetail = {
  id: number;
  test_date: string;
  status: string;
  result_count: number;
  summary: string;
  disclaimer: string;
  indicators: ReportIndicator[];
  out_of_scope_entries: { id: number; raw_indicator_name: string; created_at: string }[];
};

function sourceHostname(source: string) {
  try {
    return new URL(source).hostname;
  } catch {
    return source;
  }
}

export default function PatientReportDetailPage() {
  const router = useRouter();
  const params = useParams<{ reportId: string }>();
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!getToken() || getRole() !== "patient") {
      router.replace("/");
      return;
    }
    const load = async () => {
      setLoading(true);
      setError(null);
      try {
        const response = await authFetch(`/api/v1/patient/me/lab-reports/${params.reportId}`);
        if (response.status === 401) {
          clearSession();
          router.replace("/");
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

  const deleteReport = async () => {
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
  };

  return (
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div>
            <h1>Chi tiết phiếu xét nghiệm</h1>
            <p>Xem lại dữ liệu đã lưu, không chỉnh sửa kết quả sau khi lưu.</p>
          </div>
          <div className="flex gap-2">
            <Link href="/patient/history" className="secondary-button px-3 py-2.5">Lịch sử</Link>
            {report && (
              <button type="button" onClick={deleteReport} disabled={deleting} className="danger-button px-3 py-2.5">
                {deleting ? "Đang xóa..." : "Xóa"}
              </button>
            )}
          </div>
        </header>

        {loading ? (
          <section className="patient-card p-5 sm:p-7">
            <div className="loading-message" role="status">Đang tải phiếu xét nghiệm...</div>
          </section>
        ) : error ? (
          <section className="patient-card p-5 sm:p-7">
            <div role="alert" className="error-message">{error}</div>
          </section>
        ) : report ? (
          <section className="patient-card p-5 sm:p-7">
            <div className="section-heading">
              <span className="eyebrow">Test Detail</span>
              <h2>{report.test_date}</h2>
              <p>{report.result_count} chỉ số · {report.status}</p>
            </div>

            {report.summary && <div className="summary-box mt-5">{report.summary}</div>}

            {report.out_of_scope_entries.length > 0 && (
              <div className="info-message mt-5">
                <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
                <p className="mt-1">{report.out_of_scope_entries.map((entry) => entry.raw_indicator_name).join(", ")}</p>
              </div>
            )}

            <div className="mt-5 grid gap-3">
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
                            Tham chiếu: {indicator.reference_low ?? "-"} - {indicator.reference_high ?? "-"}
                          </p>
                        )}
                      </div>
                      <span className={`status-badge status-${tone}`}>{indicator.status}</span>
                    </div>
                    {indicator.explanation && <p className="mt-4 text-sm leading-6 text-slate-600">{indicator.explanation}</p>}
                    {indicator.sources && indicator.sources.length > 0 && (
                      <div className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-500">
                        <span className="mr-2">Nguồn tham khảo:</span>
                        {indicator.sources.map((source, sourceIndex) => (
                          <a key={sourceIndex} href={source} target="_blank" rel="noopener noreferrer" className="mr-3 text-blue-700 hover:underline">
                            [{sourceIndex + 1}] {sourceHostname(source)}
                          </a>
                        ))}
                      </div>
                    )}
                  </article>
                );
              })}
            </div>

            <div className="disclaimer-box mt-6">
              <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
              <p className="mt-1">{report.disclaimer}</p>
            </div>
          </section>
        ) : null}
      </div>
    </main>
  );
}
