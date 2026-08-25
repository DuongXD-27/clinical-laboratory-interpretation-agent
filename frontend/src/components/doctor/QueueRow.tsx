import Link from "next/link";
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

import { AlertOctagon, CheckCircle2, ChevronRight } from "lucide-react";

export default function QueueRow({ item, activeTab }: Props) {
  const criticalFlag = item.flags.find((flag) => flag.code === "CRITICAL_VALUE");
  const supportingFlags = item.flags.filter((flag) => flag.code !== "CRITICAL_VALUE");
  const visibleFlags = supportingFlags.slice(0, 2);
  const hiddenCount = Math.max(0, supportingFlags.length - visibleFlags.length);
  const progress = item.findings_total > 0
    ? Math.round((item.findings_reviewed / item.findings_total) * 100)
    : 0;
  const isVerified = activeTab === "verified";
  const isCritical = item.severity_level === "critical";
  const queueState = isVerified
    ? "Đã xác minh"
    : isCritical
      ? "Giá trị khẩn cấp"
      : item.severity_level === "abnormal"
        ? "Bất thường"
        : "Chờ đánh giá";

  return (
    <Link
      href={`/doctor/reports/${item.report_id}?tab=${activeTab}`}
      className="doctor-worklist-row group"
      aria-label={`Mở phiếu của ${item.patient_name}, ${queueState}`}
    >
      <div className="doctor-worklist-row__identity">
        <div className="doctor-worklist-row__patient">
          <strong>{item.patient_name}</strong>
          <span>#{item.patient_id}</span>
        </div>
        <div className="doctor-worklist-row__metadata">
          <span>{formatDate(item.test_date)}</span>
          <span aria-hidden="true">·</span>
          <span>{item.findings_total} chỉ số</span>
          {waitText(item.queued_at) && (
            <>
              <span aria-hidden="true">·</span>
              <span>{waitText(item.queued_at)}</span>
            </>
          )}
        </div>
      </div>

      <div className="doctor-worklist-row__reasons">
        <span className="doctor-worklist-row__zone-label">Lý do cần xem</span>
        {criticalFlag && (
          <span className="doctor-worklist-row__critical-reason">
            <AlertOctagon aria-hidden="true" />
            {criticalFlag.detail}
          </span>
        )}
        {(visibleFlags.length > 0 || hiddenCount > 0) && (
          <div className="doctor-worklist-row__chips">
            {visibleFlags.map((flag, index) => (
              <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
            ))}
            {hiddenCount > 0 && <span className="doctor-worklist-row__more">+{hiddenCount} lý do</span>}
          </div>
        )}
        {!criticalFlag && visibleFlags.length === 0 && hiddenCount === 0 && (
          <span className="doctor-worklist-row__quiet-reason">Đánh giá theo quy trình lâm sàng</span>
        )}
      </div>

      <div className="doctor-worklist-row__workflow">
        <div className="doctor-worklist-row__state-line">
          <span className={`doctor-worklist-state doctor-worklist-state--${isVerified ? "verified" : isCritical ? "critical" : "neutral"}`}>
            {isVerified && <CheckCircle2 aria-hidden="true" />}
            {isCritical && <AlertOctagon aria-hidden="true" />}
            {queueState}
          </span>
          <span className="doctor-worklist-row__progress-copy">
            {item.findings_reviewed}/{item.findings_total} đã xử lý
          </span>
        </div>
        <div
          className="doctor-worklist-row__progress-track"
          role="progressbar"
          aria-label={`${item.findings_reviewed}/${item.findings_total} luận điểm đã xử lý`}
          aria-valuemin={0}
          aria-valuemax={item.findings_total}
          aria-valuenow={item.findings_reviewed}
        >
          <span style={{ width: `${progress}%` }} />
        </div>
        <div className="doctor-worklist-row__open">
          Mở phiếu <ChevronRight aria-hidden="true" />
        </div>
      </div>
    </Link>
  );
}
