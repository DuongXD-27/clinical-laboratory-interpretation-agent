import { CheckCircle2, AlertTriangle, AlertOctagon, HelpCircle } from "lucide-react";
import ClinicalStatusChip, { type ClinicalStatusTone } from "@/components/common/ClinicalStatusChip";
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
  const icons = {
    normal: CheckCircle2,
    abnormal: AlertTriangle,
    critical: AlertOctagon,
    unknown: HelpCircle,
  };
  const tones: Record<SeverityLevel, ClinicalStatusTone> = {
    normal: "normal",
    abnormal: "abnormal",
    critical: "critical",
    unknown: "neutral",
  };

  return <ClinicalStatusChip tone={tones[level]} icon={icons[level]}>{LABELS[level]}</ClinicalStatusChip>;
}
