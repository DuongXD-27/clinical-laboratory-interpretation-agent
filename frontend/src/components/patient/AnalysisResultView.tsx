"use client";

import Link from "next/link";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import IndicatorResultCard from "@/components/patient/IndicatorResultCard";
import { reportTone, sortIndicatorsBySeverity } from "@/lib/patientUi.mjs";
import { formatClinicalText } from "@/lib/clinicalUnit.mjs";
import type { AnalysisResult } from "@/types/analysis";
import PatientPageHeader from "@/components/patient/PatientPageHeader";
import AnalysisProgressStepper from "@/components/patient/AnalysisProgressStepper";
import StatusIndicator from "@/components/common/StatusIndicator";
import { FileText, RotateCcw } from "lucide-react";
type Props = {
  result: AnalysisResult;
  criticalAcknowledged: boolean;
  onAcknowledgeCritical: () => void;
  onNewAnalysis: () => void;
  onUnauthorized: () => void;
  sourceMode: "manual" | "ocr";
};



export default function AnalysisResultView({
  result,
  criticalAcknowledged,
  onAcknowledgeCritical,
  onNewAnalysis,
  onUnauthorized,
  sourceMode,
}: Props) {
  const hasCritical = result.critical_alerts.length > 0;
  const showCriticalBanner = hasCritical && !criticalAcknowledged;
  const reportId = result.saved_report_id ?? result.report_id ?? result.existing_report_id ?? null;

  // Display-only grouping of backend-provided statuses so the patient can scan
  // "cần chú ý" vs "bình thường" without reading every card. No reclassification.
  const toneCounts = { critical: 0, abnormal: 0, unknown: 0, normal: 0 };
  for (const indicator of result.indicators ?? []) {
    toneCounts[reportTone(indicator.status)] += 1;
  }
  const orderedIndicators = sortIndicatorsBySeverity(result.indicators ?? []);

  return (
    <section className="results-section" aria-labelledby="result-title">
      {sourceMode === "ocr" && (
        <AnalysisProgressStepper currentStep={4} />
      )}
      <PatientPageHeader
        eyebrow="Kết quả phân tích"
        title="Kết quả xét nghiệm"
        titleId="result-title"
        description={`Hệ thống đã phân tích ${result.indicators?.length ?? 0} chỉ số trong phiếu xét nghiệm.`}
        className="analysis-result-heading"
        actions={<>
          {reportId && (
            <Link href={`/patient/reports/${reportId}`} transitionTypes={["nav-forward"]} className="secondary-button">
              <FileText aria-hidden="true" />
              Mở trang chi tiết
            </Link>
          )}
          <button type="button" onClick={onNewAnalysis} className="primary-button">
            <RotateCcw aria-hidden="true" />
            Phân tích phiếu khác
          </button>
        </>}
      />

      {showCriticalBanner && (
        <div className="critical-banner" role="alert">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-white/80">Cần chú ý ngay</p>
            <h2 className="mt-1 text-xl font-bold">Cảnh báo sức khỏe nghiêm trọng</h2>
            <div className="mt-2 space-y-1 text-sm leading-6 text-white/90">
              {result.critical_alerts.map((alert, index) => <p key={index}>{formatClinicalText(alert.message)}</p>)}
            </div>
          </div>
          <button type="button" onClick={onAcknowledgeCritical} className="critical-button">
            Tôi sẽ liên hệ bác sĩ
          </button>
        </div>
      )}

      <div className="analysis-result-summary">
        {result.summary && <div className="summary-box">{formatClinicalText(result.summary)}</div>}

        {(result.indicators?.length ?? 0) > 0 && (
          <dl className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Tổng quan tình trạng chỉ số">
            {toneCounts.critical > 0 && (
              <div className="flex items-center gap-1.5">
                <dt><StatusIndicator state="critical" label="Nguy kịch" level="inline" /></dt>
                <dd className="font-bold">{toneCounts.critical}</dd>
              </div>
            )}
            {toneCounts.abnormal > 0 && (
              <div className="flex items-center gap-1.5">
                <dt><StatusIndicator state="abnormal" label="Cần lưu ý" level="inline" /></dt>
                <dd className="font-bold">{toneCounts.abnormal}</dd>
              </div>
            )}
            {toneCounts.unknown > 0 && (
              <div className="flex items-center gap-1.5">
                <dt><StatusIndicator state="unknown" label="Chưa đánh giá được" /></dt>
                <dd className="font-bold">{toneCounts.unknown}</dd>
              </div>
            )}
            {toneCounts.normal > 0 && (
              <div className="flex items-center gap-1.5">
                <dt><StatusIndicator state="normal" /></dt>
                <dd className="font-bold">{toneCounts.normal}</dd>
              </div>
            )}
          </dl>
        )}

        {(result.out_of_scope_indicators?.length ?? 0) > 0 && (
          <div className="info-message mt-5" role="status">
            <p className="font-semibold text-slate-800">Chưa được hệ thống hỗ trợ diễn giải</p>
            <p className="mt-1">
              {result.out_of_scope_indicators?.join(", ")}
            </p>
          </div>
        )}

        {result.duplicate && (
          <div className="info-message mt-5" role="status">
            Kết quả xét nghiệm này có vẻ đã được lưu trước đó.
            {result.existing_report_id && (
              <Link href={`/patient/reports/${result.existing_report_id}`} transitionTypes={["nav-forward"]} className="ml-2 text-blue-700 hover:underline">
                Xem kết quả đã lưu
              </Link>
            )}
          </div>
        )}

        {result.saved && reportId && (
          <div className="info-message mt-5" role="status">
            Kết quả đã được lưu vào lịch sử xét nghiệm.
            <Link href={`/patient/reports/${reportId}`} transitionTypes={["nav-forward"]} className="ml-2 text-blue-700 hover:underline">
              Xem chi tiết
            </Link>
          </div>
        )}

      </div>

      <div className="indicator-card-grid analysis-indicator-grid">
        {orderedIndicators.map((indicator, index) => (
          <IndicatorResultCard key={`${indicator.name}-${index}`} indicator={indicator} />
        ))}
      </div>

      <div className="disclaimer-box" role="note" aria-label="Lưu ý y khoa">
        <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
        <p className="mt-1">
          {formatClinicalText(result.disclaimer ?? "Kết quả do AI tạo ra chỉ nhằm mục đích tham khảo, không thay thế chẩn đoán y khoa. Vui lòng tham vấn bác sĩ chuyên môn.")}
        </p>
      </div>

      {!showCriticalBanner && (
        <QuestionsForDoctorPanel
          questions={result.questions_for_doctor ?? []}
          reportId={reportId}
          onUnauthorized={onUnauthorized}
        />
      )}
    </section>
  );
}
