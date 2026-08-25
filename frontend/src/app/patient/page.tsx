"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { authFetch, clearSession, getRole, getToken, getUsername, fetchHistoryDetail } from "@/lib/api";
import type { LabReportDetail } from "@/types/history";

import PatientDashboardEmpty from "@/components/patient/dashboard/PatientDashboardEmpty";
import QuickActions from "@/components/patient/dashboard/QuickActions";
import LatestReportSummary from "@/components/patient/dashboard/LatestReportSummary";
import NeedsAttention from "@/components/patient/dashboard/NeedsAttention";
import RecentReports, { type DashboardReport } from "@/components/patient/dashboard/RecentReports";
import Link from "next/link";

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

  // Detail fetch state
  const [latestDetail, setLatestDetail] = useState<LabReportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState(false);

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
      
      const data: DashboardSummary = await response.json();
      setDashboard(data);

      if (data.recent_reports.length > 0) {
        // Find latest by test_date since order is not guaranteed.
        const latest = [...data.recent_reports].sort((a, b) => 
          new Date(b.test_date).getTime() - new Date(a.test_date).getTime()
        )[0];
        
        setDetailLoading(true);
        setDetailError(false);
        try {
          const detail = await fetchHistoryDetail(latest.report_id);
          setLatestDetail(detail);
        } catch {
          setDetailError(true);
        } finally {
          setDetailLoading(false);
        }
      }

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

  // Derive the latest report for passing to components
  let latestReportId: number | undefined;
  let latestBasicReport: DashboardReport | undefined;
  if (dashboard && dashboard.recent_reports.length > 0) {
    const latest = [...dashboard.recent_reports].sort((a, b) => 
      new Date(b.test_date).getTime() - new Date(a.test_date).getTime()
    )[0];
    latestReportId = latest.report_id;
    latestBasicReport = latest;
  }

  return (
    <div className="space-y-8 pb-12">
      {/* PAGE HEADER */}
      <section className="space-y-1">
        <h1 className="text-2xl font-bold text-foreground">
          Xin chào, {isGuest ? "bạn" : username || "bạn"}
        </h1>
        <p className="text-muted-foreground">
          Theo dõi và xem lại kết quả xét nghiệm của bạn.
        </p>
      </section>

      {/* MAIN CONTENT AREA */}
      {isGuest ? (
        <section className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 shadow-sm">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold text-lg text-foreground">Bạn đang dùng thử với tư cách khách</h3>
              <p className="text-muted-foreground text-sm mt-1 max-w-lg">
                Kết quả phân tích không được lưu sau khi thoát phiên. Bạn vẫn có thể nhập tay hoặc tải ảnh phiếu xét nghiệm để trải nghiệm.
              </p>
            </div>
            <Link href="/patient/analysis" className="shrink-0 inline-flex items-center justify-center h-10 px-6 font-medium text-sm text-[var(--brand-strong)] bg-[var(--brand-soft)] hover:bg-[var(--brand-soft)]/80 rounded-lg transition-colors">
              Bắt đầu phân tích
            </Link>
          </div>
        </section>
      ) : loading ? (
        <div className="space-y-8 animate-pulse motion-reduce:animate-none">
          <div className="h-40 bg-[var(--surface-subtle)] rounded-xl" />
          <div className="h-24 bg-[var(--surface-subtle)] rounded-xl" />
          <div className="h-48 bg-[var(--surface-subtle)] rounded-xl" />
        </div>
      ) : error ? (
        <section className="bg-[var(--status-critical-bg)] border border-[var(--status-critical-fg)]/20 p-6 rounded-xl">
          <div className="flex items-center gap-3 text-[var(--status-critical-fg)] mb-3">
            <span className="font-semibold" role="alert">{error}</span>
          </div>
          <button 
            type="button" 
            onClick={() => void loadDashboard()} 
            className="inline-flex items-center justify-center h-9 px-4 font-medium text-sm bg-white dark:bg-black border border-[var(--border)] rounded-md hover:bg-[var(--surface-subtle)] transition-colors"
          >
            Thử lại
          </button>
        </section>
      ) : dashboard ? (
        <div className="space-y-8">
          
          {dashboard.newly_verified_count > 0 && (
            <div className="bg-[var(--status-success-bg)] text-[var(--status-success-fg)] px-4 py-3 rounded-lg border border-[var(--status-success-fg)]/20 text-sm flex items-center gap-2" role="status">
              Bác sĩ đã kiểm chứng {dashboard.newly_verified_count} phiếu xét nghiệm của bạn.
              <Link href="/patient/history" className="font-semibold hover:underline ml-1">
                Xem lại
              </Link>
            </div>
          )}

          {/* LATEST REPORT SUMMARY & NEEDS ATTENTION */}
          {dashboard.total_reports > 0 ? (
            detailLoading ? (
              <div className="h-40 bg-[var(--surface-subtle)] rounded-xl animate-pulse motion-reduce:animate-none" />
            ) : detailError ? (
              <LatestReportSummary basicReport={latestBasicReport} detailError={true} />
            ) : latestDetail ? (
              <div className="space-y-8">
                <LatestReportSummary report={latestDetail} basicReport={latestBasicReport} />
                <NeedsAttention report={latestDetail} />
              </div>
            ) : null
          ) : (
            <PatientDashboardEmpty />
          )}

          {/* RECENT ACTIVITY */}
          {dashboard.recent_reports.length > 0 && (
            <RecentReports 
              reports={dashboard.recent_reports} 
              excludeReportId={latestReportId} 
            />
          )}

          {/* QUICK ACTIONS */}
          <QuickActions />

        </div>
      ) : null}
    </div>
  );
}
