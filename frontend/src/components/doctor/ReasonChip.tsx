import type { ReviewFlag } from "@/types/doctor";
import StatusIndicator, { type StatusLevel, type StatusState } from "@/components/common/StatusIndicator";

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

  return <StatusIndicator state={config[flag.code]} label={flag.detail} level={level} className="reason-chip" />;
}
