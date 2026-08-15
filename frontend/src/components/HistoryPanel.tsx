"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
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
import { formatDate, formatMoment, indicatorStatusText } from "@/lib/patientUi.mjs";

type Props = {
  /** "patient" chỉ xem của mình; "doctor" tra được theo tên bệnh nhân. */
  mode: "patient" | "doctor";
  accent?: "blue" | "indigo";
  id?: string;
  pageSize?: number;
  /** Đổi giá trị này để buộc nạp lại danh sách (vd. vừa lưu một phiếu mới). */
  refreshToken?: number;
  onUnauthorized: () => void;
};

const ACCENT = {
  blue: { button: "bg-blue-600 hover:bg-blue-700", text: "text-blue-600" },
  indigo: { button: "bg-indigo-600 hover:bg-indigo-700", text: "text-indigo-600" },
};

/** Nhãn trạng thái phiếu cho cả hai phía.
 *
 * Hai trạng thái tách biệt vì chúng trả lời hai câu hỏi khác nhau. "Đã có ai xem
 * phiếu của tôi chưa" thường quan trọng hơn cả nội dung nhận xét.
 */
function reviewBadge(item: { reviewed_by_doctor: boolean; has_doctor_notes: boolean }) {
  if (item.has_doctor_notes) {
    return {
      label: "Đã có ý kiến bác sĩ",
      className: "bg-emerald-50 text-emerald-700",
    };
  }
  if (item.reviewed_by_doctor) {
    return {
      label: "Bác sĩ đã xem",
      className: "bg-sky-50 text-sky-700",
    };
  }
  return {
    label: "Chưa có bác sĩ xem",
    className: "bg-slate-100 text-slate-600",
  };
}

function reportBadge(item: { has_critical_values: boolean; abnormal_count: number }) {
  if (item.has_critical_values) {
    return { label: "Nguy kịch", tone: "critical" };
  }
  if (item.abnormal_count > 0) {
    return { label: "Bất thường", tone: "abnormal" };
  }
  return { label: "Bình thường", tone: "normal" };
}

