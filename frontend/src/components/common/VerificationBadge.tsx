import StatusIndicator from "@/components/common/StatusIndicator";
import type { VerificationStatus } from "@/types/doctor";

type Props = {
  status: VerificationStatus;
};

export default function VerificationBadge({ status }: Props) {
  if (status === "unverified") {
    return <StatusIndicator state="unverified" />;
  }
  if (status === "pending_review") {
    return <StatusIndicator state="pending-verification" />;
  }
  return <StatusIndicator state="verified" />;
}
