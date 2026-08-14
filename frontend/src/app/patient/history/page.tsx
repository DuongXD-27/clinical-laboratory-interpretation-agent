"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken } from "@/lib/api";

type ReportSummary = {
  report_id: number;
  test_date: string;
  result_count: number;
  status: string;
  created_at: string;
};

function statusText(status: string) {
  if (status === "CRITICAL") return "Có chỉ số nguy kịch";
  if (status === "ABNORMAL") return "Có chỉ số bất thường";
  return "Bình thường";
}

export default function PatientHistoryPage() {
  const router = useRouter();
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
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
        const response = await authFetch("/api/v1/patient/me/lab-reports");
        if (response.status === 401) {
          clearSession();
          router.replace("/");
          return;
        }
        if (!response.ok) throw new Error("Chưa tải được lịch sử xét nghiệm.");
        const data = await response.json();
        setReports(Array.isArray(data.reports) ? data.reports : []);
      } catch (caught: unknown) {
        setError(caught instanceof Error ? caught.message : "Chưa tải được lịch sử xét nghiệm.");
      } finally {
        setLoading(false);
      }
    };
    void load();
  }, [router]);

  return (
    <main className="patient-shell">
      <div className="patient-container">
        <header className="patient-header">
          <div>
            <h1>Laboratory History</h1>
            <p>Danh sách các phiếu xét nghiệm đã xác nhận và lưu thành công.</p>
          </div>
          <Link href="/patient" className="secondary-button px-3 py-2.5">Dashboard</Link>
        </header>

        <section className="patient-card p-5 sm:p-7">
          {loading ? (
            <div className="loading-message" role="status">Đang tải lịch sử...</div>
          ) : error ? (
            <div role="alert" className="error-message">{error}</div>
          ) : reports.length === 0 ? (
            <div className="empty-metrics">
              <p className="font-medium text-slate-700">Bạn chưa có kết quả xét nghiệm nào được lưu.</p>
              <Link href="/patient" className="text-button mt-2">Phân tích phiếu đầu tiên</Link>
            </div>
          ) : (
            <div className="grid gap-3">
              {reports.map((report) => (
                <Link key={report.report_id} href={`/patient/history/${report.report_id}`} className="result-card">
                  <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                    <div>
                      <h2 className="font-semibold text-slate-950">{report.test_date}</h2>
                      <p className="mt-1 text-sm text-slate-500">{report.result_count} chỉ số</p>
                    </div>
                    <span className="status-badge status-normal">{statusText(report.status)}</span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
