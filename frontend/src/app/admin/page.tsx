"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  ForbiddenError,
  UnauthorizedError,
  clearSession,
  fetchTraceSummary,
  fetchTraces,
  fetchTracingStatus,
  getRole,
  getToken,
} from "@/lib/api";
import type { RequestTrace, TraceSummary, TracingStatus } from "@/types/admin";

const WINDOW_OPTIONS = [
  { hours: 1, label: "1 giờ qua" },
  { hours: 24, label: "24 giờ qua" },
  { hours: 24 * 7, label: "7 ngày qua" },
];

const PAGE_SIZE = 25;

function formatMs(value: number): string {
  if (value >= 1000) return `${(value / 1000).toFixed(2)}s`;
  return `${Math.round(value)}ms`;
}

function formatClock(iso: string): string {
  // Backend trả giờ UTC không kèm hậu tố Z; thiếu nó thì trình duyệt hiểu là
  // giờ địa phương và mọi mốc lệch đi đúng bằng offset múi giờ.
  const parsed = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleTimeString("vi-VN", { hour12: false });
}

function formatDay(iso: string): string {
  const parsed = new Date(iso.endsWith("Z") ? iso : `${iso}Z`);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
}

/** Phân loại theo mã trạng thái, KHÔNG theo độ trễ.
 *
 * Ngưỡng độ trễ cố ý chưa đặt: nó phải chọn từ số đo thật, và tô đỏ theo một
 * con số đoán bừa chỉ dạy người xem bỏ qua màu đỏ. Mã trạng thái thì không cần
 * đoán — 5xx là hỏng, 4xx là bị từ chối.
 */
function statusTone(status: number): string {
  if (status >= 500) return "trace-status trace-status--error";
  if (status >= 400) return "trace-status trace-status--warn";
  return "trace-status trace-status--ok";
}

