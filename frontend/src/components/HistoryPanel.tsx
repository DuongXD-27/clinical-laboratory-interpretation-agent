"use client";

import { useCallback, useEffect, useState } from "react";
import {
  answerReportQuestion,
  createDoctorNote,
  fetchHistory,
  fetchHistoryDetail,
  markReportReviewed,
  selectReportQuestions,
  UnauthorizedError,
} from "@/lib/api";
import type { LabReportDetail, LabReportSummary } from "@/types/history";

type Props = {
  /** "patient" chỉ xem của mình; "doctor" tra được theo tên bệnh nhân. */
  mode: "patient" | "doctor";
  accent?: "blue" | "indigo";
  /** Đổi giá trị này để buộc nạp lại danh sách (vd. vừa lưu một phiếu mới). */
  refreshToken?: number;
  onUnauthorized: () => void;
};

const ACCENT = {
  blue: { button: "bg-blue-600 hover:bg-blue-700", text: "text-blue-600 dark:text-blue-400" },
  indigo: { button: "bg-indigo-600 hover:bg-indigo-700", text: "text-indigo-600 dark:text-indigo-400" },
};

function formatDate(value: string) {
  // Ngày xét nghiệm là chuỗi YYYY-MM-DD; tách tay thay vì new Date() để không
  // bị lệch một ngày do trình duyệt quy về UTC.
  const [year, month, day] = value.split("-");
  return day && month && year ? `${day}/${month}/${year}` : value;
}

function formatMoment(value: string) {
  // created_at là ISO có giờ, hiển thị theo múi giờ máy người dùng.
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString("vi-VN");
}

/** Nhãn trạng thái phiếu cho cả hai phía.
 *
 * Hai trạng thái tách biệt vì chúng trả lời hai câu hỏi khác nhau. "Đã có ai xem
 * phiếu của tôi chưa" thường quan trọng hơn cả nội dung nhận xét.
 */
function reviewBadge(item: { reviewed_by_doctor: boolean; has_doctor_notes: boolean }) {
  if (item.has_doctor_notes) {
    return {
      label: "Đã có ý kiến bác sĩ",
      className:
        "bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400",
    };
  }
  if (item.reviewed_by_doctor) {
    return {
      label: "Bác sĩ đã xem",
      className: "bg-sky-100 text-sky-700 dark:bg-sky-900/30 dark:text-sky-400",
    };
  }
  return {
    label: "Chưa có bác sĩ xem",
    className: "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-400",
  };
}

