"use client";

import { useState } from "react";
import ImageLightbox from "@/components/common/ImageLightbox";
import { answerDoctorQuestion } from "@/lib/api";
import { formatDate, formatMoment } from "@/lib/patientUi.mjs";
import type { DoctorReportDetail } from "@/types/doctor";
import type { ReportQuestion } from "@/types/history";
import ReasonChip from "./ReasonChip";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { FileImage, Flag, MessageCircleQuestion, Save, UserRound } from "lucide-react";

type Props = {
  detail: DoctorReportDetail;
  readOnly: boolean;
  onQuestionUpdated: (question: ReportQuestion) => void;
};

function genderText(value: string | null) {
  if (value === "male") return "Nam";
  if (value === "female") return "Nữ";
  if (value === "other") return "Khác";
  return "-";
}

export default function DoctorReportSidebar({ detail, readOnly, onQuestionUpdated }: Props) {
  const [lightboxOpen, setLightboxOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<number, string>>({});
  const [editing, setEditing] = useState<Record<number, boolean>>({});
  const [busyQuestion, setBusyQuestion] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function saveAnswer(questionId: number) {
    const answer = (drafts[questionId] || "").trim();
    if (!answer) return;
    setBusyQuestion(questionId);
    setError(null);
    try {
      const updated = await answerDoctorQuestion(questionId, answer);
      onQuestionUpdated(updated);
      setEditing((current) => ({ ...current, [questionId]: false }));
      setDrafts((current) => ({ ...current, [questionId]: "" }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Không lưu được câu trả lời");
    } finally {
      setBusyQuestion(null);
    }
  }

  return (
    <aside className="doctor-report-sidebar">
      <section className="doctor-side-card">
        <h2><UserRound aria-hidden="true" /> Bệnh nhân</h2>
        <dl>
          <div><dt>Họ tên</dt><dd>{detail.patient.name}</dd></div>
          <div><dt>Tuổi</dt><dd>{detail.patient.age ?? "-"}</dd></div>
          <div><dt>Giới tính</dt><dd>{genderText(detail.patient.gender)}</dd></div>
          <div><dt>Ngày xét nghiệm</dt><dd>{formatDate(detail.report.test_date)}</dd></div>
          <div><dt>Nguồn nhập</dt><dd>{detail.report.input_method === "ocr" ? "OCR" : "Nhập tay"}</dd></div>
        </dl>
      </section>

      {detail.flags.length > 0 && (
        <section className="doctor-side-card">
          <h2><Flag aria-hidden="true" /> Lý do cần kiểm chứng</h2>
          <div className="doctor-side-flags">
            {detail.flags.map((flag, index) => (
              <ReasonChip key={`${flag.code}-${flag.finding_id ?? "report"}-${index}`} flag={flag} />
            ))}
          </div>
        </section>
      )}

      {detail.report.original_image_url && (
        <section className="doctor-side-card">
          <h2><FileImage aria-hidden="true" /> Ảnh gốc phiếu</h2>
          <button
            type="button"
            className="doctor-image-thumb"
            onClick={() => setLightboxOpen(true)}
          >
            {/* eslint-disable-next-line @next/next/no-img-element -- optional backend-provided report image preview. */}
            <img src={detail.report.original_image_url} alt="Ảnh gốc phiếu xét nghiệm" />
          </button>
          <ImageLightbox
            src={detail.report.original_image_url}
            alt="Ảnh gốc phiếu xét nghiệm"
            open={lightboxOpen}
            onClose={() => setLightboxOpen(false)}
          />
        </section>
      )}

      {detail.questions.length > 0 && (
        <section className="doctor-side-card">
          <h2><MessageCircleQuestion aria-hidden="true" /> Câu hỏi của bệnh nhân ({detail.questions.length})</h2>
          {error && <p className="doctor-side-error" role="alert">{error}</p>}
          <ul className="doctor-question-list">
            {detail.questions.map((question) => {
              const isEditing = editing[question.id] || !question.answer_text;
              return (
                <li key={question.id}>
                  <p>{question.question_text}</p>
                  {question.answer_text && !isEditing ? (
                    <div className="doctor-question-answer">
                      <p>{question.answer_text}</p>
                      <span>
                        {question.answered_by_username || "Bác sĩ"}
                        {question.answered_at ? ` · ${formatMoment(question.answered_at)}` : ""}
                      </span>
                      {!readOnly && (
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => {
                            setDrafts((current) => ({ ...current, [question.id]: question.answer_text || "" }));
                            setEditing((current) => ({ ...current, [question.id]: true }));
                          }}
                        >Sửa</Button>
                      )}
                    </div>
                  ) : (
                    !readOnly && (
                      <div className="doctor-question-editor">
                        <Textarea
                          rows={3}
                          value={drafts[question.id] ?? ""}
                          placeholder="Trả lời câu hỏi này cho bệnh nhân"
                          onChange={(event) =>
                            setDrafts((current) => ({ ...current, [question.id]: event.target.value }))
                          }
                        />
                        <Button
                          type="button"
                          disabled={busyQuestion === question.id || !(drafts[question.id] || "").trim()}
                          onClick={() => void saveAnswer(question.id)}
                        >
                          <Save data-icon="inline-start" aria-hidden="true" />
                          {busyQuestion === question.id ? "Đang lưu..." : "Lưu câu trả lời"}
                        </Button>
                      </div>
                    )
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </aside>
  );
}
