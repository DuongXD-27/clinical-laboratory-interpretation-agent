"use client";

import { useEffect, useRef, useState } from "react";
import DoctorNoteBlock from "@/components/common/DoctorNoteBlock";
import SeverityBadge from "@/components/common/SeverityBadge";
import { formatMoment } from "@/lib/patientUi.mjs";
import type { DoctorFinding, ReviewFlag } from "@/types/doctor";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Check, CircleMinus, PencilLine, Sparkles } from "lucide-react";
import ClinicalStatusChip from "@/components/common/ClinicalStatusChip";
import ReasonChip from "./ReasonChip";

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
        <div className="finding-card__metric">
          <h2>{finding.metric_name}</h2>
          <div className="finding-card__measurement">
            <p className="finding-card__value">{finding.value}</p>
            <span>{finding.unit}</span>
          </div>
          <p className="finding-card__ref"><span>Khoảng tham chiếu</span> {finding.reference_range}</p>
        </div>
        <SeverityBadge level={finding.classification} />
      </div>

      {flags.length > 0 && (
        <div className="finding-card__flags" role="status">
          {flags.map((flag, index) => (
            <ReasonChip key={`${flag.code}-${index}`} flag={flag} />
          ))}
        </div>
      )}

      <div className="finding-card__ai">
        <p className="finding-card__label"><Sparkles aria-hidden="true" /> Giải thích của AI</p>
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
          <ClinicalStatusChip
            tone={finding.review_outcome === "skipped" ? "neutral" : "verified"}
            icon={finding.review_outcome === "skipped" ? CircleMinus : Check}
          >
            {outcomeText(finding.review_outcome)}
          </ClinicalStatusChip>
          <span>
            {finding.reviewed_by ? ` · ${finding.reviewed_by}` : ""}
            {finding.reviewed_at ? ` · ${formatMoment(finding.reviewed_at)}` : ""}
          </span>
          {!readOnly && (
            <Button type="button" variant="ghost" size="sm" onClick={() => setEditing(true)}>
              <PencilLine data-icon="inline-start" aria-hidden="true" /> Sửa lại
            </Button>
          )}
        </div>
      )}

      {error && (
        <div className="finding-card__error" role="alert">
          {error}
          <Button type="button" variant="ghost" size="xs" onClick={() => setError(null)}>Đóng</Button>
        </div>
      )}

      {!readOnly && (!isReviewed || editing) && (
        editing ? (
          <div className="finding-card__correction">
            <Textarea
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
              <Button
                type="button"
                disabled={saving !== null || note.trim().length < 10}
                onClick={() => void save("corrected", note.trim())}
              >
                {saving === "corrected" ? "Đang lưu..." : "Lưu"}
              </Button>
              <Button type="button" variant="ghost" disabled={saving !== null} onClick={() => setEditing(false)}>
                Huỷ
              </Button>
            </div>
          </div>
        ) : (
          <div className="finding-card__actions">
            <Button
              type="button"
              disabled={saving !== null}
              onClick={() => void save("agreed")}
            >
              <Check data-icon="inline-start" aria-hidden="true" />
              {saving === "agreed" ? "Đang lưu..." : "Đồng ý"}
            </Button>
            <Button type="button" variant="outline" disabled={saving !== null} onClick={() => setEditing(true)}>
              <PencilLine data-icon="inline-start" aria-hidden="true" /> Đính chính
            </Button>
            <Button type="button" variant="ghost" disabled={saving !== null} onClick={() => void save("skipped")}>
              <CircleMinus data-icon="inline-start" aria-hidden="true" />
              {saving === "skipped" ? "Đang lưu..." : "Bỏ qua"}
            </Button>
          </div>
        )
      )}
    </article>
  );
}
