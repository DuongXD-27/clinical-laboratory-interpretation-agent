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
import { formatDate, formatMoment, formatClinicalAssessment, formatPatientDemographics, reportTone } from "@/lib/patientUi.mjs";
import { formatClinicalText, formatClinicalUnit } from "@/lib/clinicalUnit.mjs";
import type {
  DoctorTrendReviewDetail,
  TrendPoint,
  TrendReview,
  TrendReviewAssessment,
} from "@/types/analysis";
import DoctorPageHeader from "@/components/doctor/DoctorPageHeader";
import { motionElementName } from "@/lib/motion";
import DoctorSection from "@/components/doctor/DoctorSection";
import DoctorStatePanel from "@/components/doctor/DoctorStatePanel";
import StatusIndicator, { type StatusState } from "@/components/common/StatusIndicator";
import { Button } from "@/components/ui/button";
import { NativeSelect, NativeSelectOption } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { CheckCircle2, ClipboardList, FileChartColumn, LineChart, Send, Sparkles, UserRound } from "lucide-react";

const ASSESSMENT_OPTIONS: { value: TrendReviewAssessment; label: string }[] = [
  { value: "confirmed", label: "Xác nhận nhận xét AI phù hợp" },
  { value: "corrected", label: "Đính chính hoặc bổ sung nhận xét AI" },
  { value: "needs_follow_up", label: "Cần theo dõi hoặc trao đổi thêm" },
];

function statusText(review: TrendReview) {
  if (review.status === "PENDING") return "Đang chờ";
  if (review.status === "REVIEWED") return "Đã đánh giá";
  if (review.status === "CANCELLED") return "Đã huỷ";
  return "Từ chối";
}

function statusState(review: TrendReview): StatusState {
  if (review.status === "PENDING") return "pending";
  if (review.status === "REVIEWED") return "completed";
  if (review.status === "CANCELLED") return "cancelled";
  return "rejected";
}

