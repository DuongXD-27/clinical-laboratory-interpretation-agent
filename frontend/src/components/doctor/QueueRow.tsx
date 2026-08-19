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

export default function QueueRow({ item, activeTab }: Props) {
  const visibleFlags = item.flags.slice(0, 3);
  const hiddenCount = Math.max(0, item.flags.length - visibleFlags.length);

  return (
    <Link
      href={`/doctor/reports/${item.report_id}?tab=${activeTab}`}
      className={`queue-row queue-row--${item.severity_level}`}
    >
      <div className="queue-row__main">
        <div>
          <strong>{item.patient_name}</strong>
          <span> · #{item.patient_id}</span>
        </div>
        <p>{formatDate(item.test_date)} · {item.findings_total} chỉ số</p>
        <div className="queue-row__chips">
          {visibleFlags.map((flag, index) => (
            <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
          ))}
          {hiddenCount > 0 && <span className="chip-reason">+{hiddenCount}</span>}
        </div>
      </div>
      <div className="queue-row__meta">
        <SeverityBadge level={item.severity_level} />
        <span>{item.findings_reviewed}/{item.findings_total} luận điểm</span>
        <span>{waitText(item.queued_at)}</span>
      </div>
      <span className="queue-row__chevron" aria-hidden="true">›</span>
    </Link>
  );
}
