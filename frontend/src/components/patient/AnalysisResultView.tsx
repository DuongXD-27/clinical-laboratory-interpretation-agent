"use client";

import Link from "next/link";
import QuestionsForDoctorPanel from "@/components/QuestionsForDoctorPanel";
import SourcesDisclosure from "@/components/patient/SourcesDisclosure";
import { indicatorStatusText } from "@/lib/patientUi.mjs";
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
          <h2 id="result-title">Kết quả xét nghiệm</h2>
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

        {(result.out_of_scope_indicators?.length ?? 0) > 0 && (
          <div className="info-message mt-5" role="status">
            <p className="font-semibold text-slate-800">Một số chỉ số hiện chưa được hỗ trợ</p>
            <p className="mt-1">
              {result.out_of_scope_indicators?.join(", ")} hiện tại chưa được hỗ trợ, nên chưa được đưa vào phần phân tích.
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

        <div className="mt-5 grid gap-3">
          {result.indicators?.map((indicator, index) => {
            const tone = indicator.is_critical ? "critical" : indicator.is_abnormal ? "abnormal" : "normal";
            return (
              <article key={`${indicator.name}-${index}`} className={`result-card result-card-${tone}`}>
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                  <div>
                    <h3 className="font-semibold text-slate-950">{indicator.name}</h3>
                    <p className="mt-1 text-2xl font-bold tracking-tight text-slate-950">
                      {indicator.value} <span className="text-sm font-medium text-slate-500">{indicator.unit}</span>
                    </p>
                    {(indicator.reference_low !== null || indicator.reference_high !== null) && (
                      <p className="mt-1 text-xs text-slate-500">
                        Tham chiếu: {indicator.reference_low ?? "-"} – {indicator.reference_high ?? "-"}
                      </p>
                    )}
                  </div>
                  <span className={`status-badge status-${tone}`}>{indicatorStatusText(indicator.status)}</span>
                </div>
                {indicator.explanation && <p className="mt-4 text-sm leading-6 text-slate-600">{indicator.explanation}</p>}
                <SourcesDisclosure sources={indicator.sources} />
              </article>
            );
          })}
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
