"use client";

import Link from "next/link";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import IndicatorResultCard from "@/components/patient/IndicatorResultCard";
import { reportTone, sortIndicatorsBySeverity } from "@/lib/patientUi.mjs";
import type { AnalysisResult } from "@/types/analysis";
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
        <ol className="ocr-stepper ocr-stepper-result" aria-label="Quy trình phân tích ảnh đã hoàn tất">
          {["Tải phiếu", "Kiểm tra dữ liệu", "Phân tích", "Xem kết quả"].map((label, index) => (
            <li key={label} className="complete" aria-current={index === 3 ? "step" : undefined}>
              <span aria-hidden="true">✓</span>
              <strong>{label}</strong>
            </li>
          ))}
        </ol>
      )}
      <div className="page-section-heading analysis-result-heading">
        <div>
          <span className="eyebrow">Kết quả phân tích</span>
          <h1 id="result-title">Kết quả xét nghiệm</h1>
          <p>Hệ thống đã phân tích {result.indicators?.length ?? 0} chỉ số trong phiếu xét nghiệm.</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {reportId && (
            <Link href={`/patient/reports/${reportId}`} className="secondary-button">
              Mở trang chi tiết
            </Link>
          )}
          <button type="button" onClick={onNewAnalysis} className="primary-button">
            Phân tích phiếu khác
          </button>
        </div>
      </div>

      {showCriticalBanner && (
        <div className="critical-banner" role="alert">
          <div>
            <p className="text-xs font-bold uppercase tracking-[0.14em] text-red-100">Cần chú ý ngay</p>
            <h2 className="mt-1 text-xl font-bold">Cảnh báo sức khỏe nghiêm trọng</h2>
            <div className="mt-2 space-y-1 text-sm leading-6 text-red-50">
              {result.critical_alerts.map((alert, index) => <p key={index}>{alert.message}</p>)}
            </div>
          </div>
          <button type="button" onClick={onAcknowledgeCritical} className="critical-button">
            Tôi sẽ liên hệ bác sĩ
          </button>
        </div>
      )}

      <div className="patient-card p-5 sm:p-7">
        {result.summary && <div className="summary-box">{result.summary}</div>}

        {(result.indicators?.length ?? 0) > 0 && (
          <dl className="mt-5 flex flex-wrap gap-x-6 gap-y-2 text-sm" aria-label="Tổng quan tình trạng chỉ số">
            {toneCounts.critical > 0 && (
              <div className="flex items-center gap-1.5 font-medium text-[var(--status-critical-fg)]">
                <span className="w-2 h-2 rounded-full bg-[var(--status-critical-border)]" aria-hidden="true" />
                <dt>Nguy kịch</dt>
                <dd className="font-bold">{toneCounts.critical}</dd>
              </div>
            )}
            {toneCounts.abnormal > 0 && (
              <div className="flex items-center gap-1.5 font-medium text-[var(--status-abnormal-fg)]">
                <span className="w-2 h-2 rounded-full bg-[var(--status-abnormal-border)]" aria-hidden="true" />
                <dt>Cần lưu ý</dt>
                <dd className="font-bold">{toneCounts.abnormal}</dd>
              </div>
            )}
            {toneCounts.unknown > 0 && (
              <div className="flex items-center gap-1.5 font-medium text-[var(--status-unknown-fg)]">
                <span className="w-2 h-2 rounded-full bg-[var(--status-unknown-border)]" aria-hidden="true" />
                <dt>Chưa đánh giá được</dt>
                <dd className="font-bold">{toneCounts.unknown}</dd>
              </div>
            )}
            {toneCounts.normal > 0 && (
              <div className="flex items-center gap-1.5 font-medium text-[var(--status-normal-fg)]">
                <span className="w-2 h-2 rounded-full bg-[var(--status-normal-border)]" aria-hidden="true" />
                <dt>Bình thường</dt>
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
              <Link href={`/patient/reports/${result.existing_report_id}`} className="ml-2 text-blue-700 hover:underline">
                Xem kết quả đã lưu
              </Link>
            )}
          </div>
        )}

        {result.saved && reportId && (
          <div className="info-message mt-5" role="status">
            Kết quả đã được lưu vào lịch sử xét nghiệm.
            <Link href={`/patient/reports/${reportId}`} className="ml-2 text-blue-700 hover:underline">
              Xem chi tiết
            </Link>
          </div>
        )}

        <div className="mt-6 grid gap-3">
          {orderedIndicators.map((indicator, index) => (
            <IndicatorResultCard key={`${indicator.name}-${index}`} indicator={indicator} />
          ))}
        </div>

        <div className="disclaimer-box mt-6" role="note" aria-label="Lưu ý y khoa">
          <p className="font-semibold text-slate-700">Lưu ý quan trọng</p>
          <p className="mt-1">
            {result.disclaimer ?? "Kết quả do AI tạo ra chỉ nhằm mục đích tham khảo, không thay thế chẩn đoán y khoa. Vui lòng tham vấn bác sĩ chuyên môn."}
          </p>
        </div>
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
