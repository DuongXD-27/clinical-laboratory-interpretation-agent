import Link from "next/link";
import { ArrowRight, Activity, AlertTriangle } from "lucide-react";
import { formatDate } from "@/lib/patientUi.mjs";
import type { LabReportDetail } from "@/types/history";
import type { DashboardReport } from "./RecentReports";
import StatusIndicator from "@/components/common/StatusIndicator";

interface LatestReportSummaryProps {
  report?: LabReportDetail;
  basicReport?: DashboardReport;
  detailError?: boolean;
}

export default function LatestReportSummary({ report, basicReport, detailError }: LatestReportSummaryProps) {
  let normalCount = 0;
  let attentionCount = 0;
  let criticalCount = 0;

  if (report) {
    for (const indicator of report.indicators) {
      if (indicator.is_critical) {
        criticalCount++;
      } else if (indicator.status === "high" || indicator.status === "low") {
        attentionCount++;
      } else if (indicator.status === "normal") {
        normalCount++;
      }
    }
  }

  const testDate = report ? report.test_date : basicReport?.test_date;
  const resultCount = report ? report.indicators.length : basicReport?.result_count;
  const reportId = report ? report.id : basicReport?.report_id;

  if (!testDate || !reportId) return null;

  return (
    <section aria-labelledby="latest-summary-title" className="space-y-4">
      <h2 id="latest-summary-title" className="text-lg font-semibold text-foreground">
        Kết quả gần nhất
      </h2>
      <div className="relative group">
        <div className="absolute inset-[-12px] rounded-[32px] bg-gradient-to-r from-[var(--holo-cyan)]/30 via-[var(--holo-blue)]/15 to-[var(--holo-violet)]/10 blur-xl opacity-70 pointer-events-none" aria-hidden="true" />
        
        <div className="bg-[var(--glass-surface)] backdrop-blur-xl border border-white/20 rounded-[24px] p-6 shadow-[0_16px_48px_rgba(0,0,0,0.06),inset_0_1px_1px_rgba(255,255,255,0.9),inset_1px_1px_1px_rgba(71,214,211,0.2),inset_-1px_-1px_1px_rgba(96,165,250,0.15)] overflow-hidden relative">
          {/* Decorative background accent inside card */}
          <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--holo-cyan)]/10 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3 pointer-events-none" aria-hidden="true" />
          
          <div className="relative z-10 flex flex-col sm:flex-row sm:items-center justify-between gap-6">
          
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Activity className="w-4 h-4" />
              <span className="text-sm font-medium">Phiếu xét nghiệm • {formatDate(testDate)}</span>
            </div>
            <div className="text-3xl font-bold text-foreground">
              {resultCount} <span className="text-xl font-normal text-muted-foreground">chỉ số</span>
            </div>
          </div>
          
          <div className="flex flex-col gap-3 sm:border-l sm:border-[var(--border)] sm:pl-6 min-w-[200px]">
            {detailError ? (
              <div className="flex items-center gap-2 text-muted-foreground text-sm font-medium">
                <AlertTriangle className="w-4 h-4" />
                <span>Không thể tải chi tiết chỉ số.</span>
              </div>
            ) : (
              <>
                {criticalCount > 0 && (
                  <div className="flex items-center justify-between gap-4">
                    <StatusIndicator state="critical" label="Cần chú ý khẩn cấp" level="inline" />
                    <span>{criticalCount}</span>
                  </div>
                )}
                {attentionCount > 0 && (
                  <div className="flex items-center justify-between gap-4">
                    <StatusIndicator state="abnormal" label="Cần lưu ý" level="inline" />
                    <span>{attentionCount}</span>
                  </div>
                )}
                {normalCount > 0 && (
                  <div className="flex items-center justify-between gap-4">
                    <StatusIndicator state="normal" label="Trong khoảng" />
                    <span>{normalCount}</span>
                  </div>
                )}
              </>
            )}
          </div>
          
          <div className="pt-4 sm:pt-0 sm:ml-auto">
            <Link 
              href={`/patient/reports/${reportId}`}
              className="inline-flex items-center justify-center gap-2 h-10 px-6 font-medium text-sm text-[var(--brand-strong)] bg-[var(--brand-soft)] hover:bg-[var(--surface)] border border-transparent hover:border-[var(--brand)]/20 rounded-xl transition-all duration-200 motion-reduce:transition-none hover:-translate-y-0.5 shadow-sm hover:shadow-[0_4px_12px_rgba(0,0,0,0.05),inset_0_1px_1px_rgba(255,255,255,1)] w-full sm:w-auto"
            >
              Xem kết quả
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
          </div>
          
        </div>
        </div>
      </div>
    </section>
  );
}
