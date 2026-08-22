import Link from "next/link";
import SeverityBadge from "@/components/common/SeverityBadge";
import { formatDate } from "@/lib/patientUi.mjs";
import type { DoctorQueueItem } from "@/types/doctor";
import type { DoctorQueueTab } from "@/lib/api";
import ReasonChip from "./ReasonChip";

type Props = {
  item: DoctorQueueItem;
  activeTab: DoctorQueueTab;
};

function waitText(value: string | null) {
  if (!value) return "";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return "";
  const hours = Math.max(0, Math.floor((Date.now() - parsed.getTime()) / 36e5));
  if (hours < 1) return "mới vào hàng đợi";
  if (hours < 24) return `chờ ${hours} giờ`;
  return `chờ ${Math.floor(hours / 24)} ngày`;
}

import { ChevronRight } from "lucide-react";

export default function QueueRow({ item, activeTab }: Props) {
  const visibleFlags = item.flags.slice(0, 3);
  const hiddenCount = Math.max(0, item.flags.length - visibleFlags.length);

  return (
    <Link
      href={`/doctor/reports/${item.report_id}?tab=${activeTab}`}
      className="group flex flex-col md:flex-row md:items-center justify-between gap-4 p-4 bg-[var(--surface)] border border-[var(--border)] rounded-2xl shadow-sm hover:shadow-md hover:border-[var(--brand-soft)] transition-all duration-200 motion-reduce:transition-none hover:-translate-y-0.5 motion-reduce:hover:translate-y-0 outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2"
    >
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2">
          <strong className="text-base font-semibold text-foreground">{item.patient_name}</strong>
          <span className="text-sm text-muted-foreground">· #{item.patient_id}</span>
        </div>
        <div className="text-sm text-muted-foreground">
          {formatDate(item.test_date)} <span className="mx-1">·</span> {item.findings_total} chỉ số
        </div>
        {(visibleFlags.length > 0 || hiddenCount > 0) && (
          <div className="flex flex-wrap items-center gap-2 mt-1">
            {visibleFlags.map((flag, index) => (
              <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
            ))}
            {hiddenCount > 0 && <span className="inline-flex items-center justify-center px-2 py-0.5 rounded-full bg-[var(--surface-subtle)] text-[var(--foreground-secondary)] text-xs font-medium">+{hiddenCount}</span>}
          </div>
        )}
      </div>

      <div className="flex flex-col md:items-end gap-2 shrink-0 border-t border-[var(--border)] md:border-t-0 pt-3 md:pt-0 mt-2 md:mt-0">
        <div className="flex items-center gap-3 w-full md:w-auto justify-between md:justify-end">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">{item.findings_reviewed}/{item.findings_total} l.điểm</span>
            {waitText(item.queued_at) && (
              <span className="text-xs text-muted-foreground bg-[var(--surface-subtle)] px-2 py-0.5 rounded-full">{waitText(item.queued_at)}</span>
            )}
          </div>
          {item.severity_level && item.severity_level !== "unknown" && (
            <SeverityBadge level={item.severity_level} />
          )}
        </div>
        <div className="hidden md:flex items-center text-sm font-medium text-[var(--brand)] opacity-0 group-hover:opacity-100 transition-opacity">
          Xem báo cáo <ChevronRight className="w-4 h-4 ml-1" />
        </div>
      </div>
    </Link>
  );
}
