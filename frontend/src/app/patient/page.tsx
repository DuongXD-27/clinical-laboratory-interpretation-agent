"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";
import { authFetch, clearSession, getRole, getToken, getUsername } from "@/lib/api";
import { formatDate, formatMoment, reportStatusText, reportTone } from "@/lib/patientUi.mjs";

type DashboardReport = {
  report_id: number;
  test_date: string;
  result_count: number;
  status: string;
  created_at: string;
  verification_status: "unverified" | "pending_review" | "verified";
  verified_at: string | null;
};

type DashboardSummary = {
  total_reports: number;
  latest_test_date?: string | null;
  recent_reports: DashboardReport[];
  newly_verified_count: number;
};

export default function PatientDashboardPage() {
  const router = useRouter();
  const [username, setUsername] = useState<string | null>(null);
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isGuest, setIsGuest] = useState(false);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await authFetch("/api/v1/patient/me/dashboard");
      if (response.status === 401) {
        clearSession();
        router.replace("/login");
        return;
      }
      if (!response.ok) throw new Error("Chưa tải được tổng quan kết quả xét nghiệm.");
      setDashboard(await response.json());
    } catch (caught: unknown) {
      setError(caught instanceof Error ? caught.message : "Chưa tải được tổng quan kết quả xét nghiệm.");
    } finally {
      setLoading(false);
    }
  }, [router]);

  useEffect(() => {
    const role = getRole();
    if (!getToken() || (role !== "patient" && role !== "guest")) {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage session values are client-only.
    setUsername(getUsername());
    setIsGuest(role === "guest");
    if (role === "guest") {
      setLoading(false);
      return;
    }
    void loadDashboard();
  }, [loadDashboard, router]);

  const latestReport = dashboard?.recent_reports[0] ?? null;

  return (
    <div className="dashboard-layout">
      <section className="dashboard-welcome">
        <div>
          <span className="eyebrow">Tổng quan sức khỏe</span>
          <h2>Xin chào, {isGuest ? "bạn" : username || "bạn"}</h2>
          <p>Tổng quan kết quả xét nghiệm của bạn</p>
        </div>
        <Link href="/patient/analysis" className="primary-button dashboard-primary-cta">
          <span aria-hidden="true">+</span> Phân tích kết quả mới
        </Link>
      </section>

      {isGuest ? (
        <section className="patient-card p-5 sm:p-7">
          <div className="guest-dashboard-state">
            <div className="guest-dashboard-icon" aria-hidden="true">+</div>
            <div>
              <h3>Bạn đang dùng thử với tư cách khách</h3>
              <p>Kết quả phân tích không được lưu sau khi thoát phiên. Bạn vẫn có thể nhập tay hoặc tải ảnh phiếu xét nghiệm để trải nghiệm.</p>
            </div>
            <Link href="/patient/analysis" className="secondary-button">Bắt đầu phân tích</Link>
          </div>
        </section>
      ) : loading ? (
        <section className="patient-card p-5 sm:p-7">
          <div className="loading-message" role="status">Đang tải tổng quan...</div>
        </section>
      ) : error ? (
        <section className="patient-card p-5 sm:p-7">
          <div className="error-message" role="alert">{error}</div>
          <button type="button" onClick={() => void loadDashboard()} className="secondary-button mt-4">Thử lại</button>
        </section>
      ) : dashboard ? (
        <>
          {dashboard.newly_verified_count > 0 && (
            <section className="patient-card p-4 sm:p-5">
              <div className="info-message" role="status">
                Bác sĩ đã kiểm chứng {dashboard.newly_verified_count} phiếu xét nghiệm của bạn.
                <Link href="/patient/history" className="ml-2 text-blue-700 hover:underline">
                  Xem lại
                </Link>
              </div>
            </section>
          )}

          <section className="dashboard-summary-grid" aria-label="Tóm tắt kết quả xét nghiệm">
            <article className="dashboard-summary-card">
              <span className="dashboard-summary-icon" aria-hidden="true">▤</span>
              <div><p>Tổng số lần xét nghiệm</p><strong>{dashboard.total_reports}</strong></div>
            </article>
            <article className="dashboard-summary-card">
              <span className="dashboard-summary-icon" aria-hidden="true">◷</span>
              <div><p>Lần gần nhất</p><strong>{formatDate(dashboard.latest_test_date)}</strong></div>
            </article>
            <article className="dashboard-summary-card">
              <span className="dashboard-summary-icon" aria-hidden="true">✓</span>
              <div><p>Tình trạng phiếu gần nhất</p><strong className="dashboard-status-text">{latestReport ? reportStatusText(latestReport.status) : "Chưa có dữ liệu"}</strong></div>
            </article>
          </section>

          <section className="patient-card p-5 sm:p-7" aria-labelledby="latest-report-title">
            <div className="page-section-heading compact">
              <div>
                <span className="eyebrow">Phiếu gần nhất</span>
                <h2 id="latest-report-title">Kết quả mới nhất</h2>
              </div>
            </div>
            {latestReport ? (
              <article className={`recent-report-feature result-card-${reportTone(latestReport.status)}`}>
                <div className="recent-report-date">
                  <span>Ngày xét nghiệm</span>
                  <strong>{formatDate(latestReport.test_date)}</strong>
                </div>
                <div className="recent-report-meta">
                  <div><strong>{latestReport.result_count}</strong><span>chỉ số</span></div>
                  <div><strong>{formatMoment(latestReport.created_at)}</strong><span>thời gian tạo</span></div>
                </div>
                <SeverityBadge level={reportTone(latestReport.status)} />
                <VerificationBadge status={latestReport.verification_status} />
                <Link href={`/patient/reports/${latestReport.report_id}`} className="secondary-button">Xem chi tiết</Link>
              </article>
            ) : (
              <div className="compact-empty-state">
                <p>Bạn chưa có kết quả xét nghiệm nào.</p>
                <Link href="/patient/analysis" className="text-button">Phân tích kết quả đầu tiên →</Link>
              </div>
            )}
          </section>

          <section className="patient-card p-5 sm:p-7" aria-labelledby="recent-history-title">
            <div className="page-section-heading compact">
              <div>
                <span className="eyebrow">Lịch sử gần đây</span>
                <h2 id="recent-history-title">Các phiếu gần nhất</h2>
              </div>
              <Link href="/patient/history" className="text-button">Xem toàn bộ lịch sử →</Link>
            </div>
            {dashboard.recent_reports.length > 0 ? (
              <div className="dashboard-recent-list">
                {dashboard.recent_reports.slice(0, 3).map((report) => (
                  <article key={report.report_id}>
                    <div>
                      <strong>{formatDate(report.test_date)}</strong>
                      <span>{report.result_count} chỉ số · tạo {formatMoment(report.created_at)}</span>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      <SeverityBadge level={reportTone(report.status)} />
                      <VerificationBadge status={report.verification_status} />
                    </div>
                    <Link href={`/patient/reports/${report.report_id}`} aria-label={`Xem phiếu ngày ${formatDate(report.test_date)}`}>Xem chi tiết</Link>
                  </article>
                ))}
              </div>
            ) : (
              <div className="compact-empty-state">Chưa có phiếu xét nghiệm đã lưu.</div>
            )}
          </section>
        </>
      ) : null}
    </div>
  );
}
