import type { ReviewFlag } from "@/types/doctor";
import { AlertOctagon, FileSearch, MessageCircle } from "lucide-react";

type Props = {
  flag: ReviewFlag;
};

export default function ReasonChip({ flag }: Props) {
  const Icon = flag.code === "CRITICAL_VALUE"
    ? AlertOctagon
    : flag.code === "LOW_OCR_CONFIDENCE"
      ? FileSearch
      : MessageCircle;
  const tone = flag.code === "CRITICAL_VALUE"
    ? "critical"
    : flag.code === "LOW_OCR_CONFIDENCE"
      ? "ocr"
      : "question";

  return (
    <span className={`chip-reason chip-reason--${tone}`}>
      <Icon aria-hidden="true" />
      {flag.detail}
    </span>
  );
}
