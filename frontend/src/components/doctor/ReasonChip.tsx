import type { ReviewFlag } from "@/types/doctor";
import StatusIndicator, { type StatusLevel, type StatusState } from "@/components/common/StatusIndicator";
import { formatClinicalText } from "@/lib/clinicalUnit.mjs";

type Props = {
  flag: ReviewFlag;
  level?: StatusLevel;
};

export default function ReasonChip({ flag, level }: Props) {
  const config: Record<ReviewFlag["code"], StatusState> = {
    CRITICAL_VALUE: "critical",
    LOW_OCR_CONFIDENCE: "ocr-review",
    PATIENT_HAS_QUESTIONS: "question",
  };

  return <StatusIndicator state={config[flag.code]} label={formatClinicalText(flag.detail)} level={level} className="reason-chip" />;
}
