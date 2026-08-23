"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import TrendChart from "@/components/TrendChart";
import {
  clearSession,
  fetchDoctorTrendReviewDetail,
  submitDoctorTrendReview,
  UnauthorizedError,
} from "@/lib/api";
import { formatDate, formatMoment } from "@/lib/patientUi.mjs";
import type {
  DoctorTrendReviewDetail,
  TrendPoint,
  TrendReview,
  TrendReviewAssessment,
} from "@/types/analysis";

const ASSESSMENT_OPTIONS: { value: TrendReviewAssessment; label: string }[] = [
  { value: "confirmed", label: "Xác nhận nhận xét AI phù hợp" },
  { value: "corrected", label: "Đính chính hoặc bổ sung nhận xét AI" },
  { value: "needs_follow_up", label: "Cần theo dõi hoặc trao đổi thêm" },
];

function genderText(value: string | null) {
  if (value === "male") return "Nam";
  if (value === "female") return "Nữ";
  if (value === "other") return "Khác";
  return "Chưa có";
}

function statusText(review: TrendReview) {
  if (review.status === "PENDING") return "Đang chờ";
  if (review.status === "REVIEWED") return "Đã review";
  if (review.status === "CANCELLED") return "Đã huỷ";
  return "Từ chối";
}

function assessmentText(value: TrendReviewAssessment | null | undefined) {
  if (value === "confirmed") return "Bác sĩ xác nhận xu hướng";
  if (value === "corrected") return "Bác sĩ đã đính chính";
  if (value === "needs_follow_up") return "Cần theo dõi/trao đổi thêm";
  return "Đã được bác sĩ review";
}

