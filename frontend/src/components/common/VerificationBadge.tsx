import { Circle, Clock, CheckCircle2 } from "lucide-react";
import type { VerificationStatus } from "@/types/doctor";

type Props = {
  status: VerificationStatus;
};

export default function VerificationBadge({ status }: Props) {
  if (status === "unverified") {
    return (
      <span className="badge-ver badge-ver--unverified">
        <Circle className="w-3.5 h-3.5 text-slate-400" />
        Chưa kiểm chứng
      </span>
    );
  }
  if (status === "pending_review") {
    return (
      <span className="badge-ver badge-ver--pending_review">
        <Clock className="w-3.5 h-3.5 text-indigo-500" />
        Đang chờ bác sĩ xem
      </span>
    );
  }
  return (
    <span className="badge-ver badge-ver--verified">
      <CheckCircle2 className="w-3.5 h-3.5 text-teal-500" />
      Đã xác minh
    </span>
  );
}
