import type { ReviewFlag } from "@/types/doctor";
import { AlertOctagon, MessageCircleQuestion, ScanSearch } from "lucide-react";
import ClinicalStatusChip, { type ClinicalStatusTone } from "@/components/common/ClinicalStatusChip";

type Props = {
  flag: ReviewFlag;
};

export default function ReasonChip({ flag }: Props) {
  const config: Record<ReviewFlag["code"], { tone: ClinicalStatusTone; icon: typeof AlertOctagon }> = {
    CRITICAL_VALUE: { tone: "critical", icon: AlertOctagon },
    LOW_OCR_CONFIDENCE: { tone: "ocr", icon: ScanSearch },
    PATIENT_HAS_QUESTIONS: { tone: "question", icon: MessageCircleQuestion },
  };
  const { tone, icon } = config[flag.code];

  return (
    <ClinicalStatusChip tone={tone} icon={icon} className="reason-chip">
      {flag.detail}
    </ClinicalStatusChip>
  );
}
