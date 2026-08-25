import { Circle, Clock, CheckCircle2 } from "lucide-react";
import ClinicalStatusChip from "@/components/common/ClinicalStatusChip";
import type { VerificationStatus } from "@/types/doctor";

type Props = {
  status: VerificationStatus;
};

export default function VerificationBadge({ status }: Props) {
  if (status === "unverified") {
    return (
      <ClinicalStatusChip tone="neutral" icon={Circle}>
        Chưa kiểm chứng
      </ClinicalStatusChip>
    );
  }
  if (status === "pending_review") {
    return (
      <ClinicalStatusChip tone="pending" icon={Clock}>
        Đang chờ bác sĩ xem
      </ClinicalStatusChip>
    );
  }
  return (
    <ClinicalStatusChip tone="verified" icon={CheckCircle2}>
      Đã xác minh
    </ClinicalStatusChip>
  );
}
