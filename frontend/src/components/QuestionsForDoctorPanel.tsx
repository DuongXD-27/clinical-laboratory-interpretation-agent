"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchHistoryDetail,
  selectReportQuestions,
  UnauthorizedError,
} from "@/lib/api";
import type { ReportQuestion } from "@/types/history";
import { Check, Send } from "lucide-react";
import StatusIndicator from "@/components/common/StatusIndicator";

type Props = {
  /** Câu hỏi lấy trực tiếp từ kết quả phân tích, dùng khi phiếu không được lưu. */
  questions: string[];
  /** null với khách: không có phiếu nào để lưu lựa chọn vào. */
  reportId: number | null;
  onUnauthorized: () => void;
};

/** Màn 6 — câu hỏi gợi ý cho bác sĩ.
 *
 * Danh sách có ô tích chọn: câu hỏi không chỉ để đọc mà để bệnh nhân chọn những
 * câu mình thực sự muốn hỏi rồi mang theo.
 *
 * Bệnh nhân đăng nhập thì lựa chọn được lưu vào phiếu, nên bác sĩ mở phiếu sẽ
 * thấy đúng những thắc mắc bệnh nhân đã chuẩn bị. Khách thì chọn được trong
 * phiên nhưng không lưu ở đâu — đúng cam kết phiên khách không tạo dữ liệu.
 */
export default function QuestionsForDoctorPanel({ questions, reportId, onUnauthorized }: Props) {
  const [saved, setSaved] = useState<ReportQuestion[] | null>(null);
  const [localSelected, setLocalSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [sendNotice, setSendNotice] = useState<string | null>(null);

  const loadSaved = useCallback(async () => {
    if (reportId === null) return;
    try {
      const detail = await fetchHistoryDetail(reportId);
      setSaved(detail.questions);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      // Không chặn màn kết quả: vẫn hiển thị được câu hỏi từ response phân tích,
      // chỉ là chưa tick lưu được.
      setError(err instanceof Error ? err.message : "Chưa tải được câu hỏi đã lưu");
    }
  }, [reportId, onUnauthorized]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở panel
    void loadSaved();
  }, [loadSaved]);

  if (questions.length === 0 && (saved === null || saved.length === 0)) {
    // Toàn bộ chỉ số bình thường: một dòng là đủ. Tạo ra câu hỏi trong tình
    // huống này đi ngược mục tiêu — người có kết quả bình thường không nên rời
    // ứng dụng với cảm giác có điều gì cần lo lắng.
    return (
      <div className="questions-empty-state mt-5">
        <div className="section-heading">
          <span className="eyebrow">Câu hỏi gợi ý</span>
          <h2>Chuẩn bị cho buổi khám</h2>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Không có câu hỏi bổ sung được đề xuất cho phiếu này.
        </p>
      </div>
    );
  }

  const rows =
    saved && saved.length > 0
      ? saved.map((question) => ({
          key: question.id,
          text: question.question_text,
          checked: question.is_selected,
          answer: question.answer_text,
          answeredBy: question.answered_by_username,
        }))
      : questions.map((text, index) => ({
          key: index,
          text,
          checked: localSelected.has(index),
          answer: null as string | null,
          answeredBy: null as string | null,
        }));

  const selectedTexts = rows.filter((row) => row.checked).map((row) => row.text);

  function toggle(key: number) {
    setSendNotice(null);

    if (!saved || saved.length === 0 || reportId === null) {
      setLocalSelected((current) => {
        const next = new Set(current);
        if (next.has(key)) next.delete(key);
        else next.add(key);
        return next;
      });
      return;
    }

    const nextIds = saved
      .filter((question) => (question.id === key ? !question.is_selected : question.is_selected))
      .map((question) => question.id);

    setBusy(true);
    setError(null);
    void (async () => {
      try {
        setSaved(await selectReportQuestions(reportId, nextIds));
      } catch (err) {
        if (err instanceof UnauthorizedError) {
          onUnauthorized();
          return;
        }
        setError(err instanceof Error ? err.message : "Không lưu được lựa chọn");
      } finally {
        setBusy(false);
      }
    })();
  }

  return (
    <div className="patient-card mt-5 p-5 sm:p-7">
      <div className="section-heading">
        <span className="eyebrow">Câu hỏi gợi ý</span>
        <h2>Câu hỏi mang đi hỏi bác sĩ</h2>
        <p>
          Chọn những câu bạn thực sự muốn hỏi rồi mang theo khi đi khám. Đây là gợi ý, không phải
          những điều bắt buộc phải hỏi.
        </p>
      </div>

      {error && (
        <p role="alert" className="mt-3 text-sm text-[var(--status-critical-fg)]">
          {error}
        </p>
      )}

      <ul className="mt-4 grid gap-2.5">
        {rows.map((row) => (
          <li key={row.key} className={`doctor-question-row ${row.checked ? "is-selected" : ""}`}>
            <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-foreground">
              <input
                type="checkbox"
                className="sr-only"
                checked={row.checked}
                disabled={busy}
                onChange={() => toggle(row.key)}
              />
              <span className="doctor-question-check" aria-hidden="true">{row.checked ? <Check /> : null}</span>
              <span className="min-w-0 flex-1">{row.text}</span>
            </label>

            {row.answer && (
              // Câu trả lời do bác sĩ viết — tách bạch và không dán khuyến cáo
              // tự động, vì đây là ý kiến chuyên môn của người có thẩm quyền.
              <div className="status-review-note mt-3">
                <StatusIndicator state="answered" />
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{row.answer}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Bác sĩ {row.answeredBy || ""} trả lời
                </p>
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="mt-5 flex flex-col items-start gap-3 sm:flex-row sm:items-center">
        <button
          type="button"
          onClick={() => setSendNotice(
            reportId === null
              ? "Phiên dùng thử chưa có phiếu được lưu, vì vậy hệ thống chưa thể chuyển lựa chọn này cho bác sĩ."
              : "Các câu đã chọn được lưu cùng phiếu để bác sĩ xem khi mở hồ sơ. Hệ thống không gửi tin nhắn trực tiếp.",
          )}
          disabled={selectedTexts.length === 0 || busy}
          className="primary-button doctor-question-cta"
        >
          <Send aria-hidden="true" />
          Gửi câu hỏi đến bác sĩ
        </button>
        <span className="text-xs text-muted-foreground">Đã chọn {selectedTexts.length} câu</span>
      </div>

      {sendNotice && <p className="doctor-question-notice" role="status">{sendNotice}</p>}

      {reportId === null && (
        <p className="mt-3 text-xs text-slate-500">
          Bạn đang dùng thử với tư cách khách nên lựa chọn này chỉ được giữ trong phiên hiện tại.
        </p>
      )}
    </div>
  );
}
