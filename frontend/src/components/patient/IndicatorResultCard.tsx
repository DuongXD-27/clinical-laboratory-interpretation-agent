"use client";

import SourcesDisclosure from "@/components/patient/SourcesDisclosure";
import DoctorNoteBlock from "@/components/common/DoctorNoteBlock";
import { indicatorStatusText, reportTone } from "@/lib/patientUi.mjs";
import type { IndicatorResult } from "@/types/analysis";

function getIndicatorCriticalText(critical_status?: string | null) {
  if (!critical_status) return "Giá trị khẩn cấp";
  const critNormalized = String(critical_status).toUpperCase();
  if (critNormalized === "CRITICAL_HIGH") return "Giá trị khẩn cấp – cao";
  if (critNormalized === "CRITICAL_LOW") return "Giá trị khẩn cấp – thấp";
  return "Giá trị khẩn cấp";
}

function renderSafeReferenceRange(indicator: IndicatorResult) {
  const status = String(indicator.status).toUpperCase();
  if (status === "UNKNOWN" || status === "HOLD") {
    return "Chưa xác định khoảng tham chiếu";
  }
  
  if (indicator.rule_type) {
    if (indicator.rule_type === "CDL" || indicator.rule_type === "BAND") {
      return "Phân loại theo quy tắc lâm sàng";
    }
    if (indicator.rule_type === "ONE_SIDED_LIMIT") {
      if (indicator.upper_operator && indicator.reference_high !== null && indicator.reference_high !== undefined) {
        return `Ngưỡng: ${indicator.upper_operator} ${indicator.reference_high} ${indicator.unit}`;
      }
      if (indicator.reference_low !== null && indicator.reference_low !== undefined) {
        return `Giới hạn dưới tham chiếu: ${indicator.reference_low} ${indicator.unit}`;
      }
      return null;
    }
    if (indicator.reference_low !== null || indicator.reference_high !== null) {
      return `Khoảng tham chiếu hệ thống: ${indicator.reference_low ?? "-"} – ${indicator.reference_high ?? "-"}`;
    }
    return null;
  }

  if (indicator.reference_low !== null && indicator.reference_high !== null) {
    return `Khoảng tham chiếu hệ thống: ${indicator.reference_low} – ${indicator.reference_high}`;
  }

  return "Chi tiết quy tắc tham chiếu không được lưu ở phiên bản này.";
}

type Props = {
  indicator: IndicatorResult & {
    analyte_raw?: string | null;
    analyte_canonical?: string | null;
  };
};

export default function IndicatorResultCard({ indicator }: Props) {
  const tone = reportTone(indicator.status);
  
  const hasAISection = !!(indicator.explanation || indicator.doctor_note || (indicator.sources && indicator.sources.length > 0));
  const safeReference = renderSafeReferenceRange(indicator);
  
  return (
    <article className={`result-card result-card-${tone}`}>
      {/* LEVEL A — RESULT IDENTITY */}
      <div className="flex flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-[17px] font-semibold text-slate-950">{indicator.analyte_canonical ?? indicator.name}</h3>
          {indicator.analyte_raw && indicator.analyte_raw !== (indicator.analyte_canonical ?? indicator.name) && (
            <p className="mt-0.5 text-xs text-slate-500">Tên gốc: {indicator.analyte_raw}</p>
          )}
        </div>
        <div className="text-left sm:text-right mt-1 sm:mt-0">
          <p className="text-xl font-semibold text-slate-900">
            {indicator.value} <span className="text-sm font-normal text-slate-500">{indicator.unit}</span>
          </p>
        </div>
      </div>
      
      {/* LEVEL B — FACTUAL CLINICAL DATA */}
      <div className="mt-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-2">
        <div className="text-sm text-slate-600">
          {safeReference}
        </div>
        <div className="flex flex-wrap items-center gap-1.5 sm:justify-end">
          <span className={`status-badge status-${tone}`}>{indicatorStatusText(indicator.status)}</span>
          {(indicator.is_critical || !!indicator.critical_status) && (
            <span className="status-badge status-critical">{getIndicatorCriticalText(indicator.critical_status)}</span>
          )}
        </div>
      </div>

      {/* LEVEL C — AI INTERPRETATION */}
      {hasAISection && (
        <div className="result-card-ai mt-3 border-t border-slate-100/70 pt-3">
          <div className="grid grid-cols-1 gap-y-1.5 lg:grid-cols-[112px_minmax(0,1fr)] lg:gap-x-4">
            <div>
              {indicator.explanation && (
                <p className="text-sm font-semibold text-slate-900">Giải thích của AI</p>
              )}
            </div>
            <div className="flex min-w-0 flex-col gap-2.5">
              {indicator.explanation && (
                <p className="text-sm leading-[1.55] text-slate-700">
                  {indicator.explanation}
                </p>
              )}
              {indicator.doctor_note && (
                <DoctorNoteBlock
                  note={indicator.doctor_note}
                  doctorName={indicator.reviewed_by_username}
                  reviewedAt={indicator.reviewed_at}
                />
              )}
              <SourcesDisclosure sources={indicator.sources} />
            </div>
          </div>
        </div>
      )}
    </article>
  );
}
