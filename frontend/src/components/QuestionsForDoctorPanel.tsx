"use client";

import { useCallback, useEffect, useState } from "react";
import {
  fetchHistoryDetail,
  selectReportQuestions,
  UnauthorizedError,
} from "@/lib/api";
import type { ReportQuestion } from "@/types/history";

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
 * câu mình thực sự muốn hỏi rồi mang theo. Chức năng sao chép chỉ áp dụng cho
 * các câu đã chọn.
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
  const [copied, setCopied] = useState(false);

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
      <div className="patient-card mt-5 p-5 sm:p-7">
        <div className="section-heading">
          <span className="eyebrow">Câu hỏi gợi ý</span>
          <h2>Chuẩn bị cho buổi khám</h2>
        </div>
        <p className="mt-3 text-sm leading-6 text-slate-600">
          Lần này không có chỉ số nào cần hỏi thêm.
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
    setCopied(false);

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

  async function copySelected() {
    if (selectedTexts.length === 0) return;

    const text = selectedTexts.map((line, index) => `${index + 1}. ${line}`).join("\n");

    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
    } catch {
      setError("Trình duyệt không cho phép sao chép. Bạn có thể chọn và copy tay.");
    }
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
        <p role="alert" className="mt-3 text-sm text-red-600">
          {error}
        </p>
      )}

      <ul className="mt-4 grid gap-2">
        {rows.map((row) => (
          <li key={row.key} className="rounded-xl border border-slate-200 p-3">
            <label className="flex cursor-pointer items-start gap-3 text-sm leading-6 text-slate-700">
              <input
                type="checkbox"
                className="mt-1.5"
                checked={row.checked}
                disabled={busy}
                onChange={() => toggle(row.key)}
              />
              <span>{row.text}</span>
            </label>

            {row.answer && (
              // Câu trả lời do bác sĩ viết — tách bạch và không dán khuyến cáo
              // tự động, vì đây là ý kiến chuyên môn của người có thẩm quyền.
              <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/60 p-3">
                <p className="whitespace-pre-wrap text-sm leading-6 text-slate-800">{row.answer}</p>
                <p className="mt-2 text-xs text-slate-500">
                  Bác sĩ {row.answeredBy || ""} trả lời
                </p>
              </div>
            )}
          </li>
        ))}
      </ul>

      <div className="mt-4 flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => void copySelected()}
          disabled={selectedTexts.length === 0}
          className="h-10 rounded-lg border border-slate-300 px-4 text-sm font-medium disabled:opacity-50"
        >
          Sao chép {selectedTexts.length > 0 ? `${selectedTexts.length} câu đã chọn` : "câu đã chọn"}
        </button>
        <button
          type="button"
          onClick={() => window.print()}
          disabled={selectedTexts.length === 0}
          className="h-10 rounded-lg border border-slate-300 px-4 text-sm font-medium disabled:opacity-50"
        >
          In
        </button>
        {copied && <span className="text-sm text-emerald-700">Đã sao chép vào clipboard.</span>}
      </div>

      {reportId === null && (
        <p className="mt-3 text-xs text-slate-500">
          Bạn đang dùng thử với tư cách khách nên lựa chọn này không được lưu lại. Đăng ký tài khoản
          để bác sĩ thấy được những câu bạn đã chọn.
        </p>
      )}
    </div>
  );
}
