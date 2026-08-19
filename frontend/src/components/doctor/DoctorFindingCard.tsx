"use client";

import { useEffect, useRef, useState } from "react";
import DoctorNoteBlock from "@/components/common/DoctorNoteBlock";
import SeverityBadge from "@/components/common/SeverityBadge";
import { formatMoment } from "@/lib/patientUi.mjs";
import type { DoctorFinding, ReviewFlag } from "@/types/doctor";

type Props = {
  finding: DoctorFinding;
  flags: ReviewFlag[];
  readOnly: boolean;
  onReview: (findingId: number, outcome: "agreed" | "corrected" | "skipped", note?: string) => Promise<void>;
};

function outcomeText(outcome: DoctorFinding["review_outcome"]) {
  if (outcome === "agreed") return "Đã đồng ý với giải thích của AI";
  if (outcome === "corrected") return "Đã đính chính";
  if (outcome === "skipped") return "Đã bỏ qua";
  return "";
}

export default function DoctorFindingCard({ finding, flags, readOnly, onReview }: Props) {
  const [editing, setEditing] = useState(false);
  const [note, setNote] = useState(finding.doctor_note ?? "");
  const [saving, setSaving] = useState<"agreed" | "corrected" | "skipped" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const isReviewed = finding.review_outcome !== "pending";

  useEffect(() => {
    if (editing) textareaRef.current?.focus();
  }, [editing]);

  async function save(outcome: "agreed" | "corrected" | "skipped", draft?: string) {
    setSaving(outcome);
    setError(null);
    try {
      await onReview(finding.id, outcome, draft);
      setEditing(false);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không lưu được luận điểm này");
    } finally {
      setSaving(null);
    }
  }

  return (
    <article
      className={`finding-card finding-card--${finding.classification}${flags.length > 0 ? " finding-card--flagged" : ""}${isReviewed ? " finding-card--reviewed" : ""}`}
    >
      <div className="finding-card__header">
        <div>
          <h2>{finding.metric_name}</h2>
          <p className="finding-card__value">
            {finding.value} <span>{finding.unit}</span>
          </p>
          <p className="finding-card__ref">Tham chiếu: {finding.reference_range}</p>
        </div>
        <SeverityBadge level={finding.classification} />
      </div>

      {flags.length > 0 && (
        <div className="finding-card__flags" role="status">
          {flags.map((flag, index) => (
            <span key={`${flag.code}-${index}`}>⚠ {flag.detail}</span>
          ))}
        </div>
      )}

      <div className="finding-card__ai">
        <p className="finding-card__label">Giải thích của AI</p>
        <p>{finding.ai_text}</p>
      </div>

      {finding.review_outcome === "corrected" && finding.doctor_note && (
        <DoctorNoteBlock
          note={finding.doctor_note}
          doctorName={finding.reviewed_by}
          reviewedAt={finding.reviewed_at}
        />
      )}

      {isReviewed && !editing && (
        <div className={`finding-card__outcome finding-card__outcome--${finding.review_outcome}`}>
          <span>{finding.review_outcome === "skipped" ? "−" : "✓"}</span>
          <span>
            {outcomeText(finding.review_outcome)}
            {finding.reviewed_by ? ` · ${finding.reviewed_by}` : ""}
            {finding.reviewed_at ? ` · ${formatMoment(finding.reviewed_at)}` : ""}
          </span>
          {!readOnly && (
            <button type="button" onClick={() => setEditing(true)}>
              Sửa lại
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="finding-card__error" role="alert">
          {error}
          <button type="button" onClick={() => setError(null)}>Đóng</button>
        </div>
      )}

      {!readOnly && (!isReviewed || editing) && (
        editing ? (
          <div className="finding-card__correction">
            <textarea
              ref={textareaRef}
              value={note}
              minLength={10}
              maxLength={4000}
              placeholder="Nội dung đính chính cho bệnh nhân..."
              onChange={(event) => setNote(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Escape") setEditing(false);
                if ((event.ctrlKey || event.metaKey) && event.key === "Enter" && note.trim().length >= 10) {
                  void save("corrected", note.trim());
                }
              }}
            />
            <div className="finding-card__correction-actions">
              <span className={note.trim().length >= 10 ? "is-ready" : ""}>
                {note.trim().length} / tối thiểu 10
              </span>
              <button
                type="button"
                disabled={saving !== null || note.trim().length < 10}
                onClick={() => void save("corrected", note.trim())}
                className="doctor-primary-button"
              >
                {saving === "corrected" ? "Đang lưu..." : "Lưu"}
              </button>
              <button type="button" disabled={saving !== null} onClick={() => setEditing(false)}>
                Huỷ
              </button>
            </div>
          </div>
        ) : (
          <div className="finding-card__actions">
            <button
              type="button"
              disabled={saving !== null}
              onClick={() => void save("agreed")}
              className="doctor-primary-button"
            >
              {saving === "agreed" ? "Đang lưu..." : "Đồng ý"}
            </button>
            <button type="button" disabled={saving !== null} onClick={() => setEditing(true)}>
              Đính chính
            </button>
            <button type="button" disabled={saving !== null} onClick={() => void save("skipped")}>
              {saving === "skipped" ? "Đang lưu..." : "Bỏ qua"}
            </button>
          </div>
        )
      )}
    </article>
  );
}
