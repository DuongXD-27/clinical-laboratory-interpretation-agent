import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import type { SeverityLevel } from "@/types/doctor";

type Props = {
  level: SeverityLevel;
};

export default function SeverityBadge({ level }: Props) {
  return <StatusIndicator state={level as StatusState} />;
}
