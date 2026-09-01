import { Fragment } from "react";
import { Check } from "lucide-react";

import { cn } from "@/lib/utils";

const ANALYSIS_WORKFLOW_STEPS = [
  "Tải phiếu",
  "Kiểm tra dữ liệu",
  "Phân tích",
  "Xem kết quả",
] as const;

type AnalysisProgressStep = 1 | 2 | 3 | 4;

type Props = {
  currentStep: AnalysisProgressStep;
};

/**
 * The single visual source of truth for the OCR analysis workflow.
 * State changes may alter only the circle content and quiet semantic color;
 * the DOM and geometry stay identical from upload through result.
 */
export default function AnalysisProgressStepper({ currentStep }: Props) {
  return (
    <ol
      className="m-0 flex list-none items-center overflow-x-auto whitespace-nowrap p-0 pb-2 text-sm font-medium select-none sm:pb-0"
      aria-label="Quy trình phân tích phiếu xét nghiệm"
    >
      {ANALYSIS_WORKFLOW_STEPS.map((label, index) => {
        const step = (index + 1) as AnalysisProgressStep;
        const isComplete = step < currentStep;
        const isCurrent = step === currentStep;
        const isReached = isComplete || isCurrent;

        return (
          <Fragment key={label}>
            <li
              className={cn(
                "flex items-center gap-2",
                isReached ? "text-foreground" : "text-muted-foreground/70",
              )}
              data-state={isComplete ? "complete" : isCurrent ? "current" : "pending"}
              aria-current={isCurrent ? "step" : undefined}
              aria-label={isComplete ? `${label}, đã hoàn tất` : isCurrent ? `${label}, bước hiện tại` : label}
            >
              <span
                className={cn(
                  "flex size-6 items-center justify-center rounded-full border text-xs font-semibold",
                  isReached
                    ? "border-[var(--border)] bg-[var(--surface)] shadow-sm"
                    : "border-[var(--border)]/50",
                )}
                aria-hidden="true"
              >
                {isComplete ? <Check className="size-3.5" strokeWidth={2.25} /> : step}
              </span>
              <span>{label}</span>
            </li>
            {index < ANALYSIS_WORKFLOW_STEPS.length - 1 ? (
              <li
                className="mx-3 h-px w-8 bg-[var(--border)]/60 sm:mx-4 sm:w-12"
                aria-hidden="true"
              />
            ) : null}
          </Fragment>
        );
      })}
    </ol>
  );
}
