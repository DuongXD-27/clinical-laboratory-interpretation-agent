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

import { ArrowRight, Clock3, ListChecks } from "lucide-react";

export default function QueueRow({ item, activeTab }: Props) {
  const visibleFlags = item.flags.slice(0, 3);
  const hiddenCount = Math.max(0, item.flags.length - visibleFlags.length);
  const progress = item.findings_total > 0
    ? Math.round((item.findings_reviewed / item.findings_total) * 100)
    : 0;

  return (
    <Link
      href={`/doctor/reports/${item.report_id}?tab=${activeTab}`}
      className="doctor-queue-card"
    >
      <div className="doctor-queue-card__main">
        <div className="doctor-queue-card__identity">
          <strong>{item.patient_name}</strong>
          <span>Hồ sơ #{item.patient_id}</span>
        </div>
        <div className="doctor-queue-card__meta">
          <span>{formatDate(item.test_date)}</span>
          <span><ListChecks aria-hidden="true" /> {item.findings_total} chỉ số</span>
          {waitText(item.queued_at) && <span><Clock3 aria-hidden="true" /> {waitText(item.queued_at)}</span>}
        </div>
        {(visibleFlags.length > 0 || hiddenCount > 0) && (
          <div className="doctor-queue-card__reasons">
            {visibleFlags.map((flag, index) => (
              <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
            ))}
            {hiddenCount > 0 && <span className="doctor-queue-card__more">+{hiddenCount}</span>}
          </div>
        )}
      </div>

      <div className="doctor-queue-card__status">
        <div className="doctor-queue-card__status-line">
          {item.severity_level && item.severity_level !== "unknown" && (
            <SeverityBadge level={item.severity_level} />
          )}
          <span className="doctor-queue-card__review-count">{item.findings_reviewed}/{item.findings_total} đã xử lý</span>
        </div>
        <div className="doctor-queue-card__progress" aria-hidden="true">
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="doctor-queue-card__action">
          Mở phiếu <ArrowRight aria-hidden="true" />
        </div>
      </div>
    </Link>
  );
}
