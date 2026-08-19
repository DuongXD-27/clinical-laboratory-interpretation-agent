import Link from "next/link";
import { ArrowRight, FileText } from "lucide-react";
import { formatDate, formatMoment, reportTone } from "@/lib/patientUi.mjs";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";

// We extract the type inline or import it if exported.
// Since DashboardReport is defined in page.tsx, we'll redefine its shape here to keep components isolated.
export interface DashboardReport {
  report_id: number;
  test_date: string;
  result_count: number;
  status: string;
  created_at: string;
  verification_status: "unverified" | "pending_review" | "verified";
  verified_at: string | null;
}

interface RecentReportsProps {
  reports: DashboardReport[];
  excludeReportId?: number;
}

export default function RecentReports({ reports, excludeReportId }: RecentReportsProps) {
  const displayReports = reports
    .filter((report) => report.report_id !== excludeReportId)
    .slice(0, 3);

  if (displayReports.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="recent-activity-title" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 id="recent-activity-title" className="text-lg font-semibold text-foreground">
          Hoạt động gần đây
        </h2>
        <Link 
          href="/patient/history" 
          className="text-sm font-medium text-[var(--brand)] hover:underline"
        >
          Xem tất cả
        </Link>
      </div>

      <div className="space-y-3">
        {displayReports.map((report) => (
          <Link
            key={report.report_id}
            href={`/patient/reports/${report.report_id}`}
            className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-xl hover:border-[var(--brand-soft)] hover:shadow-sm transition-all group"
            aria-label={`Xem phiếu ngày ${formatDate(report.test_date)}`}
          >
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-[var(--surface-subtle)] flex items-center justify-center shrink-0 text-muted-foreground group-hover:text-[var(--brand)] group-hover:bg-[var(--brand-soft)] transition-colors" aria-hidden="true">
                <FileText className="w-5 h-5" />
              </div>
              <div className="flex flex-col">
                <span className="font-semibold text-foreground">Phiếu xét nghiệm • {formatDate(report.test_date)}</span>
                <span className="text-sm text-muted-foreground">
                  {report.result_count} chỉ số · Tạo {formatMoment(report.created_at)}
                </span>
              </div>
            </div>
            
            <div className="flex items-center gap-2 pl-13 sm:pl-0">
              <SeverityBadge level={reportTone(report.status)} />
              <VerificationBadge status={report.verification_status} />
              <ArrowRight className="w-4 h-4 text-muted-foreground ml-2 hidden sm:block opacity-0 group-hover:opacity-100 transition-opacity" aria-hidden="true" />
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
