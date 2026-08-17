"use client";

type Props = {
  reviewed: number;
  total: number;
  busy: boolean;
  readOnly: boolean;
  onComplete: () => void;
};

export default function DoctorReviewProgressBar({ reviewed, total, busy, readOnly, onComplete }: Props) {
  if (readOnly) return null;

  const remaining = Math.max(0, total - reviewed);
  const pct = total > 0 ? Math.round((reviewed / total) * 100) : 0;

  return (
    <div className="review-progress-bar" aria-live="polite">
      <div className="review-progress-bar__left">
        <div className="review-progress-bar__track" aria-hidden="true">
          <span style={{ width: `${pct}%` }} />
        </div>
        <strong>Đã xử lý {reviewed}/{total} luận điểm</strong>
      </div>
      <div className="review-progress-bar__right">
        {remaining > 0 && <span>Còn {remaining} luận điểm chưa xử lý</span>}
        <button
          type="button"
          disabled={busy || remaining > 0}
          onClick={onComplete}
          className="doctor-primary-button"
        >
          {busy ? "Đang hoàn tất..." : "Hoàn tất kiểm chứng"}
        </button>
      </div>
    </div>
  );
}
