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
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import StatusIndicator from "@/components/common/StatusIndicator";
import { PATIENT_ROUTES } from "@/lib/patientRoutes.mjs";
import { SystemState } from "@/components/common/SystemState";
import { Button, buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";

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
    <div className="patient-page-layout">
      <PatientPageHeader
        eyebrow="Tổng quan sức khỏe"
        title={<>Xin chào, {isGuest ? "bạn" : username || "bạn"}</>}
        description="Theo dõi và xem lại kết quả xét nghiệm của bạn."
      />

      {/* MAIN CONTENT AREA */}
      {isGuest ? (
        <section className="dashboard-guest-card">
          <div className="flex flex-col md:flex-row items-center justify-between gap-4">
            <div>
              <h3 className="font-semibold text-lg text-foreground">Bạn đang dùng thử với tư cách khách</h3>
              <p className="text-muted-foreground text-sm mt-1 max-w-lg">
                Kết quả phân tích không được lưu sau khi thoát phiên. Bạn vẫn có thể nhập tay hoặc tải ảnh phiếu xét nghiệm để trải nghiệm.
              </p>
            </div>
            <Link href={PATIENT_ROUTES.ANALYSIS} transitionTypes={["nav-route"]} className={buttonVariants({ variant: "secondary" })}>
              Bắt đầu phân tích
            </Link>
          </div>
        </section>
      ) : loading ? (
        <div className="dashboard-skeleton" role="status" aria-label="Đang tải tổng quan">
          <Skeleton className="h-40 rounded-[var(--radius-glass)]" />
          <Skeleton className="h-24 rounded-[var(--radius-glass)]" />
          <Skeleton className="h-48 rounded-[var(--radius-glass)]" />
        </div>
      ) : error ? (
        <SystemState
          kind="error"
          title="Chưa tải được tổng quan"
          description={error}
          className="dashboard-state"
          action={<Button type="button" variant="outline" onClick={() => void loadDashboard()}>Thử lại</Button>}
        />
      ) : dashboard ? (
        <div className="dashboard-stack">
          
          {dashboard.newly_verified_count > 0 && (
            <div className="dashboard-verified-notice" role="status">
              <StatusIndicator state="verified" label="Đã kiểm chứng" />
              <span>Bác sĩ đã kiểm chứng {dashboard.newly_verified_count} phiếu xét nghiệm của bạn.</span>
              <Link href={PATIENT_ROUTES.HISTORY} transitionTypes={["nav-route"]} className="font-semibold hover:underline ml-1">
                Xem lại
              </Link>
            </div>
          )}

          {/* LATEST REPORT SUMMARY & NEEDS ATTENTION */}
          {dashboard.total_reports > 0 ? (
            detailLoading ? (
              <Skeleton className="h-40 rounded-[var(--radius-glass)]" />
            ) : detailError ? (
              <LatestReportSummary basicReport={latestBasicReport} detailError={true} />
            ) : latestDetail ? (
              <div className="dashboard-stack">
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
