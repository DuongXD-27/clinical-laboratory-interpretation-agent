import Link from "next/link";
import { ViewTransition } from "react";
import { ArrowRight, Activity, AlertTriangle } from "lucide-react";
import { formatDate } from "@/lib/patientUi.mjs";
import type { LabReportDetail } from "@/types/history";
import type { DashboardReport } from "./RecentReports";
import StatusIndicator from "@/components/common/StatusIndicator";
import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { motionElementName } from "@/lib/motion";

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
    <section aria-labelledby="latest-summary-title" className="dashboard-section">
      <h2 id="latest-summary-title" className="text-lg font-semibold text-foreground">
        Kết quả gần nhất
      </h2>
      <div className="dashboard-latest-card">
        <div className="dashboard-latest-card__layout">
          <ViewTransition name={motionElementName("patient-report", reportId)} default="none" share="lumilens-shared-detail">
          <div className="space-y-1">
            <div className="flex items-center gap-2 text-muted-foreground mb-2">
              <Activity className="size-4" aria-hidden="true" />
              <span className="text-sm font-medium">Phiếu xét nghiệm • {formatDate(testDate)}</span>
            </div>
            <div className="dashboard-latest-card__value">
              {resultCount} <span className="text-xl font-normal text-muted-foreground">chỉ số</span>
            </div>
          </div>
          </ViewTransition>
          
          <div className="flex flex-col gap-3 sm:border-l sm:border-[var(--border)] sm:pl-6 min-w-[200px]">
            {detailError ? (
              <div className="flex items-center gap-2 text-muted-foreground text-sm font-medium">
                <AlertTriangle className="size-4" aria-hidden="true" />
                <span>Không thể tải chi tiết chỉ số.</span>
              </div>
            ) : (
              <>
                {criticalCount > 0 && (
                  <div className="latest-report-status-cluster">
                    <StatusIndicator state="critical" label={`${criticalCount} cần chú ý khẩn cấp`} level="inline" />
                  </div>
                )}
                {attentionCount > 0 && (
                  <div className="latest-report-status-cluster">
                    <StatusIndicator state="abnormal" label={`${attentionCount} cần lưu ý`} level="inline" />
                  </div>
                )}
                {normalCount > 0 && (
                  <div className="latest-report-status-cluster">
                    <StatusIndicator state="normal" label={`${normalCount} trong khoảng`} />
                  </div>
                )}
              </>
            )}
          </div>
          
          <div className="pt-4 sm:pt-0 sm:ml-auto">
            <Link 
              href={`/patient/reports/${reportId}`}
              transitionTypes={["nav-forward"]}
              className={cn(buttonVariants({ variant: "secondary" }), "w-full sm:w-auto")}
            >
              Xem kết quả
              <ArrowRight data-icon="inline-end" aria-hidden="true" />
            </Link>
          </div>
          
        </div>
      </div>
    </section>
  );
}
