"use client";

import { useId, useState, type ReactNode } from "react";
import { Sparkles } from "lucide-react";
import { formatClinicalText, formatClinicalUnitSuffix } from "@/lib/clinicalUnit.mjs";
import { cn } from "@/lib/utils";

type Props = {
  tone: "normal" | "abnormal" | "critical" | "unknown" | string;
  title: ReactNode;
  titleMeta?: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  reference?: ReactNode;
  status?: ReactNode;
  notice?: ReactNode;
  reason?: ReactNode;
  explanation?: ReactNode;
  explanationText?: string | null;
  interpretationExtra?: ReactNode;
  sourceFooter?: ReactNode;
  actionFooter?: ReactNode;
  headingLevel?: "h2" | "h3";
  className?: string;
};

export default function ClinicalIndicatorCard({
  tone,
  title,
  titleMeta,
  value,
  unit,
  reference,
  status,
  notice,
  reason,
  explanation,
  explanationText,
  interpretationExtra,
  sourceFooter,
  actionFooter,
  headingLevel = "h3",
  className,
}: Props) {
  const [expanded, setExpanded] = useState(false);
  const explanationId = useId();
  const Heading = headingLevel;
  const canToggle = (explanationText?.length ?? 0) > 280;
  const hasInterpretation = Boolean(explanation || explanationText || interpretationExtra || sourceFooter);
  const displayUnit = typeof unit === "string" || typeof unit === "number"
    ? formatClinicalUnitSuffix(unit)
    : unit;
  const displayExplanationText = explanationText ? formatClinicalText(explanationText) : explanationText;

  return (
    <article className={cn("clinical-indicator-card clinical-card", `clinical-card--${tone}`, className)}>
      <div className="clinical-card__header">
        <div className="clinical-card__identity">
          <Heading className="clinical-card__title">{title}</Heading>
          {titleMeta ? <div className="clinical-card__title-meta">{titleMeta}</div> : null}
        </div>
        <div className="clinical-card__measurement">
          <span className="clinical-card__value">{value}</span>
          {displayUnit ? <span className="clinical-card__unit">{displayUnit}</span> : null}
        </div>
      </div>

      {notice}

      {(reference || status) ? (
        <div className="clinical-card__subheader">
          {reference ? <div className="clinical-card__reference">{reference}</div> : <span />}
          {status ? <div className="clinical-card__status">{status}</div> : null}
        </div>
      ) : null}

      {reason ? <div className="clinical-card__reason">{reason}</div> : null}

      {hasInterpretation ? (
        <div className="clinical-card__interpretation">
          {(explanation || explanationText) ? (
            <>
              <p className="clinical-card__label"><Sparkles aria-hidden="true" /> Giải thích của AI</p>
              <div
                id={explanationId}
                className={cn("clinical-card__explanation", expanded && "is-expanded")}
              >
                {explanation ?? displayExplanationText}
              </div>
              {canToggle ? (
                <button
                  type="button"
                  className="clinical-card__toggle"
                  aria-controls={explanationId}
                  aria-expanded={expanded}
                  onClick={() => setExpanded((current) => !current)}
                >
                  {expanded ? "Thu gọn" : "Xem thêm"}
                </button>
              ) : null}
            </>
          ) : null}
          {interpretationExtra}
          {sourceFooter ? <div className="clinical-card__source-footer">{sourceFooter}</div> : null}
        </div>
      ) : null}

      {actionFooter ? <div className="clinical-card__action-footer">{actionFooter}</div> : null}
    </article>
  );
}
