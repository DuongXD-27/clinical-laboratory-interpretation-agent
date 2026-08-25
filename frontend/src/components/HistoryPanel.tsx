"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronDown, ChevronRight } from "lucide-react";
import {
  answerReportQuestion,
  createDoctorNote,
  fetchHistory,
  fetchHistoryDetail,
  markReportReviewed,
  selectReportQuestions,
  UnauthorizedError,
} from "@/lib/api";
import SeverityBadge from "@/components/common/SeverityBadge";
import VerificationBadge from "@/components/common/VerificationBadge";
import IndicatorResultCard from "./patient/IndicatorResultCard";
import type { LabReportDetail, LabReportSummary } from "@/types/history";
import { formatDate, formatMoment } from "@/lib/patientUi.mjs";
import { groupBySection } from "@/lib/trendUi.mjs";
import type { SeverityLevel } from "@/types/doctor";

type Props = {
  /** "patient" chỉ xem của mình; "doctor" tra được theo tên bệnh nhân. */
  mode: "patient" | "doctor";
  /** Retained for call-site compatibility; visual accent is handled by severity badges. */
  accent?: "blue" | "indigo";
  id?: string;
  pageSize?: number;
  /** Đổi giá trị này để buộc nạp lại danh sách (vd. vừa lưu một phiếu mới). */
  refreshToken?: number;
  onUnauthorized: () => void;
};

function reportSeverity(item: { has_critical_values: boolean; abnormal_count: number }): SeverityLevel {
  if (item.has_critical_values) return "critical";
  if (item.abnormal_count > 0) return "abnormal";
  return "normal";
}

export default function HistoryPanel({ mode, id, pageSize = 5, refreshToken = 0, onUnauthorized }: Props) {
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
              verification_status: updated.verification_status,
              verified_by_username: updated.verified_by_username,
              verified_at: updated.verified_at,
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
        <h2 className="text-lg font-semibold text-foreground">
          {mode === "doctor" ? "Lịch sử xét nghiệm của bệnh nhân" : "Lịch sử xét nghiệm của tôi"}
        </h2>
        <p className="mt-1 text-sm text-muted-foreground">
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
                className="w-full h-10 px-3 text-sm patient-control-clinical"
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
              className="w-full h-10 px-3 text-sm patient-control-clinical"
            />
          </label>
          <label className="space-y-1 text-sm text-slate-700">
            <span className="font-medium">Đến ngày</span>
            <input
              aria-label="Lọc lịch sử đến ngày"
              type="date"
              value={toDate}
              onChange={(event) => setToDate(event.target.value)}
              className="w-full h-10 px-3 text-sm patient-control-clinical"
            />
          </label>
          <div className="flex items-end gap-2">
            <button
              type="button"
              onClick={applyFilters}
              disabled={loading}
              className="flex-1 patient-btn-secondary disabled:opacity-50"
            >
              {loading ? "Đang tải..." : "Lọc"}
            </button>
            {(fromDate || toDate || patientUsername) && (
              <button
                type="button"
                onClick={clearFilters}
                className="h-10 px-4 rounded-xl text-sm font-medium text-slate-600 hover:text-slate-900 bg-[var(--surface-subtle)] border border-[var(--border)] transition-colors"
              >
                Xoá lọc
              </button>
            )}
          </div>
        </div>
      </div>

      {error && (
        <div role="alert" className="patient-glass-clinical p-6 mt-4 text-[var(--status-critical-fg)]">
          {error}
        </div>
      )}

      {loading && (
        <div className="grid gap-3 py-5" role="status" aria-live="polite">
          {Array.from({ length: Math.min(pageSize, 5) }).map((_, index) => (
            <div key={index} className="h-16 animate-pulse motion-reduce:animate-none rounded-xl bg-[var(--surface-subtle)] border border-[var(--border)]/60" />
          ))}
        </div>
      )}

      {!error && items.length === 0 && !loading && (
        <div className="patient-glass-clinical p-8 my-4 text-center text-sm text-muted-foreground">
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
          <p className="pt-4 pb-2 text-xs text-slate-500">
            Hiển thị {rangeStart}-{rangeEnd} trong {total} phiếu
          </p>
          <ul className="pb-6">
            {items.map((item) => {
              const severity = reportSeverity(item);

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
                        <div className="text-lg font-semibold text-slate-950">
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
                        <SeverityBadge level={severity} />
                        <VerificationBadge status={item.verification_status} />
                        <span className="flex items-center gap-1 text-xs font-medium text-slate-500 hover:text-indigo-600 transition-colors ml-1">
                          {mode === "patient" ? "Mở nhanh" : "Xem chi tiết"}
                          {expandedId === item.id ? (
                            <ChevronDown className="w-3.5 h-3.5" />
                          ) : (
                            <ChevronRight className="w-3.5 h-3.5" />
                          )}
                        </span>
                      </div>
                    </div>
                    </button>
                  </div>

                  {expandedId === item.id && (
                    <div className="pb-5 pt-2">
                      {detailLoading && <p className="py-4 text-sm text-slate-500 px-6">Đang mở phiếu...</p>}

                      {actionError && (
                        <p className="mt-4 text-sm text-red-600 px-6">{actionError}</p>
                      )}

                      {detail && (
                        <div className="space-y-5">
                          <div className="flex items-center gap-2 mb-2 pb-3 pt-3 border-b border-slate-100 text-slate-500 px-6">
                            <span className="text-sm font-medium text-slate-700">Thông tin bệnh nhân</span>
                            <span className="w-1 h-1 rounded-full bg-slate-300"></span>
                            <span className="text-slate-600">
                              {detail.patient_age_at_test ?? "-"} tuổi ·{" "}
                              {detail.patient_gender_at_test === "male"
                                ? "Nam"
                                : detail.patient_gender_at_test === "female"
                                  ? "Nữ"
                                  : "Khác"}
                            </span>
                          </div>

                          {/* ---- Khối 1: nội dung do hệ thống sinh ---- */}
                          <div className="space-y-4">
                            {groupBySection(detail.indicators).map((group) => (
                              <div key={group.label} className="space-y-3">
                                <h4 className="indicator-group-title text-sm font-semibold text-slate-800">{group.label}</h4>
                                {group.items.map((indicator, index) => (
                                  <IndicatorResultCard
                                    key={index}
                                    indicator={indicator as unknown as import("@/types/analysis").IndicatorResult}
                                  />
                                ))}
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
                          
                          {mode === "patient" && (
                            <div className="pt-4 mt-2 flex justify-end">
                              <Link href={`/patient/reports/${item.id}`} className="text-sm font-medium text-indigo-600 hover:text-indigo-700 hover:underline">
                                Xem trang chi tiết ›
                              </Link>
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