export default function AdminTracePage() {
  const router = useRouter();

  const [checkingAuth, setCheckingAuth] = useState(true);
  const [status, setStatus] = useState<TracingStatus | null>(null);
  const [summary, setSummary] = useState<TraceSummary | null>(null);
  const [traces, setTraces] = useState<RequestTrace[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);

  const [windowHours, setWindowHours] = useState(24);
  const [onlyLlmErrors, setOnlyLlmErrors] = useState(false);
  const [onlyServerErrors, setOnlyServerErrors] = useState(false);
  const [offset, setOffset] = useState(0);

  // Ô nhập tự do tách làm hai state: cái đang gõ và cái đã áp dụng.
  //
  // Nếu `load` phụ thuộc thẳng vào ô nhập thì mỗi ký tự gõ vào là một lượt gọi
  // API — HistoryPanel đã vấp đúng chuyện này. Ô nhập chỉ có hiệu lực khi bấm
  // Lọc hoặc Enter; select và nút bật/tắt thì áp dụng ngay vì chúng đổi rời rạc.
  const [pathInput, setPathInput] = useState("");
  const [durationInput, setDurationInput] = useState("");
  const [appliedPath, setAppliedPath] = useState("");
  const [appliedDuration, setAppliedDuration] = useState("");

  useEffect(() => {
    if (!getToken() || getRole() !== "admin") {
      router.replace("/login");
      return;
    }
    // eslint-disable-next-line react-hooks/set-state-in-effect -- localStorage auth is available only after mount.
    setCheckingAuth(false);
  }, [router]);

  const bounce = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const parsedDuration = appliedDuration.trim() === "" ? undefined : Number(appliedDuration);

      const [statusData, summaryData, listData] = await Promise.all([
        fetchTracingStatus(),
        fetchTraceSummary(windowHours),
        fetchTraces({
          limit: PAGE_SIZE,
          offset,
          windowHours,
          path: appliedPath.trim() || undefined,
          onlyLlmErrors: onlyLlmErrors || undefined,
          statusCode: onlyServerErrors ? 500 : undefined,
          minDurationMs:
            parsedDuration !== undefined && Number.isFinite(parsedDuration) ? parsedDuration : undefined,
        }),
      ]);

      setStatus(statusData);
      setSummary(summaryData);
      setTraces(listData.items);
      setTotal(listData.total);
      setLoadedAt(new Date().toLocaleTimeString("vi-VN", { hour12: false }));
    } catch (err) {
      // Máy chủ mới là nơi quyết định vai trò, không phải localStorage.
      //
      // Guard ở đầu trang đọc `getRole()`, tức là đọc một giá trị người dùng
      // sửa được bằng DevTools. Sửa thành "admin" là guard cho qua, và trước
      // bản vá này trang sẽ đứng nguyên ở màn admin kèm một dòng lỗi — không
      // rò dữ liệu nào, nhưng trông y như phân quyền hỏng.
      //
      // 403 nghĩa là máy chủ đã phủ nhận vai trò đó. Xoá phiên và đá về đăng
      // nhập, thay vì tiếp tục tin localStorage.
      if (err instanceof UnauthorizedError || err instanceof ForbiddenError) {
        bounce();
        return;
      }
      setError(err instanceof Error ? err.message : "Không tải được dữ liệu trace");
    } finally {
      setLoading(false);
    }
  }, [appliedDuration, appliedPath, bounce, offset, onlyLlmErrors, onlyServerErrors, windowHours]);

  useEffect(() => {
    if (checkingAuth) return;
    // `load` đặt cờ loading ngay khi chạy — đây là nạp dữ liệu lúc mở trang và
    // khi bộ lọc đã áp dụng đổi, không phải đồng bộ state này theo state khác.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở trang, không phải đồng bộ state
    void load();
  }, [checkingAuth, load]);

  if (checkingAuth) {
    return (
      <div className="loading-message" role="status">
        Đang mở trang quản trị...
      </div>
    );
  }

  // Tỉ lệ thanh nền theo dòng chậm nhất của TRANG đang xem. Dùng ngưỡng tuyệt
  // đối thì phải bịa ra một con số, mà con số đó chưa chọn từ số đo thật.
  const slowest = traces.reduce((max, trace) => Math.max(max, trace.duration_ms), 1);
  const hasFilters = Boolean(appliedPath || appliedDuration || onlyLlmErrors || onlyServerErrors);

  return (
    <div className="history-page-layout">
      <div className="page-section-heading">
        <div>
          <span className="eyebrow">Vận hành</span>
          <h2>Trace hệ thống</h2>
          <p>
            Độ trễ, truy vấn CSDL và lời gọi LLM của từng request. Trang này không hiển thị dữ liệu
            xét nghiệm của bệnh nhân.
          </p>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          {loadedAt ? <span className="trace-updated">Cập nhật {loadedAt}</span> : null}
          <button
            type="button"
            className="secondary-button"
            onClick={() => void load()}
            disabled={loading}
          >
            {loading ? "Đang tải..." : "Làm mới"}
          </button>
          {/* Bản đầu của trang này KHÔNG có nút đăng xuất — màn bệnh nhân có
              (trong PatientShell), màn bác sĩ có, riêng admin thì không. Hệ quả
              không phải chuyện thẩm mỹ: admin vào đây rồi thì không còn chỗ nào
              để thoát, phiên nằm lại trong localStorage, và người dùng tưởng
              mình đã đăng xuất trong khi chưa. */}
          <button
            type="button"
            className="secondary-button"
            onClick={() => {
              clearSession();
              router.replace("/login");
            }}
          >
            Đăng xuất
          </button>
        </div>
      </div>

      {error ? (
        <p className="error-message" role="alert">
          {error}
        </p>
      ) : null}

      {status ? (
        <section className="admin-surface trace-config">
          <span className="trace-config__item">
            <span className={`trace-dot ${status.langfuse_configured ? "trace-dot--on" : "trace-dot--off"}`} />
            Langfuse
            <strong className="trace-config__value">
              {status.langfuse_configured ? "đang bật" : "chưa cấu hình"}
            </strong>
          </span>
          <span className="trace-config__item">
            Máy chủ
            <span className="trace-config__value trace-config__value--mono">{status.langfuse_host}</span>
          </span>
          <span className="trace-config__item">
            Che dữ liệu
            <strong className="trace-config__value">{status.masked ? "bật" : "tắt"}</strong>
          </span>
          <span className="trace-config__item">
            Giữ trace
            <strong className="trace-config__value">{status.retention_days} ngày</strong>
          </span>
          {status.langfuse_configured ? null : (
            /* Phân biệt "chưa cấu hình" với "chưa có traffic". Thiếu dòng này
               thì một bảng rỗng có hai cách hiểu và không cách nào loại trừ. */
            <p className="trace-config__note">
              Chưa đặt LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY. Bảng dưới vẫn chạy bình thường vì nó
              đọc CSDL của hệ thống; chỉ thiếu phần token và chi phí từng lời gọi LLM.
            </p>
          )}
        </section>
      ) : null}

      {summary ? (
        <section className="trace-kpis">
          <div className="trace-kpi">
            <span className="trace-kpi__label">Request</span>
            <strong className="trace-kpi__value">{summary.request_count}</strong>
            <span className="trace-kpi__unit">trong khoảng đang xem</span>
          </div>
          <div className="trace-kpi">
            <span className="trace-kpi__label">Trung bình</span>
            <strong className="trace-kpi__value">{formatMs(summary.avg_duration_ms)}</strong>
            <span className="trace-kpi__unit">mỗi request</span>
          </div>
          <div className="trace-kpi">
            <span className="trace-kpi__label">Chậm nhất</span>
            <strong className="trace-kpi__value">{formatMs(summary.max_duration_ms)}</strong>
            <span className="trace-kpi__unit">một lượt</span>
          </div>
          <div className="trace-kpi">
            <span className="trace-kpi__label">Gọi LLM</span>
            <strong className="trace-kpi__value">{summary.llm_call_count}</strong>
            <span className="trace-kpi__unit">lượt</span>
          </div>
          <div className={`trace-kpi${summary.llm_error_count > 0 ? " trace-kpi--alert" : ""}`}>
            <span className="trace-kpi__label">LLM lỗi</span>
            <strong className="trace-kpi__value">{summary.llm_error_count}</strong>
            <span className="trace-kpi__unit">vẫn trả về 200</span>
          </div>
          <div className={`trace-kpi${summary.server_error_count > 0 ? " trace-kpi--alert" : ""}`}>
            <span className="trace-kpi__label">Lỗi 5xx</span>
            <strong className="trace-kpi__value">{summary.server_error_count}</strong>
            <span className="trace-kpi__unit">request hỏng</span>
          </div>
        </section>
      ) : null}

      {/* LLM hỏng thì analyzer âm thầm rơi về nội dung dựng sẵn, response vẫn
          200, và chỉ bệnh nhân nhận ra chất lượng đi xuống. Nên nhắc chủ động,
          kèm sẵn nút lọc — thấy vấn đề mà phải tự đi tìm thì phần lớn sẽ bỏ qua. */}
      {summary && summary.llm_error_count > 0 && !onlyLlmErrors ? (
        <div className="trace-alert">
          <span>
            <strong>{summary.llm_error_count} lời gọi LLM lỗi</strong> trong khoảng này. Những request đó
            vẫn trả 200 nhưng nội dung đã rơi về bản dựng sẵn.
          </span>
          <button
            type="button"
            onClick={() => {
              setOnlyLlmErrors(true);
              setOffset(0);
            }}
          >
            Xem ngay
          </button>
        </div>
      ) : null}

      <form
        className="admin-surface trace-filters"
        onSubmit={(event) => {
          event.preventDefault();
          setAppliedPath(pathInput);
          setAppliedDuration(durationInput);
          setOffset(0);
        }}
      >
        <label className="trace-field">
          <span className="trace-field__label">Khoảng thời gian</span>
          <select
            value={windowHours}
            onChange={(event) => {
              setWindowHours(Number(event.target.value));
              setOffset(0);
            }}
          >
            {WINDOW_OPTIONS.map((option) => (
              <option key={option.hours} value={option.hours}>
                {option.label}
              </option>
            ))}
          </select>
        </label>

        <label className="trace-field trace-field--path">
          <span className="trace-field__label">Đường dẫn chứa</span>
          <input
            type="text"
            value={pathInput}
            placeholder="/api/v1/analyze"
            onChange={(event) => setPathInput(event.target.value)}
          />
        </label>

        <label className="trace-field trace-field--num">
          <span className="trace-field__label">Chậm hơn</span>
          <input
            type="number"
            min={0}
            value={durationInput}
            placeholder="3000 ms"
            onChange={(event) => setDurationInput(event.target.value)}
          />
        </label>

        <label className={`trace-toggle${onlyLlmErrors ? " trace-toggle--on" : ""}`}>
          <input
            type="checkbox"
            checked={onlyLlmErrors}
            onChange={(event) => {
              setOnlyLlmErrors(event.target.checked);
              setOffset(0);
            }}
          />
          Chỉ request có LLM lỗi
        </label>

        <label className={`trace-toggle${onlyServerErrors ? " trace-toggle--on" : ""}`}>
          <input
            type="checkbox"
            checked={onlyServerErrors}
            onChange={(event) => {
              setOnlyServerErrors(event.target.checked);
              setOffset(0);
            }}
          />
          Chỉ lỗi 500
        </label>

        <button type="submit" className="secondary-button trace-filters__submit" disabled={loading}>
          Lọc
        </button>
      </form>

      <section className="admin-surface trace-table-wrap">
        <div className="trace-scroll">
          <table className="trace-table">
            <thead>
              <tr>
                <th>Thời điểm</th>
                <th>Request</th>
                <th>Mã</th>
                <th className="trace-num">Thời lượng</th>
                <th className="trace-num">CSDL</th>
                <th className="trace-num">LLM</th>
                <th>Vai trò</th>
                <th>request_id</th>
              </tr>
            </thead>
            <tbody>
              {traces.length === 0 ? (
                <tr>
                  <td colSpan={8} className="trace-empty">
                    {loading ? (
                      "Đang tải..."
                    ) : (
                      <>
                        <strong>Không có request nào khớp bộ lọc</strong>
                        {hasFilters
                          ? "Nới bộ lọc hoặc chọn khoảng thời gian rộng hơn."
                          : "Hệ thống chưa nhận request nào trong khoảng này."}
                      </>
                    )}
                  </td>
                </tr>
              ) : (
                traces.map((trace) => {
                  const share = Math.max(4, Math.round((trace.duration_ms / slowest) * 100));
                  return (
                    <tr key={`${trace.request_id}-${trace.created_at}`}>
                      <td className="trace-time">
                        {formatClock(trace.created_at)}
                        <div className="trace-sub">{formatDay(trace.created_at)}</div>
                      </td>
                      <td>
                        <span className="trace-method">{trace.method}</span>
                        <div className="trace-path" title={trace.path}>
                          {trace.path}
                        </div>
                      </td>
                      <td>
                        <span className={statusTone(trace.status_code)}>{trace.status_code}</span>
                      </td>
                      <td className="trace-num">
                        <span className="trace-bar">
                          <span
                            className={`trace-bar__fill${trace.duration_ms >= 3000 ? " trace-bar__fill--slow" : ""}`}
                            style={{ width: `${share}%` }}
                          />
                          <span className="trace-bar__text">{formatMs(trace.duration_ms)}</span>
                        </span>
                      </td>
                      <td className="trace-num">
                        {trace.db_query_count}
                        <div className="trace-sub">{formatMs(trace.db_ms)}</div>
                      </td>
                      <td className="trace-num">
                        {trace.llm_call_count > 0 ? (
                          <>
                            {trace.llm_call_count}
                            {trace.llm_error_count > 0 ? (
                              <span className="trace-llm-error"> · {trace.llm_error_count} lỗi</span>
                            ) : null}
                            <div className="trace-sub">{formatMs(trace.llm_ms)}</div>
                          </>
                        ) : (
                          <span className="trace-sub">—</span>
                        )}
                      </td>
                      <td className="trace-role">{trace.user_role ?? "—"}</td>
                      <td>
                        <code className="trace-id" title={trace.request_id}>
                          {trace.request_id}
                        </code>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        <div className="trace-footer">
          <span>
            {total === 0 ? "0 request" : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} trên ${total} request`}
          </span>
          <div className="trace-pager">
            <button
              type="button"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Trước
            </button>
            <button
              type="button"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Sau
            </button>
          </div>
        </div>
      </section>
    </div>
  );
}
