import type { VerificationStatus } from "@/types/doctor";

type Props = {
  status: VerificationStatus;
};

const META: Record<VerificationStatus, { label: string; icon: string }> = {
  unverified: { label: "Chưa kiểm chứng", icon: "○" },
  pending_review: { label: "Đang chờ bác sĩ xem", icon: "◷" },
  verified: { label: "Đã bác sĩ kiểm chứng", icon: "✓" },
};

export default function VerificationBadge({ status }: Props) {
  const meta = META[status] ?? META.unverified;
  return (
    <span className={`badge-ver badge-ver--${status}`}>
      <span aria-hidden="true">{meta.icon}</span>
      {meta.label}
    </span>
  );
}