function assessmentText(value: TrendReviewAssessment | null | undefined) {
  if (value === "confirmed") return "Bác sĩ xác nhận xu hướng";
  if (value === "corrected") return "Bác sĩ đã đính chính";
  if (value === "needs_follow_up") return "Cần theo dõi/trao đổi thêm";
  return "Đã được bác sĩ đánh giá";
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
        setError(caught instanceof Error ? caught.message : "Không mở được yêu cầu đánh giá xu hướng.");
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
      setToast("Đã lưu đánh giá xu hướng.");
    } catch (caught) {
      if (caught instanceof UnauthorizedError) {
        clearSession();
        router.replace("/");
        return;
      }
      setError(caught instanceof Error ? caught.message : "Không lưu được đánh giá xu hướng.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Đánh giá xu hướng" title="Đang tải yêu cầu…" />
        <section className="doctor-detail-skeleton" aria-label="Đang tải yêu cầu đánh giá xu hướng" role="status">
          <div className="doctor-detail-skeleton__grid">
            <div className="doctor-detail-skeleton__primary">
              <Skeleton />
              <Skeleton />
            </div>
            <Skeleton className="doctor-detail-skeleton__sidebar" />
          </div>
        </section>
      </div>
    );
  }

  if (error || !detail || !review) {
    return (
      <div className="doctor-page doctor-detail-page">
        <DoctorPageHeader eyebrow="Đánh giá xu hướng" title="Không mở được yêu cầu" />
        <DoctorStatePanel
          kind="error"
          title="Không mở được yêu cầu đánh giá xu hướng"
          description={error || "Không tìm thấy yêu cầu đánh giá xu hướng."}
          action={(
            <Button render={<Link href="/doctor/trend-reviews" transitionTypes={["nav-back"]} />} nativeButton={false} variant="outline">
              Quay lại danh sách
            </Button>
          )}
        />
      </div>
    );
  }

  const patientDemographics = formatPatientDemographics(detail.patient.gender, detail.patient.age);

  return (
    <div className="doctor-page doctor-detail-page">
      {toast && <div className="doctor-toast" role="status">{toast}</div>}
      <DoctorPageHeader
        eyebrow="ĐÁNH GIÁ XU HƯỚNG"
        title={`Đánh giá xu hướng ${review.display_name}`}
        transitionName={motionElementName("doctor-trend-review", review.id)}
        description={
          <div className="doctor-trend-hero-meta">
            <p className="doctor-trend-hero-meta__primary">
              {detail.patient.name} · {patientDemographics} · Yêu cầu #{review.id}
            </p>
            <p className="doctor-trend-hero-meta__secondary">
              Gửi lúc {formatMoment(review.requested_at)}
            </p>
          </div>
        }
        actions={<StatusIndicator state={statusState(review)} label={statusText(review)} />}
        backHref="/doctor/trend-reviews"
        backLabel="Danh sách đánh giá xu hướng"
      />

      {review.status === "REVIEWED" && (
        <div className="doctor-verified-banner">
          <CheckCircle2 aria-hidden="true" />
          Đã đánh giá bởi {review.reviewed_by_username || "bác sĩ"}
          {review.reviewed_at ? ` lúc ${formatMoment(review.reviewed_at)}` : ""}.
        </div>
      )}

      {error && <div className="doctor-error-state" role="alert">{error}</div>}

      <div className="doctor-trend-review-grid">
        <section className="doctor-trend-primary-col" aria-label="Chi tiết đánh giá xu hướng">
          <DoctorSection
            className="trend-chart-card"
            title={review.display_name}
            description={`${review.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"} · ${formatClinicalUnit(review.canonical_unit)}`}
            icon={LineChart}
            meta={<span className="doctor-section-count">{points.length} mốc</span>}
          >
            <div className="doctor-trend-chart">
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

            <div className="finding-card__ai doctor-ai-review">
              <p className="doctor-ai-label"><Sparkles aria-hidden="true" /> Nhận xét xu hướng của AI</p>
              <p className="finding-card__explanation text-[var(--foreground-secondary)] leading-relaxed">
                {formatClinicalText(review.llm_explanation_snapshot)}
              </p>
            </div>
          </DoctorSection>

          <DoctorSection
            className="trend-data-card"
            title="Dữ liệu các mốc xét nghiệm"
            description={`${points.length} mốc được ghi nhận khi bệnh nhân gửi yêu cầu.`}
            icon={FileChartColumn}
          >
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
                      <td>{formatClinicalUnit(review.canonical_unit)}</td>
                      <td>
                        <StatusIndicator
                          state={reportTone(point.assessment)}
                          label={formatClinicalAssessment(point.assessment)}
                          level="inline"
                        />
                      </td>
                      <td>
                        <Link href={`/doctor/reports/${point.report_id}`} transitionTypes={["nav-forward"]} className="doctor-table-link">
                          #{point.report_id}
                        </Link>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </DoctorSection>
        </section>

        <aside className="doctor-report-sidebar" aria-label="Thông tin bổ sung và nhận xét">
          <DoctorSection className="doctor-side-card" title="Bệnh nhân & yêu cầu" icon={UserRound}>
            <dl className="doctor-metadata-list">
              <div>
                <dt>Bệnh nhân</dt>
                <dd>{detail.patient.name}</dd>
              </div>
              <div>
                <dt>Mã bệnh nhân</dt>
                <dd>#{detail.patient.id}</dd>
              </div>
              <div>
                <dt>Giới tính / Tuổi</dt>
                <dd>{patientDemographics}</dd>
              </div>
              <div>
                <dt>Chỉ số</dt>
                <dd>{review.display_name}</dd>
              </div>
              <div>
                <dt>Phạm vi dữ liệu</dt>
                <dd>{review.trend_filter === "latest5" ? "5 kết quả gần nhất" : "3 tháng gần nhất"}</dd>
              </div>
              <div>
                <dt>Trạng thái</dt>
                <dd>{statusText(review)}</dd>
              </div>
            </dl>
          </DoctorSection>

          <DoctorSection className="doctor-side-card" title="Nhận xét chuyên môn" icon={ClipboardList}>
            {readOnly && review.doctor_comment ? (
              <div className="doctor-question-answer">
                <p className="doctor-comment-text">{formatClinicalText(review.doctor_comment)}</p>
                <span className="doctor-assessment-badge">{assessmentText(review.doctor_assessment)}</span>
              </div>
            ) : (
              <div className="doctor-question-editor">
                <div className="doctor-form-field">
                  <label className="doctor-form-label" htmlFor="trend-review-assessment">
                    Đánh giá xu hướng
                  </label>
                  <NativeSelect
                    id="trend-review-assessment"
                    className="doctor-select"
                    name="trend-review-assessment"
                    autoComplete="off"
                    value={assessment}
                    disabled={saving}
                    onChange={(event) => setAssessment(event.target.value as TrendReviewAssessment)}
                  >
                    {ASSESSMENT_OPTIONS.map((option) => (
                      <NativeSelectOption key={option.value} value={option.value}>{option.label}</NativeSelectOption>
                    ))}
                  </NativeSelect>
                </div>

                <div className="doctor-form-field">
                  <label className="doctor-form-label" htmlFor="trend-review-comment">
                    Nhận xét của bác sĩ
                  </label>
                  <Textarea
                    id="trend-review-comment"
                    name="trend-review-comment"
                    autoComplete="off"
                    value={comment}
                    disabled={saving}
                    maxLength={8000}
                    rows={5}
                    placeholder="Nhập nhận xét chuyên môn về diễn tiến chỉ số…"
                    onChange={(event) => setComment(event.target.value)}
                  />
                  {comment.trim().length === 0 ? (
                    <p className="doctor-field-hint" role="status">
                      Cần nhập nhận xét trước khi gửi đánh giá
                    </p>
                  ) : (
                    <p className="doctor-field-hint doctor-field-hint--ready" role="status">
                      Sẵn sàng gửi ({comment.trim().length} ký tự)
                    </p>
                  )}
                </div>

                <div className="doctor-form-actions">
                  <Button
                    type="button"
                    disabled={!canSubmit}
                    onClick={() => void handleSubmit()}
                  >
                    <Send data-icon="inline-start" aria-hidden="true" />
                    {saving ? "Đang gửi…" : "Gửi đánh giá"}
                  </Button>
                </div>
              </div>
            )}
          </DoctorSection>
        </aside>
      </div>
    </div>
  );
}
