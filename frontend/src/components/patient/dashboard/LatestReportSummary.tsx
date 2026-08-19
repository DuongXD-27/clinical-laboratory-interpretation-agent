import Link from "next/link";
import { ArrowRight, Activity, AlertCircle, AlertTriangle, CheckCircle2 } from "lucide-react";
import { formatDate } from "@/lib/patientUi.mjs";
import type { LabReportDetail } from "@/types/history";
import type { DashboardReport } from "./RecentReports";

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
      
      <div className="bg-[var(--glass-surface)] backdrop-blur-md border border-[var(--glass-border)] rounded-2xl p-5 sm:p-6 shadow-sm overflow-hidden relative">
        {/* Decorative background accent */}
        <div className="absolute top-0 right-0 w-64 h-64 bg-[var(--brand)]/5 rounded-full blur-3xl -translate-y-1/2 translate-x-1/3 pointer-events-none" aria-hidden="true" />
        
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
                  <div className="flex items-center justify-between text-[var(--status-critical-fg)] font-medium">
                    <div className="flex items-center gap-2">
                      <AlertCircle className="w-4 h-4" />
                      <span>Cần chú ý khẩn cấp</span>
                    </div>
                    <span>{criticalCount}</span>
                  </div>
                )}
                {attentionCount > 0 && (
                  <div className="flex items-center justify-between text-[var(--status-warning-fg)] font-medium">
                    <div className="flex items-center gap-2">
                      <AlertTriangle className="w-4 h-4" />
                      <span>Cần lưu ý</span>
                    </div>
                    <span>{attentionCount}</span>
                  </div>
                )}
                {normalCount > 0 && (
                  <div className="flex items-center justify-between text-[var(--status-success-fg)] font-medium">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Trong khoảng</span>
                    </div>
                    <span>{normalCount}</span>
                  </div>
                )}
              </>
            )}
          </div>
          
          <div className="pt-4 sm:pt-0 sm:ml-auto">
            <Link 
              href={`/patient/reports/${reportId}`}
              className="inline-flex items-center justify-center gap-2 h-10 px-6 font-medium text-sm text-[var(--brand-strong)] bg-[var(--brand-soft)] hover:bg-[var(--brand-soft)]/80 rounded-lg transition-colors w-full sm:w-auto"
            >
              Xem kết quả
              <ArrowRight className="w-4 h-4" aria-hidden="true" />
            </Link>
          </div>
          
        </div>
      </div>
    </section>
  );
}
