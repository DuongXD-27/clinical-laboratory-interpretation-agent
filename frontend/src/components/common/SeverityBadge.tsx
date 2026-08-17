import type { SeverityLevel } from "@/types/doctor";

type Props = {
  level: SeverityLevel;
};

const LABELS: Record<SeverityLevel, string> = {
  critical: "Nguy kịch",
  abnormal: "Bất thường",
  normal: "Bình thường",
};

export default function SeverityBadge({ level }: Props) {
  return (
    <span className={`badge-sev badge-sev--${level}`}>
      {LABELS[level]}
    </span>
  );
}
