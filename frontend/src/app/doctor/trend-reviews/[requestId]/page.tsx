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
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import ClinicalStatusChip, { type ClinicalStatusTone } from "@/components/common/ClinicalStatusChip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, LineChart, Send, Sparkles } from "lucide-react";

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

function statusTone(review: TrendReview): ClinicalStatusTone {
  if (review.status === "PENDING") return "pending";
  if (review.status === "REVIEWED") return "verified";
  return "neutral";
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
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Review xu hướng" title="Đang tải yêu cầu" />
        <section className="doctor-detail-skeleton" aria-label="Đang tải yêu cầu review xu hướng">
          <div className="skeleton-card" />
          <div className="skeleton-card" />
        </section>
      </div>
    );
  }

  if (error || !detail || !review) {
    return (
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Review xu hướng" title="Không mở được yêu cầu" />
        <section className="doctor-state-card doctor-state-card--error">
          <div className="doctor-error-state" role="alert">
            <p>{error || "Không tìm thấy yêu cầu review xu hướng."}</p>
            <Link href="/doctor/trend-reviews">Quay lại danh sách</Link>
          </div>
        </section>
      </div>
    );
  }

  return (
    <div className="doctor-page doctor-detail-page">
      {toast && <div className="doctor-toast" role="status">{toast}</div>}
      <DoctorPageHeader
        eyebrow={`Review xu hướng · Yêu cầu #${review.id}`}
        title={detail.patient.name}
        description={`${genderText(detail.patient.gender)} · ${detail.patient.age ?? "-"} tuổi · ${review.display_name}`}
        actions={<ClinicalStatusChip tone={statusTone(review)}>{statusText(review)}</ClinicalStatusChip>}
        backHref="/doctor/trend-reviews"
        backLabel="Danh sách review xu hướng"
      />

      {review.status === "REVIEWED" && (
        <div className="doctor-verified-banner">
          <CheckCircle2 aria-hidden="true" />
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
                  <h2><LineChart aria-hidden="true" /> {review.display_name}</h2>
                  <p className="finding-card__ref">
                    {review.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"} · {review.canonical_unit}
                  </p>
                </div>
                <span className="doctor-card-meta">
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
                <p className="finding-card__label"><Sparkles aria-hidden="true" /> Nhận xét xu hướng của AI</p>
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
              <div className="doctor-table-wrap">
                <table className="doctor-data-table">
                  <thead>
                    <tr>
                      <th>Ngày xét nghiệm</th>
                      <th>Giá trị</th>
                      <th>Đơn vị</th>
                      <th>Đánh giá</th>
                      <th>Phiếu</th>
                    </tr>
                  </thead>
                  <tbody>
                    {points.map((point: TrendPoint) => (
                      <tr key={`${point.report_id}-${point.test_date}`}>
                        <td>{formatDate(point.test_date)}</td>
                        <td><strong>{point.value}</strong></td>
                        <td>{review.canonical_unit}</td>
                        <td>{point.assessment}</td>
                        <td>
                          <Link href={`/doctor/reports/${point.report_id}`}>
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
                    className="doctor-select"
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
                  <Textarea
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
                    <Button
                      type="button"
                      disabled={!canSubmit}
                      onClick={() => void handleSubmit()}
                    >
                      <Send data-icon="inline-start" aria-hidden="true" />
                      {saving ? "Đang gửi..." : "Gửi review"}
                    </Button>
                  </div>
                </div>
              )}
            </section>
          </aside>
      </div>
    </div>
  );
}