export default function HistoryPanel({ mode, accent = "blue", refreshToken = 0, onUnauthorized }: Props) {
  const theme = ACCENT[accent];

  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [patientUsername, setPatientUsername] = useState("");

  const [items, setItems] = useState<LabReportSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [detail, setDetail] = useState<LabReportDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);

  // Ô nhập ghi chú/câu trả lời của bác sĩ, và trạng thái đang gửi.
  const [noteDraft, setNoteDraft] = useState("");
  const [answerDrafts, setAnswerDrafts] = useState<Record<number, string>>({});
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistory({
        from: fromDate || undefined,
        to: toDate || undefined,
        patientUsername: mode === "doctor" ? patientUsername.trim() || undefined : undefined,
      });
      setItems(data.items);
      setTotal(data.total);
      setExpandedId(null);
      setDetail(null);
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setItems([]);
      setTotal(0);
      setError(err instanceof Error ? err.message : "Không tải được lịch sử");
    } finally {
      setLoading(false);
    }
  }, [fromDate, toDate, patientUsername, mode, onUnauthorized]);

  useEffect(() => {
    // Nạp lần đầu và mỗi khi có phiếu mới được lưu.
    //
    // Cố tình KHÔNG phụ thuộc `load`: nó đổi identity theo từng ký tự gõ vào ô
    // lọc, đưa vào deps sẽ thành gọi API liên tục. Việc lọc do người dùng bấm
    // nút. `load` cũng đặt state ngay (cờ loading) — đây là fetch lúc mở panel,
    // không phải đồng bộ state với state khác.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở panel, không phải đồng bộ state
    void load();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- xem giải thích ở trên
  }, [refreshToken]);

  /** Cập nhật một dòng trong danh sách để nhãn trạng thái khớp ngay, không phải lọc lại. */
  function syncSummary(updated: LabReportDetail) {
    setItems((current) =>
      current.map((item) =>
        item.id === updated.id
          ? {
              ...item,
              reviewed_by_doctor: updated.reviewed_by_doctor,
              has_doctor_notes: updated.has_doctor_notes,
            }
          : item,
      ),
    );
  }

  async function toggleDetail(reportId: number) {
    if (expandedId === reportId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }

    setExpandedId(reportId);
    setDetail(null);
    setNoteDraft("");
    setAnswerDrafts({});
    setActionError(null);
    setDetailLoading(true);
    try {
      setDetail(await fetchHistoryDetail(reportId));
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setError(err instanceof Error ? err.message : "Không mở được phiếu");
      setExpandedId(null);
    } finally {
      setDetailLoading(false);
    }
  }

  async function runAction(action: () => Promise<void>) {
    setBusy(true);
    setActionError(null);
    try {
      await action();
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        onUnauthorized();
        return;
      }
      setActionError(err instanceof Error ? err.message : "Không thực hiện được");
    } finally {
      setBusy(false);
    }
  }

  async function reloadDetail(reportId: number) {
    const fresh = await fetchHistoryDetail(reportId);
    setDetail(fresh);
    syncSummary(fresh);
  }

  function toggleQuestion(reportId: number, questionId: number) {
    if (!detail) return;

    const nextIds = detail.questions
      .filter((question) =>
        question.id === questionId ? !question.is_selected : question.is_selected,
      )
      .map((question) => question.id);

    void runAction(async () => {
      const updated = await selectReportQuestions(reportId, nextIds);
      setDetail({ ...detail, questions: updated });
    });
  }

  function saveNote(reportId: number) {
    const text = noteDraft.trim();
    if (!text) return;

    void runAction(async () => {
      await createDoctorNote(reportId, text);
      setNoteDraft("");
      await reloadDetail(reportId);
    });
  }

  function saveAnswer(reportId: number, questionId: number) {
    const text = (answerDrafts[questionId] || "").trim();
    if (!text) return;

    void runAction(async () => {
      await answerReportQuestion(reportId, questionId, text);
      setAnswerDrafts((current) => ({ ...current, [questionId]: "" }));
      await reloadDetail(reportId);
    });
  }

  function markReviewed(reportId: number) {
    void runAction(async () => {
      const updated = await markReportReviewed(reportId);
      setDetail(updated);
      syncSummary(updated);
    });
  }

  return (
    <section className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden">
      <div className="p-6 border-b border-zinc-100 dark:border-zinc-800">
        <h2 className="font-semibold text-lg">
          {mode === "doctor" ? "Lịch sử xét nghiệm của bệnh nhân" : "Lịch sử xét nghiệm của tôi"}
        </h2>
        <p className="text-sm text-zinc-500 mt-1">
          {mode === "doctor"
            ? "Mở một phiếu để đọc kết quả, xem câu hỏi bệnh nhân đã chọn và ghi nhận xét."
            : "Mỗi lần bạn phân tích một phiếu, kết quả được lưu lại ở đây."}
        </p>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {mode === "doctor" && (
            <label className="text-sm space-y-1">
              <span className="font-medium">Tên bệnh nhân</span>
              <input
                aria-label="Tên đăng nhập của bệnh nhân"
                value={patientUsername}
                onChange={(event) => setPatientUsername(event.target.value)}
                placeholder="Tất cả bệnh nhân"
                className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
              />
            </label>
          )}
          <label className="text-sm space-y-1">
            <span className="font-medium">Từ ngày</span>
            <input
              aria-label="Lọc lịch sử từ ngày"
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
            />
          </label>
          <label className="text-sm space-y-1">
            <span className="font-medium">Đến ngày</span>
            <input
              aria-label="Lọc lịch sử đến ngày"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="w-full border rounded-lg px-3 py-2 dark:bg-zinc-950 dark:border-zinc-700"
            />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={() => void load()}
              disabled={loading}
              className={`flex-1 h-10 rounded-lg text-sm font-medium text-white disabled:opacity-50 ${theme.button}`}
            >
              {loading ? "Đang tải..." : "Lọc"}
            </button>
            {(fromDate || toDate || patientUsername) && (
              <button
                type="button"
                onClick={() => {
                  setFromDate("");
                  setToDate("");
                  setPatientUsername("");
                }}
                className="h-10 px-3 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm"
              >
                Xoá lọc
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="px-6 py-4 bg-red-50 dark:bg-red-950/30 text-red-600 dark:text-red-400 text-sm">
          {error}
        </div>
      )}

      {!error && items.length === 0 && !loading && (
        <p className="px-6 py-8 text-sm text-zinc-500 text-center">
          Chưa có phiếu xét nghiệm nào trong khoảng đã chọn.
        </p>
      )}

      {items.length > 0 && (
        <>
          <p className="px-6 pt-4 text-xs text-zinc-500">
            {total} phiếu {fromDate || toDate ? "trong khoảng đã chọn" : "đã lưu"}
          </p>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {items.map((item) => {
              const badge = reviewBadge(item);

              return (
                <li key={item.id}>
                  <button
                    type="button"
                    onClick={() => void toggleDetail(item.id)}
                    className="w-full text-left px-6 py-4 hover:bg-zinc-50 dark:hover:bg-zinc-800/40 transition-colors"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="font-medium">
                          Phiếu ngày {formatDate(item.test_date)}
                          {mode === "doctor" && (
                            <span className="ml-2 text-sm font-normal text-zinc-500">
                              — {item.patient_username}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-zinc-500 mt-1">
                          {item.indicator_count} chỉ số · {item.abnormal_count} bất thường ·{" "}
                          {item.source === "ocr" ? "nhập từ ảnh" : "nhập tay"}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        {item.has_critical_values && (
                          <span className="px-2.5 py-1 rounded-md bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-400 text-xs font-semibold uppercase tracking-wide">
                            Nguy kịch
                          </span>
                        )}
                        <span className={`px-2.5 py-1 rounded-md text-xs font-medium ${badge.className}`}>
                          {badge.label}
                        </span>
                        <span className={`text-xs font-medium ${theme.text}`}>
                          {expandedId === item.id ? "Thu gọn" : "Xem chi tiết"}
                        </span>
                      </div>
                    </div>
                  </button>

                  {expandedId === item.id && (
                    <div className="px-6 pb-5 bg-zinc-50/60 dark:bg-zinc-950/40">
                      {detailLoading && <p className="py-4 text-sm text-zinc-500">Đang mở phiếu...</p>}

                      {actionError && (
                        <p className="mt-4 text-sm text-red-600 dark:text-red-400">{actionError}</p>
                      )}

                      {detail && (
                        <div className="space-y-5 pt-4">
                          <p className="text-xs text-zinc-500">
                            {detail.patient_age_at_test ?? "-"} tuổi ·{" "}
                            {detail.patient_gender_at_test === "male"
                              ? "Nam"
                              : detail.patient_gender_at_test === "female"
                                ? "Nữ"
                                : "Khác"}
                          </p>

                          {/* ---- Khối 1: nội dung do hệ thống sinh ---- */}
                          <div className="space-y-3">
                            {detail.indicators.map((indicator, index) => (
                              <div
                                key={index}
                                className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="font-medium">{indicator.name}</span>
                                  <span className="text-sm">
                                    <strong>{indicator.value}</strong>{" "}
                                    <span className="text-zinc-500">{indicator.unit}</span>
                                  </span>
                                </div>
                                <div className="text-xs text-zinc-500 mt-1">
                                  Khoảng tham chiếu: {indicator.reference_low ?? "-"} –{" "}
                                  {indicator.reference_high ?? "-"} · {indicator.status}
                                </div>
                                {indicator.explanation && (
                                  <p className="text-sm text-zinc-700 dark:text-zinc-300 mt-2 leading-relaxed">
                                    {indicator.explanation}
                                  </p>
                                )}
                              </div>
                            ))}

                            {detail.disclaimer && (
                              <p className="text-xs text-zinc-500 italic">{detail.disclaimer}</p>
                            )}
                          </div>

                          {/* ---- Khối 2: ghi chú của bác sĩ ----
                              Tách bạch khỏi khối trên vì đây là ranh giới trách
                              nhiệm thật: phần hệ thống luôn kèm khuyến cáo
                              "không chẩn đoán", phần bác sĩ thì ngược lại, có
                              thể chứa đúng thứ hệ thống bị cấm. Trộn hai nguồn
                              vào một khối thì bệnh nhân không biết ai đang nói
                              với mình. */}
                          <div className="rounded-xl border-2 border-emerald-200 dark:border-emerald-900/60 bg-emerald-50/50 dark:bg-emerald-950/20 p-4">
                            <h3 className="font-semibold text-sm text-emerald-900 dark:text-emerald-300">
                              Ghi chú của bác sĩ
                            </h3>

                            {detail.doctor_notes.length === 0 ? (
                              <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-2">
                                {detail.reviewed_by_doctor
                                  ? "Bác sĩ đã xem phiếu này và chưa có nhận xét thêm."
                                  : "Chưa có bác sĩ nào ghi nhận xét cho phiếu này."}
                              </p>
                            ) : (
                              <ul className="mt-3 space-y-3">
                                {detail.doctor_notes.map((note) => (
                                  <li
                                    key={note.id}
                                    className="rounded-lg bg-white dark:bg-zinc-900 border border-emerald-200 dark:border-emerald-900/60 p-3"
                                  >
                                    <p className="text-sm text-zinc-800 dark:text-zinc-200 whitespace-pre-wrap leading-relaxed">
                                      {note.note_text}
                                    </p>
                                    <p className="text-xs text-zinc-500 mt-2">
                                      {note.doctor_username || "Bác sĩ"} ·{" "}
                                      {formatMoment(note.created_at)}
                                    </p>
                                  </li>
                                ))}
                              </ul>
                            )}

                            {detail.doctor_notes.length > 0 && (
                              // Khuyến cáo "đây không phải chẩn đoán y khoa" cố
                              // tình KHÔNG dán vào khối này. Thay vào đó là một
                              // dòng minh bạch trách nhiệm: nếu ghi chú có sai
                              // sót, ranh giới giữa lỗi hệ thống và lỗi bác sĩ
                              // phải rõ.
                              <p className="text-xs text-emerald-800/80 dark:text-emerald-400/80 mt-3">
                                Nội dung trong khối này do bác sĩ trực tiếp viết và tự chịu trách
                                nhiệm, không do hệ thống sinh ra và không qua bộ kiểm duyệt nội dung
                                tự động.
                              </p>
                            )}

                            {detail.doctor_views.length > 0 && (
                              <p className="text-xs text-zinc-500 mt-2">
                                Đã xem:{" "}
                                {detail.doctor_views
                                  .map(
                                    (view) =>
                                      `${view.doctor_username || "bác sĩ"} (${formatMoment(view.viewed_at)})`,
                                  )
                                  .join(", ")}
                              </p>
                            )}

                            {mode === "doctor" && (
                              <div className="mt-4 space-y-2">
                                <textarea
                                  aria-label="Ghi chú lâm sàng cho phiếu này"
                                  value={noteDraft}
                                  onChange={(event) => setNoteDraft(event.target.value)}
                                  rows={3}
                                  maxLength={4000}
                                  placeholder="Nhận xét của bạn về phiếu này. Ô này bắt đầu trống và hệ thống không gợi ý nội dung."
                                  className="w-full border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700"
                                />
                                <div className="flex flex-wrap gap-2">
                                  <button
                                    type="button"
                                    onClick={() => saveNote(item.id)}
                                    disabled={busy || !noteDraft.trim()}
                                    className="h-9 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-medium disabled:opacity-50"
                                  >
                                    Lưu ghi chú
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => markReviewed(item.id)}
                                    disabled={busy}
                                    className="h-9 px-4 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm disabled:opacity-50"
                                  >
                                    Đánh dấu đã xem
                                  </button>
                                </div>
                                <p className="text-xs text-zinc-500">
                                  Ghi chú chỉ thêm mới, không sửa và không xoá. Muốn đính chính thì
                                  viết ghi chú mới.
                                </p>
                              </div>
                            )}
                          </div>

                          {/* ---- Khối 3: câu hỏi gợi ý ---- */}
                          {detail.questions.length > 0 && (
                            <div className="rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 p-4">
                              <h3 className="font-semibold text-sm">
                                {mode === "doctor"
                                  ? "Câu hỏi bệnh nhân đã chọn"
                                  : "Câu hỏi gợi ý mang đi khám"}
                              </h3>

                              <ul className="mt-3 space-y-3">
                                {detail.questions
                                  .filter((question) => mode === "patient" || question.is_selected)
                                  .map((question) => (
                                    <li
                                      key={question.id}
                                      className="rounded-lg border border-zinc-200 dark:border-zinc-800 p-3"
                                    >
                                      {mode === "patient" ? (
                                        <label className="flex gap-3 items-start text-sm cursor-pointer">
                                          <input
                                            type="checkbox"
                                            className="mt-1"
                                            checked={question.is_selected}
                                            disabled={busy}
                                            onChange={() => toggleQuestion(item.id, question.id)}
                                          />
                                          <span>{question.question_text}</span>
                                        </label>
                                      ) : (
                                        <p className="text-sm">{question.question_text}</p>
                                      )}

                                      {question.answer_text ? (
                                        <div className="mt-3 rounded-lg bg-emerald-50/60 dark:bg-emerald-950/20 border border-emerald-200 dark:border-emerald-900/60 p-3">
                                          <p className="text-sm whitespace-pre-wrap">
                                            {question.answer_text}
                                          </p>
                                          <p className="text-xs text-zinc-500 mt-2">
                                            Bác sĩ {question.answered_by_username || ""} trả lời
                                            {question.answered_at
                                              ? ` · ${formatMoment(question.answered_at)}`
                                              : ""}
                                          </p>
                                        </div>
                                      ) : (
                                        mode === "doctor" && (
                                          <div className="mt-3 space-y-2">
                                            <textarea
                                              aria-label="Trả lời câu hỏi này"
                                              rows={2}
                                              maxLength={4000}
                                              value={answerDrafts[question.id] || ""}
                                              onChange={(event) =>
                                                setAnswerDrafts((current) => ({
                                                  ...current,
                                                  [question.id]: event.target.value,
                                                }))
                                              }
                                              placeholder="Trả lời câu hỏi này cho bệnh nhân"
                                              className="w-full border rounded-lg px-3 py-2 text-sm dark:bg-zinc-950 dark:border-zinc-700"
                                            />
                                            <button
                                              type="button"
                                              onClick={() => saveAnswer(item.id, question.id)}
                                              disabled={busy || !(answerDrafts[question.id] || "").trim()}
                                              className="h-8 px-3 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium disabled:opacity-50"
                                            >
                                              Lưu câu trả lời
                                            </button>
                                          </div>
                                        )
                                      )}
                                    </li>
                                  ))}
                              </ul>

                              {mode === "doctor" &&
                                detail.questions.every((question) => !question.is_selected) && (
                                  <p className="text-sm text-zinc-500 mt-2">
                                    Bệnh nhân chưa chọn câu hỏi nào cho phiếu này.
                                  </p>
                                )}
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}
