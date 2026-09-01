import { AlertOctagon, ChevronRight } from "lucide-react";
import Link from "next/link";
import { ViewTransition } from "react";
import StatusIndicator from "@/components/common/StatusIndicator";
import type { DoctorQueueTab } from "@/lib/api";
import { motionElementName } from "@/lib/motion";
import { formatDate } from "@/lib/patientUi.mjs";
import type { DoctorQueueItem } from "@/types/doctor";
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

export default function DoctorQueueCard({ item, activeTab }: Props) {
  const criticalFlag = item.flags.find((flag) => flag.code === "CRITICAL_VALUE");
  const supportingFlags = item.flags.filter((flag) => flag.code !== "CRITICAL_VALUE");
  const visibleFlags = supportingFlags.slice(0, 2);
  const hiddenCount = Math.max(0, supportingFlags.length - visibleFlags.length);
  const progress = item.findings_total > 0
    ? Math.round((item.findings_reviewed / item.findings_total) * 100)
    : 0;
  const queueWait = waitText(item.queued_at);
  const isVerified = activeTab === "verified";
  const isCritical = item.severity_level === "critical";
  const statusState = isVerified
    ? "verified"
    : isCritical
      ? "critical"
      : item.severity_level === "abnormal"
        ? "abnormal"
        : item.severity_level === "unknown"
          ? "unknown"
          : "pending";
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
      transitionTypes={["nav-forward"]}
      className="doctor-worklist-card group"
      data-severity={item.severity_level}
      data-queue-state={statusState}
      aria-label={`Mở phiếu của ${item.patient_name}, ${queueState}`}
    >
      <ViewTransition name={motionElementName("doctor-report", item.report_id)} default="none" share="lumilens-shared-detail">
        <div className="doctor-worklist-card__identity">
          <div className="doctor-worklist-card__patient">
            <strong>{item.patient_name}</strong>
            <span>#{item.patient_id}</span>
          </div>
          <div className="doctor-worklist-card__metadata">
            <span>{formatDate(item.test_date)}</span>
            <span aria-hidden="true">·</span>
            <span>{item.findings_total} chỉ số</span>
            {queueWait ? (
              <>
                <span aria-hidden="true">·</span>
                <span>{queueWait}</span>
              </>
            ) : null}
          </div>
        </div>
      </ViewTransition>

      <div className="doctor-worklist-card__reasons">
        <span className="doctor-worklist-card__zone-label">Lý do cần xem</span>
        {criticalFlag ? (
          <span className="doctor-worklist-card__critical-reason">
            <AlertOctagon aria-hidden="true" />
            {criticalFlag.detail}
          </span>
        ) : null}
        {visibleFlags.length > 0 || hiddenCount > 0 ? (
          <div className="doctor-worklist-card__chips">
            {visibleFlags.map((flag, index) => (
              <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
            ))}
            {hiddenCount > 0 ? <span className="doctor-worklist-card__more">+{hiddenCount} lý do</span> : null}
          </div>
        ) : null}
        {!criticalFlag && visibleFlags.length === 0 && hiddenCount === 0 ? (
          <span className="doctor-worklist-card__quiet-reason">Đánh giá theo quy trình lâm sàng</span>
        ) : null}
      </div>

      <div className="doctor-worklist-card__workflow">
        <div className="doctor-worklist-card__state-line">
          <StatusIndicator state={statusState} label={queueState} />
          <span className="doctor-worklist-card__progress-copy">
            {item.findings_reviewed}/{item.findings_total} đã xử lý
          </span>
        </div>
        <div
          className="doctor-worklist-card__progress-track"
          role="progressbar"
          aria-label={`${item.findings_reviewed}/${item.findings_total} luận điểm đã xử lý`}
          aria-valuemin={0}
          aria-valuemax={item.findings_total}
          aria-valuenow={item.findings_reviewed}
        >
          <span style={{ width: `${progress}%` }} />
        </div>
        <span className="doctor-worklist-card__open">
          Mở phiếu <ChevronRight aria-hidden="true" />
        </span>
      </div>
    </Link>
  );
}