export default function DoctorTrendReviewDetailPage() {
  const params = useParams<{ requestId: string }>();
  const router = useRouter();
  const requestId = Number(params.requestId);
  const [detail, setDetail] = useState<DoctorTrendReviewDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [assessment, setAssessment] = useState<TrendReviewAssessment>("confirmed");
  const [comment, setComment] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchDoctorTrendReviewDetail(requestId);
        setDetail(data);
        setAssessment(data.review.doctor_assessment ?? "confirmed");
        setComment(data.review.doctor_comment ?? "");
      } catch (caught) {
        if (caught instanceof UnauthorizedError) {
          clearSession();
          router.replace("/");
          return;
        }
        setError(caught instanceof Error ? caught.message : "Không mở được yêu cầu review xu hướng.");
      } finally {
        setLoading(false);
      }
    }
    if (Number.isFinite(requestId)) void load();
  }, [requestId, router]);

  const review = detail?.review ?? null;
  const points = useMemo(() => review?.trend_snapshot.points ?? [], [review]);
  const readOnly = review?.status !== "PENDING";
  const canSubmit = Boolean(!readOnly && comment.trim().length > 0 && !saving);

  async function handleSubmit() {
    if (!review || !canSubmit) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await submitDoctorTrendReview(review.id, assessment, comment);
      setDetail((current) => current ? { ...current, review: updated } : current);
      setToast("Đã lưu review xu hướng.");
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        clearSession();
        router.replace("/");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không lưu được review xu hướng.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="doctor-portal">
        <section className="doctor-report-shell">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </section>
      </main>
    );
  }

  if (error || !detail || !review) {
    return (
      <main className="doctor-portal">
        <section className="doctor-report-shell">
          <div className="doctor-error-state" role="alert">
            <p>{error || "Không tìm thấy yêu cầu review xu hướng."}</p>
            <Link href="/doctor/trend-reviews">Quay lại danh sách</Link>
          </div>
        </section>
      </main>
    );
  }

  return (
    <main className="doctor-portal">
      {toast && <div className="doctor-toast" role="status">{toast}</div>}
      <section className="doctor-report-shell">
        <header className="doctor-report-header">
          <Link href="/doctor/trend-reviews">‹ Danh sách review xu hướng</Link>
          <div className="doctor-report-header__row">
            <div>
              <h1>{detail.patient.name}</h1>
              <p>
                {genderText(detail.patient.gender)} · {detail.patient.age ?? "-"} tuổi · {review.display_name}
              </p>
            </div>
            <div className="doctor-report-header__badges">
              <span className="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-xs font-bold text-slate-700">
                {statusText(review)}
              </span>
            </div>
          </div>
        </header>

        {review.status === "REVIEWED" && (
          <div className="doctor-verified-banner">
            <span aria-hidden="true">✓</span>
            Đã review bởi {review.reviewed_by_username || "bác sĩ"}
            {review.reviewed_at ? ` lúc ${formatMoment(review.reviewed_at)}` : ""}.
          </div>
        )}

        {error && <div className="doctor-error-state" role="alert">{error}</div>}

        <div className="doctor-report-grid">
          <section className="doctor-finding-list" aria-label="Chi tiết review xu hướng">
            <article className="finding-card finding-card--normal">
              <div className="finding-card__header">
                <div>
                  <h2>{review.display_name}</h2>
                  <p className="finding-card__ref">
                    {review.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"} · {review.canonical_unit}
                  </p>
                </div>
                <span className="text-xs font-semibold text-slate-500">
                  Gửi lúc {formatMoment(review.requested_at)}
                </span>
              </div>

              <div className="mt-5">
                <TrendChart
                  analyte={review.display_name}
                  unit={review.canonical_unit}
                  points={points}
                  referenceLow={review.trend_snapshot.reference_low}
                  referenceHigh={review.trend_snapshot.reference_high}
                  criticalLow={review.trend_snapshot.critical_low}
                  criticalHigh={review.trend_snapshot.critical_high}
                />
              </div>

              <div className="finding-card__ai">
                <p className="finding-card__label">Nhận xét xu hướng của AI</p>
                <p>{review.llm_explanation_snapshot}</p>
              </div>
            </article>

            <article className="finding-card finding-card--normal">
              <div className="finding-card__header">
                <div>
                  <h2>Dữ liệu các mốc xét nghiệm</h2>
                  <p className="finding-card__ref">{points.length} mốc được snapshotted khi bệnh nhân gửi yêu cầu.</p>
                </div>
              </div>
              <div className="mt-4 overflow-x-auto">
                <table className="w-full min-w-[520px] text-sm">
                  <thead>
                    <tr className="border-b border-slate-200 text-left text-xs font-bold uppercase text-slate-500">
                      <th className="py-2 pr-4">Ngày xét nghiệm</th>
                      <th className="py-2 pr-4">Giá trị</th>
                      <th className="py-2 pr-4">Đơn vị</th>
                      <th className="py-2 pr-4">Đánh giá</th>
                      <th className="py-2">Phiếu</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((point: TrendPoint) => (
                      <tr key={`${point.report_id}-${point.test_date}`} className="border-b border-slate-100">
                        <td className="py-3 pr-4 text-slate-700">{formatDate(point.test_date)}</td>
                        <td className="py-3 pr-4 font-semibold text-slate-900">{point.value}</td>
                        <td className="py-3 pr-4 text-slate-600">{review.canonical_unit}</td>
                        <td className="py-3 pr-4 text-slate-600">{point.assessment}</td>
                        <td className="py-3">
                          <Link className="font-semibold text-indigo-600" href={`/doctor/reports/${point.report_id}`}>
                            #{point.report_id}
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </article>
          </section>

          <aside className="doctor-report-sidebar">
            <section className="doctor-side-card">
              <h2>Thông tin yêu cầu</h2>
              <dl>
                <div>
                  <dt>Bệnh nhân</dt>
                  <dd>{detail.patient.name}</dd>
                </div>
                <div>
                  <dt>Mã bệnh nhân</dt>
                  <dd>#{detail.patient.id}</dd>
                </div>
                <div>
                  <dt>Giới tính</dt>
                  <dd>{genderText(detail.patient.gender)}</dd>
                </div>
                <div>
                  <dt>Tuổi</dt>
                  <dd>{detail.patient.age ?? "-"}</dd>
                </div>
                <div>
                  <dt>Chỉ số</dt>
                  <dd>{review.display_name}</dd>
                </div>
                <div>
                  <dt>Trạng thái</dt>
                  <dd>{statusText(review)}</dd>
                </div>
              </dl>
            </section>

            <section className="doctor-side-card">
              <h2>Nhận xét chuyên môn</h2>
              {readOnly && review.doctor_comment ? (
                <div className="doctor-question-answer">
                  <p>{review.doctor_comment}</p>
                  <span>{assessmentText(review.doctor_assessment)}</span>
                </div>
              ) : (
                <div className="doctor-question-editor">
                  <label className="finding-card__label" htmlFor="trend-review-assessment">
                    Đánh giá xu hướng
                  </label>
                  <select
                    id="trend-review-assessment"
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900"
                    value={assessment}
                    disabled={saving}
                    onChange={(event) => setAssessment(event.target.value as TrendReviewAssessment)}
                  >
                    {ASSESSMENT_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>{option.label}</option>
                    ))}
                  </select>
                  <label className="finding-card__label mt-2" htmlFor="trend-review-comment">
                    Nhận xét của bác sĩ
                  </label>
                  <textarea
                    id="trend-review-comment"
                    value={comment}
                    disabled={saving}
                    maxLength={8000}
                    onChange={(event) => setComment(event.target.value)}
                  />
                  <div className="finding-card__correction-actions">
                    <span className={comment.trim() ? "is-ready" : ""}>
                      {comment.trim() ? "Sẵn sàng gửi" : "Cần nhập nhận xét"}
                    </span>
                    <button
                      type="button"
                      className="doctor-primary-button"
                      disabled={!canSubmit}
                      onClick={() => void handleSubmit()}
                    >
                      {saving ? "Đang gửi..." : "Gửi review"}
                    </button>
                  </div>
                </div>
              )}
            </section>
          </aside>
        </div>
      </section>
    </main>
  );
}
