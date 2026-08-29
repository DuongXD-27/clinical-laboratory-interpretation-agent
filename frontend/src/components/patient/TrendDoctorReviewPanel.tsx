"use client";

import { useCallback, useEffect, useState } from "react";
import {
  createPatientTrendReviewRequest,
  fetchPatientTrendReviewState,
  UnauthorizedError,
} from "@/lib/api";
import { formatMoment } from "@/lib/patientUi.mjs";
import type { TrendResponse, TrendReviewPatientState } from "@/types/analysis";
import TrendReviewHistoryPanel from "./TrendReviewHistoryPanel";
import StatusIndicator from "@/components/common/StatusIndicator";

type Props = {
  trend: TrendResponse;
  explanation: string | null;
  onUnauthorized: () => void;
};

function assessmentText(value: string | null | undefined) {
  if (value === "confirmed") return "Bác sĩ xác nhận xu hướng";
  if (value === "corrected") return "Bác sĩ đã đính chính";
  if (value === "needs_follow_up") return "Cần theo dõi/trao đổi thêm";
  return "Đã được bác sĩ review";
}

function requestReason(state: TrendReviewPatientState | null, hasExplanation: boolean) {
  if (!hasExplanation) return "Cần tạo giải thích xu hướng trước khi gửi bác sĩ review.";
  if (!state) return "";
  if (state.reason === "PENDING_EXISTS") return "Yêu cầu review đang chờ bác sĩ xử lý.";
  if (state.reason === "LATEST_REVIEW_STILL_CURRENT") return "Review mới nhất vẫn khớp dữ liệu xu hướng hiện tại.";
  if (state.reason === "CURRENT_TREND_CHANGED") return "Biểu đồ hiện tại đã thay đổi từ lần bác sĩ review gần nhất.";
  if (state.reason === "TREND_UNAVAILABLE") return "Xu hướng này chưa đủ dữ liệu để gửi review.";
  return "";
}

export default function TrendDoctorReviewPanel({ trend, explanation, onUnauthorized }: Props) {
  const [state, setState] = useState<TrendReviewPatientState | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [showHistory, setShowHistory] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setState(await fetchPatientTrendReviewState(trend.analyte_canonical, trend.filter));
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không tải được trạng thái review.");
    } finally {
      setLoading(false);
    }
  }, [onUnauthorized, trend.analyte_canonical, trend.filter]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- load() synchronizes server review state for the visible trend.
    void load();
  }, [load]);

  async function sendRequest() {
    if (!explanation) return;
    setSending(true);
    setError(null);
    try {
      const response = await createPatientTrendReviewRequest(
        trend.analyte_canonical,
        trend.filter,
        explanation,
      );
      setState((current) => ({
        latest_review: current?.latest_review ?? null,
        latest_historical_review: current?.latest_historical_review ?? null,
        pending_request: response.review,
        can_request_review: false,
        reason: "PENDING_EXISTS",
        current_trend_hash: response.review.trend_snapshot_hash,
        history_count: current?.history_count ?? 0,
      }));
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không gửi được yêu cầu review.");
    } finally {
      setSending(false);
    }
  }

  const latest = state?.latest_review;
  const pending = state?.pending_request;
  const hasHistory = Boolean((state?.history_count ?? 0) > 0 || state?.latest_historical_review);
  const hasExplanation = Boolean(explanation?.trim());
  const canSend = Boolean(state?.can_request_review && hasExplanation && !sending);
  const reason = requestReason(state, hasExplanation);

  return (
    <>
    <section className="patient-glass-clinical p-5 sm:p-6" aria-labelledby="trend-doctor-review-title">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h3 id="trend-doctor-review-title" className="text-sm font-semibold text-slate-800">
            Đề nghị review của bác sĩ
          </h3>
          <p className="mt-1 text-sm text-slate-600">
            {loading
              ? "Đang tải trạng thái review..."
              : pending
                ? "Yêu cầu đã được gửi tới bác sĩ."
                : latest
                  ? assessmentText(latest.doctor_assessment)
                  : state?.latest_historical_review
                    ? "Chưa có nhận xét của bác sĩ cho biểu đồ hiện tại"
                    : "Chưa có nhận xét của bác sĩ"}
          </p>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end">
          {hasHistory && (
            <button
              type="button"
              className="patient-btn-secondary shrink-0"
              onClick={() => setShowHistory((value) => !value)}
            >
              {showHistory ? "Ẩn lịch sử review" : "Xem lịch sử review"}
            </button>
          )}
          {!pending && (
            <button
              type="button"
              className="patient-btn-secondary shrink-0"
              disabled={!canSend}
              onClick={() => void sendRequest()}
            >
              {sending
                ? "Đang gửi..."
                : hasHistory
                  ? "Gửi yêu cầu review lại"
                  : "Gửi yêu cầu tới bác sĩ"}
            </button>
          )}
        </div>
      </div>

      {pending && (
        <div className="status-review-note mt-4">
          <StatusIndicator state="pending" label="Đang chờ bác sĩ review" />
          <span>Gửi lúc {formatMoment(pending.requested_at)}.</span>
        </div>
      )}

      {latest?.doctor_comment && (
        <div className="status-review-note mt-4">
          <StatusIndicator
            state={latest.doctor_assessment === "corrected" ? "corrected" : latest.doctor_assessment === "needs_follow_up" ? "reviewing" : "completed"}
            label={assessmentText(latest.doctor_assessment)}
          />
          <p className="text-sm whitespace-pre-wrap leading-relaxed text-slate-800">{latest.doctor_comment}</p>
          <p className="text-xs text-slate-600">
            {latest.reviewed_by_username || "Bác sĩ"}
            {latest.reviewed_at ? ` · ${formatMoment(latest.reviewed_at)}` : ""}
          </p>
        </div>
      )}

      {reason && !pending && <p className="mt-3 text-xs text-slate-500">{reason}</p>}
      {error && <div className="error-message mt-4" role="alert">{error}</div>}

    </section>
      {showHistory && (
        <TrendReviewHistoryPanel
          trend={trend}
          onUnauthorized={onUnauthorized}
          onClose={() => setShowHistory(false)}
        />
      )}
    </>
  );
}
