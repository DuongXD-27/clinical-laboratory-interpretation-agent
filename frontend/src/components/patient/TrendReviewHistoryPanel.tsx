"use client";

import { useCallback, useEffect, useState } from "react";
import TrendChart from "@/components/TrendChart";
import {
  fetchPatientTrendReviewHistory,
  UnauthorizedError,
} from "@/lib/api";
import { formatDate, formatMoment } from "@/lib/patientUi.mjs";
import { formatClinicalText, formatClinicalUnit } from "@/lib/clinicalUnit.mjs";
import type { TrendResponse, TrendReview } from "@/types/analysis";
import StatusIndicator from "@/components/common/StatusIndicator";

type Props = {
  trend: TrendResponse;
  onUnauthorized: () => void;
  onClose: () => void;
};

function assessmentText(value: string | null | undefined) {
  if (value === "confirmed") return "Bác sĩ xác nhận xu hướng";
  if (value === "corrected") return "Bác sĩ đã đính chính";
  if (value === "needs_follow_up") return "Cần theo dõi/trao đổi thêm";
  return "Đã được bác sĩ đánh giá";
}

export default function TrendReviewHistoryPanel({ trend, onUnauthorized, onClose }: Props) {
  const [items, setItems] = useState<TrendReview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await fetchPatientTrendReviewHistory(trend.analyte_canonical, trend.filter);
      setItems(response.items);
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không tải được lịch sử đánh giá xu hướng.");
    } finally {
      setLoading(false);
    }
  }, [onUnauthorized, trend.analyte_canonical, trend.filter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() synchronizes history with the selected visible trend.
    void load();
  }, [load]);

  return (
    <section className="patient-glass-clinical p-5 sm:p-6" aria-labelledby="trend-review-history-title">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h3 id="trend-review-history-title" className="text-sm font-semibold text-slate-800">
            Lịch sử đánh giá xu hướng
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            Các nhận xét đã lưu cho những phiên bản biểu đồ trước đây của {trend.display_name}.
          </p>
        </div>
        <button type="button" className="patient-btn-secondary shrink-0" onClick={onClose}>
          Đóng lịch sử
        </button>
      </div>

      {loading && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white/60 px-4 py-3 text-sm text-slate-600" role="status">
          Đang tải lịch sử đánh giá...
        </div>
      )}

      {error && !loading && (
        <div className="error-message mt-4" role="alert">
          {error}
          <button type="button" onClick={() => void load()}>Thử lại</button>
        </div>
      )}

      {!error && !loading && items.length === 0 && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white/60 px-4 py-3 text-sm text-slate-600">
          Chưa có lịch sử đánh giá cho chỉ số này.
        </div>
      )}

      {!error && !loading && items.length > 0 && (
        <div className="mt-5 grid gap-4">
          {items.map((review, index) => (
            <details
              key={review.id}
              className="rounded-xl border border-slate-200 bg-white/70 p-4"
              open={index === 0}
            >
              <summary className="flex cursor-pointer list-none flex-col gap-1 sm:flex-row sm:items-center sm:justify-between">
                <StatusIndicator
                  state={review.doctor_assessment === "corrected" ? "corrected" : review.doctor_assessment === "needs_follow_up" ? "reviewing" : "completed"}
                  label={assessmentText(review.doctor_assessment)}
                  size="md"
                />
                <span className="text-xs text-slate-500">
                  {review.reviewed_at ? formatMoment(review.reviewed_at) : formatMoment(review.requested_at)}
                </span>
              </summary>

              <div className="mt-4 grid gap-4">
                {review.doctor_comment && (
                  <div className="status-review-note">
                    <p className="text-sm leading-relaxed text-slate-800 whitespace-pre-wrap">
                      {formatClinicalText(review.doctor_comment)}
                    </p>
                    <p className="text-xs text-slate-600">
                      {review.reviewed_by_username || "Bác sĩ"}
                      {review.reviewed_at ? ` · ${formatMoment(review.reviewed_at)}` : ""}
                    </p>
                  </div>
                )}

                <div>
                  <p className="mb-2 text-xs font-semibold uppercase text-slate-500">
                    Bản chụp biểu đồ đã được đánh giá
                  </p>
                  <TrendChart
                    analyte={review.trend_snapshot.display_name}
                    unit={review.trend_snapshot.canonical_unit}
                    points={review.trend_snapshot.points}
                    referenceLow={review.trend_snapshot.reference_low}
                    referenceHigh={review.trend_snapshot.reference_high}
                    criticalLow={review.trend_snapshot.critical_low}
                    criticalHigh={review.trend_snapshot.critical_high}
                    height={280}
                  />
                </div>

                <div className="rounded-xl border border-slate-200 bg-white/70 px-4 py-3">
                  <p className="mb-2 text-xs font-semibold uppercase text-slate-500">
                    Nhận xét AI tại thời điểm gửi
                  </p>
                  <p className="text-sm leading-relaxed text-slate-700">
                    {formatClinicalText(review.llm_explanation_snapshot)}
                  </p>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[420px] text-sm">
                    <thead>
                      <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase text-slate-500">
                        <th className="py-2 pr-4">Ngày</th>
                        <th className="py-2 pr-4">Giá trị</th>
                        <th className="py-2 pr-4">Đơn vị</th>
                        <th className="py-2">Đánh giá</th>
                      </tr>
                    </thead>
                    <tbody>
                      {review.trend_snapshot.points.map((point) => (
                        <tr key={`${review.id}-${point.report_id}-${point.test_date}`} className="border-b border-slate-100">
                          <td className="py-2 pr-4 text-slate-700">{formatDate(point.test_date)}</td>
                          <td className="py-2 pr-4 font-semibold text-slate-900">{point.value}</td>
                          <td className="py-2 pr-4 text-slate-600">{formatClinicalUnit(review.trend_snapshot.canonical_unit)}</td>
                          <td className="py-2 text-slate-600">{point.assessment}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </details>
          ))}
        </div>
      )}
    </section>
  );
}
