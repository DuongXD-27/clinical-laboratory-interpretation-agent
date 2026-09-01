"use client";

import Link from "next/link";
import { ViewTransition } from "react";
import SourcesDisclosure from "@/components/patient/SourcesDisclosure";
import DoctorNoteBlock from "@/components/common/DoctorNoteBlock";
import ClinicalIndicatorCard from "@/components/common/ClinicalIndicatorCard";
import { indicatorDisplayLabel, referencePresentation, reportTone } from "@/lib/patientUi.mjs";
import { formatClinicalText } from "@/lib/clinicalUnit.mjs";
import type { IndicatorResult } from "@/types/analysis";
import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import { motionElementName } from "@/lib/motion";

function getIndicatorCriticalText(critical_status?: string | null) {
  if (!critical_status) return "Giá trị khẩn cấp";
  const critNormalized = String(critical_status).toUpperCase();
  if (critNormalized === "CRITICAL_HIGH") return "Giá trị khẩn cấp – cao";
  if (critNormalized === "CRITICAL_LOW") return "Giá trị khẩn cấp – thấp";
  return "Giá trị khẩn cấp";
}

type Props = {
  indicator: IndicatorResult & {
    analyte_raw?: string | null;
    analyte_canonical?: string | null;
  };
};

export default function IndicatorResultCard({ indicator }: Props) {
  const tone = reportTone(indicator.status);
  const analyteId = indicator.analyte_canonical ?? indicator.name;
  
  const explanationCitations = indicator.explanation_sources ?? indicator.citations ?? [];
  const hasAISection = !!(indicator.explanation || indicator.doctor_note || explanationCitations.length > 0 || (indicator.sources && indicator.sources.length > 0));
  const reference = referencePresentation(indicator);

  return (
    <ClinicalIndicatorCard
      tone={tone}
      className={`result-card result-card-${tone}`}
      title={(
        <ViewTransition name={motionElementName("patient-analyte", analyteId)} default="none" share="lumilens-shared-detail">
          <Link
            href={`/patient/trends?analyte=${encodeURIComponent(analyteId)}`}
            transitionTypes={["nav-forward"]}
            className="clinical-card__trend-link"
          >
            {analyteId}
          </Link>
        </ViewTransition>
      )}
      titleMeta={indicator.analyte_raw && indicator.analyte_raw !== (indicator.analyte_canonical ?? indicator.name)
        ? <>Tên gốc: {indicator.analyte_raw}</>
        : undefined}
      value={indicator.value}
      unit={indicator.unit}
      notice={String(indicator.input_integrity_status || "").toUpperCase() === "NEED_REVIEW" ? (
        <div className="input-review-callout mt-3" role="status">
          <StatusIndicator state="input-review" size="md" />
          <span>{formatClinicalText(indicator.input_integrity_message || "Hãy đối chiếu tên chỉ số, giá trị và đơn vị với phiếu gốc.")}</span>
        </div>
      ) : undefined}
      reference={reference.primary ? (
        <div className="flex flex-col gap-1">
          <span>{reference.primary}</span>
          {reference.secondary ? <span>{reference.secondary}</span> : null}
        </div>
      ) : undefined}
      status={(
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          {tone !== "critical" && <StatusIndicator state={tone as StatusState} label={indicatorDisplayLabel(indicator)} />}
          {(tone === "critical" || indicator.is_critical || !!indicator.critical_status) && (
            <StatusIndicator state="critical" label={getIndicatorCriticalText(indicator.critical_status)} />
          )}
        </div>
      )}
      explanationText={hasAISection ? indicator.explanation : undefined}
      interpretationExtra={indicator.doctor_note ? (
            <DoctorNoteBlock
              note={indicator.doctor_note}
              doctorName={indicator.reviewed_by_username}
              reviewedAt={indicator.reviewed_at}
            />
      ) : undefined}
      sourceFooter={hasAISection ? <SourcesDisclosure sources={indicator.sources} citations={explanationCitations} /> : undefined}
    />
  );
}
