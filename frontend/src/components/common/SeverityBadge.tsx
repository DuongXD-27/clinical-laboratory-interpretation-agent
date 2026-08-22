import { CheckCircle2, AlertTriangle, AlertOctagon, HelpCircle } from "lucide-react";
import type { SeverityLevel } from "@/types/doctor";

type Props = {
  level: SeverityLevel;
};

const LABELS: Record<SeverityLevel, string> = {
  critical: "Giá trị khẩn cấp",
  abnormal: "Bất thường",
  normal: "Bình thường",
  unknown: "Chưa phân loại",
};

export default function SeverityBadge({ level }: Props) {
  return (
    <span className={`badge-sev badge-sev--${level}`}>
      {level === "normal" && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />}
      {level === "abnormal" && <AlertTriangle className="w-3.5 h-3.5 text-amber-500" />}
      {level === "critical" && <AlertOctagon className="w-3.5 h-3.5 text-red-500" />}
      {level === "unknown" && <HelpCircle className="w-3.5 h-3.5 text-slate-400" />}
      {LABELS[level]}
    </span>
  );
}