export default function HistoryPanel({ mode, accent = "blue", id, pageSize = 5, refreshToken = 0, onUnauthorized }: Props) {
  const theme = ACCENT[accent];
  const panelRef = useRef<HTMLElement | null>(null);

  const [fromDate, setFromDate] = useState("");
  const [toDate, setToDate] = useState("");
  const [patientUsername, setPatientUsername] = useState("");
  const [page, setPage] = useState(1);

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

  const load = useCallback(async (
    nextPage = page,
    options: {
      from?: string;
      to?: string;
      patientUsername?: string;
      scroll?: boolean;
    } = {},
  ) => {
    const queryFrom = options.from ?? fromDate;
    const queryTo = options.to ?? toDate;
    const queryPatientUsername = options.patientUsername ?? patientUsername;

    setLoading(true);
    setError(null);
    try {
      const data = await fetchHistory({
        from: queryFrom || undefined,
        to: queryTo || undefined,
        patientUsername: mode === "doctor" ? queryPatientUsername.trim() || undefined : undefined,
        limit: pageSize,
        offset: (nextPage - 1) * pageSize,
      });
      setItems(data.items);
      setTotal(data.total);
      setPage(nextPage);
      setExpandedId(null);
      setDetail(null);
      if (options.scroll) {
        window.requestAnimationFrame(() => panelRef.current?.scrollIntoView({ block: "start" }));
      }
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
  }, [fromDate, toDate, patientUsername, mode, onUnauthorized, page, pageSize]);

  useEffect(() => {
    // Nạp lần đầu và mỗi khi có phiếu mới được lưu.
    //
    // Cố tình KHÔNG phụ thuộc `load`: nó đổi identity theo từng ký tự gõ vào ô
    // lọc, đưa vào deps sẽ thành gọi API liên tục. Việc lọc do người dùng bấm
    // nút. `load` cũng đặt state ngay (cờ loading) — đây là fetch lúc mở panel,
    // không phải đồng bộ state với state khác.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở panel, không phải đồng bộ state
    void load(1);
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

  function applyFilters() {
    void load(1);
  }

  function clearFilters() {
    setFromDate("");
    setToDate("");
    setPatientUsername("");
    void load(1, { from: "", to: "", patientUsername: "" });
  }

  function goToPage(nextPage: number) {
    if (nextPage < 1 || nextPage > totalPages || nextPage === page) return;
    void load(nextPage, { scroll: true });
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const rangeStart = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const rangeEnd = Math.min(total, page * pageSize);
  const pageNumbers = Array.from({ length: totalPages }, (_, index) => index + 1)
    .filter((item) => item === 1 || item === totalPages || Math.abs(item - page) <= 1);

  return (
    <section id={id} ref={panelRef} className="history-panel">
      <div className="history-panel-header">
        <h2 className="text-lg font-semibold text-slate-950">
          {mode === "doctor" ? "Lịch sử xét nghiệm của bệnh nhân" : "Lịch sử xét nghiệm của tôi"}
        </h2>
        <p className="mt-1 text-sm text-slate-600">
          {mode === "doctor"
            ? "Mở một phiếu để đọc kết quả, xem câu hỏi bệnh nhân đã chọn và ghi nhận xét."
            : "Mỗi lần bạn phân tích một phiếu, kết quả được lưu lại ở đây."}
        </p>

        <div className="mt-4 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {mode === "doctor" && (
            <label className="space-y-1 text-sm text-slate-700">
              <span className="font-medium">Tên bệnh nhân</span>
              <input
                aria-label="Tên đăng nhập của bệnh nhân"
                value={patientUsername}
                onChange={(event) => setPatientUsername(event.target.value)}
                placeholder="Tất cả bệnh nhân"
                className="history-filter-input"
              />
            </label>
          )}
          <label className="space-y-1 text-sm text-slate-700">
            <span className="font-medium">Từ ngày</span>
            <input
              aria-label="Lọc lịch sử từ ngày"
              type="date"
              value={fromDate}
              onChange={(event) => setFromDate(event.target.value)}
              className="history-filter-input"
            />
          </label>
          <label className="space-y-1 text-sm text-slate-700">
            <span className="font-medium">Đến ngày</span>
            <input
              aria-label="Lọc lịch sử đến ngày"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="history-filter-input"
            />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={applyFilters}
              disabled={loading}
              className={`flex-1 h-10 rounded-lg text-sm font-medium text-white disabled:opacity-50 ${theme.button}`}
            >
              {loading ? "Đang tải..." : "Lọc"}
            </button>
            {(fromDate || toDate || patientUsername) && (
              <button
                type="button"
                onClick={clearFilters}
                className="h-10 rounded-lg border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50"
              >
                Xoá lọc
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div className="bg-red-50 px-6 py-4 text-sm text-red-600">
          {error}
        </div>
      )}

      {loading && (
        <div className="grid gap-3 px-6 py-5" role="status" aria-live="polite">
          {Array.from({ length: pageSize }).map((_, index) => (
            <div key={index} className="h-16 animate-pulse rounded-xl bg-slate-100" />
          ))}
        </div>
      )}

      {!error && items.length === 0 && !loading && (
        <div className="px-6 py-8 text-center text-sm text-slate-500">
          <p>
            {fromDate || toDate ? "Không có phiếu nào trong khoảng thời gian này." : "Chưa có phiếu xét nghiệm nào trong khoảng đã chọn."}
          </p>
          {(fromDate || toDate || patientUsername) && (
            <button type="button" onClick={clearFilters} className="text-button mt-3 px-3 py-2">
              Xóa lọc
            </button>
          )}
          {mode === "patient" && !fromDate && !toDate && (
            <Link href="/patient/analysis" className="primary-button mt-4 inline-flex items-center">
              Phân tích kết quả đầu tiên
            </Link>
          )}
        </div>
      )}

      {items.length > 0 && !loading && (
        <>
          <p className="px-6 pt-4 text-xs text-slate-500">
            Hiển thị {rangeStart}-{rangeEnd} trong {total} phiếu
          </p>
          <ul className="divide-y divide-slate-100">
            {items.map((item) => {
              const badge = reviewBadge(item);
              const status = reportBadge(item);

              return (
                <li key={item.id}>
                  <div className="history-row-actions">
                    <button
                      type="button"
                      onClick={() => void toggleDetail(item.id)}
                      className="history-row"
                      aria-expanded={expandedId === item.id}
                    >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="font-medium text-slate-950">
                          Phiếu ngày {formatDate(item.test_date)}
                          {mode === "doctor" && (
                            <span className="ml-2 text-sm font-normal text-slate-500">
                              — {item.patient_username}
                            </span>
                          )}
                        </div>
                        <div className="mt-1 text-xs text-slate-500">
                          {item.indicator_count} chỉ số · {item.abnormal_count} bất thường ·{" "}
                          {item.source === "ocr" ? "nhập từ ảnh" : "nhập tay"} · tạo lúc {formatMoment(item.created_at)}
                        </div>
                      </div>
                      <div className="flex items-center gap-2">
                        <span className={`status-badge status-${status.tone}`}>
                          {status.label}
                        </span>
                        <span className={`review-badge ${badge.className}`}>
                          {badge.label}
                        </span>
                        <span className={`text-xs font-medium ${theme.text}`}>
                          {expandedId === item.id ? "Thu gọn" : mode === "patient" ? "Mở nhanh" : "Xem chi tiết"} ›
                        </span>
                      </div>
                    </div>
                    </button>
                    {mode === "patient" && (
                      <Link href={`/patient/reports/${item.id}`} className="history-detail-link">
                        Xem trang chi tiết
                      </Link>
                    )}
                  </div>

                  {expandedId === item.id && (
                    <div className="bg-slate-50/70 px-6 pb-5">
                      {detailLoading && <p className="py-4 text-sm text-slate-500">Đang mở phiếu...</p>}

                      {actionError && (
                        <p className="mt-4 text-sm text-red-600">{actionError}</p>
                      )}

                      {detail && (
                        <div className="space-y-5 pt-4">
                          <p className="text-xs text-slate-500">
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
                                className="rounded-xl border border-slate-200 bg-white p-4"
                              >
                                <div className="flex items-center justify-between gap-3">
                                  <span className="font-medium">{indicator.name}</span>
                                  <span className="text-sm">
                                    <strong>{indicator.value}</strong>{" "}
                                    <span className="text-slate-500">{indicator.unit}</span>
                                  </span>
                                </div>
                                <div className="mt-1 text-xs text-slate-500">
                                  Khoảng tham chiếu: {indicator.reference_low ?? "-"} –{" "}
                                  {indicator.reference_high ?? "-"} · {indicatorStatusText(indicator.status, indicator.critical_status)}
                                </div>
                                {indicator.explanation && (
                                  <p className="mt-2 text-sm leading-relaxed text-slate-700">
                                    {indicator.explanation}
                                  </p>
                                )}
                              </div>
                            ))}

                            {detail.disclaimer && (
                              <p className="text-xs italic text-slate-500">{detail.disclaimer}</p>
                            )}
                          </div>

                          {/* ---- Khối 2: ghi chú của bác sĩ ----
                              Tách bạch khỏi khối trên vì đây là ranh giới trách
                              nhiệm thật: phần hệ thống luôn kèm khuyến cáo
                              "không chẩn đoán", phần bác sĩ thì ngược lại, có
                              thể chứa đúng thứ hệ thống bị cấm. Trộn hai nguồn
                              vào một khối thì bệnh nhân không biết ai đang nói
                              với mình. */}
                          <div className="rounded-xl border-2 border-emerald-200 bg-emerald-50/50 p-4">
                            <h3 className="text-sm font-semibold text-emerald-900">
                              Ghi chú của bác sĩ
                            </h3>

                            {detail.doctor_notes.length === 0 ? (
                              <p className="mt-2 text-sm text-slate-600">
                                {detail.reviewed_by_doctor
                                  ? "Bác sĩ đã xem phiếu này và chưa có nhận xét thêm."
                                  : "Chưa có bác sĩ nào ghi nhận xét cho phiếu này."}
                              </p>
                            ) : (
                              <ul className="mt-3 space-y-3">
                                {detail.doctor_notes.map((note) => (
                                  <li
                                    key={note.id}
                                    className="rounded-lg border border-emerald-200 bg-white p-3"
                                  >
                                    <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-800">
                                      {note.note_text}
                                    </p>
                                    <p className="mt-2 text-xs text-slate-500">
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
                              <p className="mt-3 text-xs text-emerald-800/80">
                                Nội dung trong khối này do bác sĩ trực tiếp viết và tự chịu trách
                                nhiệm, không do hệ thống sinh ra và không qua bộ kiểm duyệt nội dung
                                tự động.
                              </p>
                            )}

                            {detail.doctor_views.length > 0 && (
                              <p className="mt-2 text-xs text-slate-500">
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
                                  className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
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
                                    className="h-9 rounded-lg border border-slate-300 px-4 text-sm disabled:opacity-50"
                                  >
                                    Đánh dấu đã xem
                                  </button>
                                </div>
                                <p className="text-xs text-slate-500">
                                  Ghi chú chỉ thêm mới, không sửa và không xoá. Muốn đính chính thì
                                  viết ghi chú mới.
                                </p>
                              </div>
                            )}
                          </div>

                          {/* ---- Khối 3: câu hỏi gợi ý ---- */}
                          {detail.questions.length > 0 && (
                            <div className="rounded-xl border border-slate-200 bg-white p-4">
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
                                      className="rounded-lg border border-slate-200 p-3"
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
                                        <div className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50/60 p-3">
                                          <p className="text-sm whitespace-pre-wrap">
                                            {question.answer_text}
                                          </p>
                                          <p className="mt-2 text-xs text-slate-500">
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
                                              className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
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
                                    <p className="mt-2 text-sm text-slate-500">
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
          <div className="history-pagination">
            <button type="button" onClick={() => goToPage(page - 1)} disabled={page === 1}>
              ‹
            </button>
            {pageNumbers.map((item, index) => {
              const previous = pageNumbers[index - 1];
              return (
                <span key={item} className="contents">
                  {previous && item - previous > 1 && <span className="history-page-gap">…</span>}
                  <button
                    type="button"
                    onClick={() => goToPage(item)}
                    className={item === page ? "active" : ""}
                    aria-current={item === page ? "page" : undefined}
                  >
                    {item}
                  </button>
                </span>
              );
            })}
            <button type="button" onClick={() => goToPage(page + 1)} disabled={page === totalPages}>
              ›
            </button>
          </div>
        </>
      )}
    </section>
  );
}
