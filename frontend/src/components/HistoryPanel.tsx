"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchHistory, fetchHistoryDetail, UnauthorizedError } from "@/lib/api";
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

  async function toggleDetail(reportId: number) {
    if (expandedId === reportId) {
      setExpandedId(null);
      setDetail(null);
      return;
    }

    setExpandedId(reportId);
    setDetail(null);
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

  return (
    <section className="bg-white dark:bg-zinc-900 rounded-2xl border border-zinc-200 dark:border-zinc-800 shadow-sm overflow-hidden">
      <div className="p-6 border-b border-zinc-100 dark:border-zinc-800">
        <h2 className="font-semibold text-lg">
          {mode === "doctor" ? "Lịch sử xét nghiệm của bệnh nhân" : "Lịch sử xét nghiệm của tôi"}
        </h2>
        <p className="text-sm text-zinc-500 mt-1">
          {mode === "doctor"
            ? "Để trống ô tên bệnh nhân để xem toàn bộ. Lọc theo ngày ghi trên phiếu."
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
            {items.map((item) => (
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
                      <span className={`text-xs font-medium ${theme.text}`}>
                        {expandedId === item.id ? "Thu gọn" : "Xem chi tiết"}
                      </span>
                    </div>
                  </div>
                </button>

                {expandedId === item.id && (
                  <div className="px-6 pb-5 bg-zinc-50/60 dark:bg-zinc-950/40">
                    {detailLoading && <p className="py-4 text-sm text-zinc-500">Đang mở phiếu...</p>}
                    {detail && (
                      <div className="space-y-3 pt-4">
                        <p className="text-xs text-zinc-500">
                          {detail.patient_age} tuổi ·{" "}
                          {detail.patient_gender === "male" ? "Nam" : detail.patient_gender === "female" ? "Nữ" : "Khác"}
                        </p>
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
                              Khoảng tham chiếu: {indicator.reference_low ?? "-"} – {indicator.reference_high ?? "-"} ·{" "}
                              {indicator.status}
                            </div>
                            {indicator.explanation && (
                              <p className="text-sm text-zinc-700 dark:text-zinc-300 mt-2 leading-relaxed">
                                {indicator.explanation}
                              </p>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
