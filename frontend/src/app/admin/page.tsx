"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RefreshCw, Search } from "lucide-react";
import {
  ForbiddenError,
  UnauthorizedError,
  clearSession,
  fetchTraceLatency,
  fetchTraceSummary,
  fetchTraces,
  fetchTracingStatus,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import type {
  LatencyGroup,
  LatencyGroups,
  RequestTrace,
  TraceSummary,
  TracingStatus,
} from "@/types/admin";

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
function statusVariant(status: number): "success" | "warning" | "destructive" {
  if (status >= 500) return "destructive";
  if (status >= 400) return "warning";
  return "success";
}

type KpiProps = { label: string; value: string | number; hint: string; alert?: boolean };

/** Một ô số liệu trong bảng phân vị. `null` hiện dấu gạch, không hiện 0. */
function Cell({ value, suffix = "ms" }: { value: number | null; suffix?: string }) {
  if (value === null) {
    // Dấu gạch, không phải "0ms". Trên màn hình vận hành, 0ms đọc như nhanh
    // tuyệt đối — nhầm nó với "chưa đo được" dẫn tới kết luận sai về một hệ
    // thống đang chết.
    return <span className="text-muted-foreground">—</span>;
  }
  const shown = suffix === "ms" && value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}${suffix}`;
  return <span>{shown}</span>;
}

/** Phân vị độ trễ, tách nhóm AI và API thường.
 *
 * Đây là thứ thay cho ô "Trung bình" cũ. Trên dữ liệu thật, trung bình toàn hệ
 * thống ra 85ms trong khi request AI mất 4–7 giây: khoảng 1200 request API
 * thường đè con số đó xuống. Trung bình không sai về toán học, nó chỉ trả lời
 * một câu không ai cần hỏi — "hệ thống nhìn chung thế nào" — thay vì câu cần
 * hỏi là "bệnh nhân đang chờ bao lâu".
 */
function LatencyTable({ latency }: { latency: LatencyGroups }) {
  const rows: Array<{ label: string; hint: string; data: LatencyGroup }> = [
    { label: "Đường AI", hint: "analyze · chatbot · OCR · xu hướng", data: latency.ai },
    { label: "API thường", hint: "đăng nhập · lịch sử · admin", data: latency.api },
  ];

  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Độ trễ theo phân vị
          </span>
          <span className="text-xs text-muted-foreground">
            Trộn hai nhóm này lại thì mọi phân vị đều vô nghĩa
          </span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[36rem] border-collapse text-sm tabular-nums">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-3 font-semibold">Nhóm</th>
                <th className="py-2 px-3 text-right font-semibold">Request</th>
                <th className="py-2 px-3 text-right font-semibold">P50</th>
                <th className="py-2 px-3 text-right font-semibold">P95</th>
                <th className="py-2 px-3 text-right font-semibold">P99</th>
                <th className="py-2 px-3 text-right font-semibold">Max</th>
                <th className="py-2 px-3 text-right font-semibold">Lỗi</th>
                <th className="py-2 pl-3 text-right font-semibold">Req/phút</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ label, hint, data }) => (
                <tr key={data.group} className="border-b border-[var(--border)]/50 last:border-0">
                  <td className="py-2.5 pr-3">
                    <span className="block font-medium text-foreground">{label}</span>
                    <span className="block text-xs text-muted-foreground">{hint}</span>
                  </td>
                  <td className="py-2.5 px-3 text-right">{data.count}</td>
                  <td className="py-2.5 px-3 text-right"><Cell value={data.p50_ms} /></td>
                  <td className="py-2.5 px-3 text-right font-semibold text-foreground">
                    <Cell value={data.p95_ms} />
                  </td>
                  <td className="py-2.5 px-3 text-right"><Cell value={data.p99_ms} /></td>
                  <td className="py-2.5 px-3 text-right"><Cell value={data.max_ms} /></td>
                  <td
                    className={cn(
                      "py-2.5 px-3 text-right",
                      data.error_count > 0 && "font-semibold text-[var(--status-critical-fg)]",
                    )}
                  >
                    <Cell value={data.error_rate_pct} suffix="%" />
                  </td>
                  <td className="py-2.5 pl-3 text-right text-muted-foreground">
                    <Cell value={data.requests_per_min} suffix="" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function Kpi({ label, value, hint, alert = false }: KpiProps) {
  return (
    <Card
      className={cn(
        "gap-0 py-4",
        // Chỉ tô cảnh báo khi thật sự có lỗi. Tô sẵn thì màu mất hết ý nghĩa.
        alert && "border-[var(--status-critical-border)] bg-[var(--status-critical-bg)]",
      )}
    >
      <CardContent className="px-4">
        <span className="block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          {label}
        </span>
        {/* tabular-nums để các thẻ không nhảy khi số đổi lúc làm mới */}
        <strong
          className={cn(
            "mt-1.5 block text-2xl font-semibold leading-none tabular-nums tracking-tight",
            alert ? "text-[var(--status-critical-fg)]" : "text-foreground",
          )}
        >
          {value}
        </strong>
        <span className="mt-1 block text-xs text-muted-foreground">{hint}</span>
      </CardContent>
    </Card>
  );
}

export default function AdminTracePage() {
  const router = useRouter();

  const [status, setStatus] = useState<TracingStatus | null>(null);
  const [summary, setSummary] = useState<TraceSummary | null>(null);
  const [latency, setLatency] = useState<LatencyGroups | null>(null);
  const [traces, setTraces] = useState<RequestTrace[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loadedAt, setLoadedAt] = useState<string | null>(null);
  const [lookupId, setLookupId] = useState("");

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

  const bounce = useCallback(() => {
    clearSession();
    router.replace("/login");
  }, [router]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const parsedDuration = appliedDuration.trim() === "" ? undefined : Number(appliedDuration);

      const [statusData, summaryData, latencyData, listData] = await Promise.all([
        fetchTracingStatus(),
        fetchTraceSummary(windowHours),
        fetchTraceLatency(windowHours),
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
      setLatency(latencyData);
      setTraces(listData.items);
      setTotal(listData.total);
      setLoadedAt(new Date().toLocaleTimeString("vi-VN", { hour12: false }));
    } catch (err) {
      // Máy chủ mới là nơi quyết định vai trò, không phải localStorage. Guard ở
      // AdminShell đọc `getRole()` — một giá trị người dùng sửa được bằng
      // DevTools. 403 nghĩa là máy chủ đã phủ nhận vai trò đó.
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
    // `load` đặt cờ loading ngay khi chạy — đây là nạp dữ liệu lúc mở trang và
    // khi bộ lọc đã áp dụng đổi, không phải đồng bộ state này theo state khác.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- fetch lúc mở trang, không phải đồng bộ state
    void load();
  }, [load]);

  // Tỉ lệ thanh nền theo dòng chậm nhất của TRANG đang xem. Dùng ngưỡng tuyệt
  // đối thì phải bịa ra một con số, mà con số đó chưa chọn từ số đo thật.
  const slowest = traces.reduce((max, trace) => Math.max(max, trace.duration_ms), 1);
  const hasFilters = Boolean(appliedPath || appliedDuration || onlyLlmErrors || onlyServerErrors);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <h2 className="m-0 text-xl font-semibold tracking-tight lg:text-2xl">Trace hệ thống</h2>
          <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
            Độ trễ, truy vấn CSDL và lời gọi LLM của từng request. Trang này không hiển thị dữ liệu xét
            nghiệm của bệnh nhân.
          </p>
        </div>
        <div className="flex items-center gap-3">
          {loadedAt ? (
            <span className="text-xs tabular-nums text-muted-foreground">Cập nhật {loadedAt}</span>
          ) : null}
          {/* Đường đi thật của tính năng này: người dùng đọc `request_id` từ màn
              lỗi rồi đọc cho admin. Bắt admin tự lọc trong bảng là bỏ mất chính
              lý do id đó tồn tại. */}
          <form
            className="flex items-center gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const id = lookupId.trim();
              if (id) router.push(`/admin/traces/${encodeURIComponent(id)}`);
            }}
          >
            <Input
              value={lookupId}
              onChange={(event) => setLookupId(event.target.value)}
              placeholder="Dán request_id..."
              aria-label="Tra cứu theo request_id"
              className="h-9 w-48 font-mono text-xs"
            />
            <Button type="submit" variant="outline" size="sm" disabled={!lookupId.trim()}>
              <Search className="h-4 w-4" aria-hidden="true" />
              Tra
            </Button>
          </form>
          <Button variant="outline" size="sm" onClick={() => void load()} disabled={loading}>
            <RefreshCw className={cn("h-4 w-4", loading && "animate-spin")} aria-hidden="true" />
            {loading ? "Đang tải..." : "Làm mới"}
          </Button>
        </div>
      </div>

      {error ? (
        <Card className="border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] py-3">
          <CardContent className="px-4 text-sm text-[var(--status-critical-fg)]" role="alert">
            {error}
          </CardContent>
        </Card>
      ) : null}

      {status ? (
        <Card className="py-3">
          <CardContent className="flex flex-wrap items-center gap-x-7 gap-y-2 px-4 text-sm">
            <span className="flex items-center gap-2 text-muted-foreground">
              <span
                className={cn(
                  "inline-block h-2 w-2 rounded-full",
                  status.langfuse_configured
                    ? "bg-[var(--status-normal-fg)] shadow-[0_0_0_3px_var(--status-normal-bg)]"
                    : "bg-[var(--foreground-muted)] shadow-[0_0_0_3px_var(--surface-subtle)]",
                )}
                aria-hidden="true"
              />
              Langfuse
              <strong className="font-medium text-foreground">
                {status.langfuse_configured ? "đang bật" : "chưa cấu hình"}
              </strong>
            </span>
            <span className="text-muted-foreground">
              Máy chủ <span className="font-mono text-xs text-foreground">{status.langfuse_host}</span>
            </span>
            <span className="text-muted-foreground">
              Che dữ liệu <strong className="font-medium text-foreground">{status.masked ? "bật" : "tắt"}</strong>
            </span>
            <span className="text-muted-foreground">
              Giữ trace <strong className="font-medium text-foreground">{status.retention_days} ngày</strong>
            </span>
            {status.langfuse_configured ? null : (
              /* Phân biệt "chưa cấu hình" với "chưa có traffic". Thiếu dòng này
                 thì một bảng rỗng có hai cách hiểu và không cách nào loại trừ. */
              <p className="m-0 basis-full text-xs leading-relaxed text-muted-foreground">
                Chưa đặt LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY. Bảng dưới vẫn chạy bình thường vì nó đọc
                CSDL của hệ thống; chỉ thiếu phần token và chi phí từng lời gọi LLM.
              </p>
            )}
          </CardContent>
        </Card>
      ) : null}

      {latency ? <LatencyTable latency={latency} /> : null}

      {summary ? (
        <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
          <Kpi label="Request" value={summary.request_count} hint="trong khoảng đang xem" />
          {/* Ô "Trung bình" đã bị bỏ, không phải quên: 85ms trên 1213 request
              trong khi request AI mất 4–7 giây là một con số gây hiểu sai. Ai
              cần độ trễ thì đọc bảng phân vị ở trên. */}
          <Kpi label="Gọi LLM" value={summary.llm_call_count} hint="lượt" />
          <Kpi
            label="LLM lỗi"
            value={summary.llm_error_count}
            hint="vẫn trả về 200"
            alert={summary.llm_error_count > 0}
          />
          <Kpi
            label="Lỗi 5xx"
            value={summary.server_error_count}
            hint="request hỏng"
            alert={summary.server_error_count > 0}
          />
        </section>
      ) : null}

      {/* LLM hỏng thì analyzer âm thầm rơi về nội dung dựng sẵn, response vẫn
          200, và chỉ bệnh nhân nhận ra chất lượng đi xuống. Nên nhắc chủ động,
          kèm sẵn nút lọc — thấy vấn đề mà phải tự đi tìm thì phần lớn sẽ bỏ qua. */}
      {summary && summary.llm_error_count > 0 && !onlyLlmErrors ? (
        <Card className="border-[var(--status-critical-border)] bg-[var(--status-critical-bg)] py-3">
          <CardContent className="flex flex-wrap items-center gap-3 px-4">
            <AlertTriangle className="h-4 w-4 shrink-0 text-[var(--status-critical-fg)]" aria-hidden="true" />
            <span className="flex-1 text-sm text-[var(--status-critical-fg)]">
              <strong>{summary.llm_error_count} lời gọi LLM lỗi</strong> trong khoảng này. Những request đó vẫn
              trả 200 nhưng nội dung đã rơi về bản dựng sẵn.
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setOnlyLlmErrors(true);
                setOffset(0);
              }}
            >
              Xem ngay
            </Button>
          </CardContent>
        </Card>
      ) : null}

      <Card className="py-4">
        <CardContent className="px-4">
          <form
            className="flex flex-wrap items-end gap-3"
            onSubmit={(event) => {
              event.preventDefault();
              setAppliedPath(pathInput);
              setAppliedDuration(durationInput);
              setOffset(0);
            }}
          >
            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Khoảng thời gian
              </span>
              <select
                value={windowHours}
                onChange={(event) => {
                  setWindowHours(Number(event.target.value));
                  setOffset(0);
                }}
                className="h-9 rounded-md border border-[var(--border)] bg-[var(--surface)] px-3 text-sm text-foreground"
              >
                {WINDOW_OPTIONS.map((option) => (
                  <option key={option.hours} value={option.hours}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Đường dẫn chứa
              </span>
              <Input
                type="text"
                value={pathInput}
                placeholder="/api/v1/analyze"
                onChange={(event) => setPathInput(event.target.value)}
                className="h-9 w-56"
              />
            </label>

            <label className="flex flex-col gap-1.5">
              <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
                Chậm hơn
              </span>
              <Input
                type="number"
                min={0}
                value={durationInput}
                placeholder="3000 ms"
                onChange={(event) => setDurationInput(event.target.value)}
                className="h-9 w-32"
              />
            </label>

            {/* Bật lên thì thấy ngay là đang lọc, khỏi phải soi ô tick. */}
            <label
              className={cn(
                "flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border px-3 text-sm transition-colors",
                onlyLlmErrors
                  ? "border-[var(--brand)] bg-[var(--brand-soft)] font-medium text-[var(--brand-strong)]"
                  : "border-[var(--border)] text-[var(--foreground-secondary)] hover:border-[var(--border-strong)]",
              )}
            >
              <input
                type="checkbox"
                checked={onlyLlmErrors}
                onChange={(event) => {
                  setOnlyLlmErrors(event.target.checked);
                  setOffset(0);
                }}
                className="h-3.5 w-3.5 accent-[var(--brand)]"
              />
              Chỉ request có LLM lỗi
            </label>

            <label
              className={cn(
                "flex h-9 cursor-pointer select-none items-center gap-2 rounded-md border px-3 text-sm transition-colors",
                onlyServerErrors
                  ? "border-[var(--brand)] bg-[var(--brand-soft)] font-medium text-[var(--brand-strong)]"
                  : "border-[var(--border)] text-[var(--foreground-secondary)] hover:border-[var(--border-strong)]",
              )}
            >
              <input
                type="checkbox"
                checked={onlyServerErrors}
                onChange={(event) => {
                  setOnlyServerErrors(event.target.checked);
                  setOffset(0);
                }}
                className="h-3.5 w-3.5 accent-[var(--brand)]"
              />
              Chỉ lỗi 500
            </label>

            <Button type="submit" size="sm" className="ml-auto" disabled={loading}>
              Lọc
            </Button>
          </form>
        </CardContent>
      </Card>

      <Card className="overflow-hidden py-0">
        {/* Bảng rộng hơn màn hình hẹp là bình thường — cho nó cuộn trong khung
            của chính nó thay vì đẩy cả trang cuộn ngang. */}
        <div className="max-h-[62vh] overflow-auto">
          <table className="w-full border-separate border-spacing-0 text-sm">
            <thead>
              <tr>
                {["Thời điểm", "Request", "Mã", "Thời lượng", "CSDL", "LLM", "Vai trò", "request_id"].map(
                  (head, index) => (
                    <th
                      key={head}
                      className={cn(
                        "sticky top-0 z-10 whitespace-nowrap border-b border-[var(--border)] bg-[var(--surface-subtle)] px-3.5 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground",
                        index >= 3 && index <= 5 ? "text-right" : "text-left",
                      )}
                    >
                      {head}
                    </th>
                  ),
                )}
              </tr>
            </thead>
            <tbody>
              {traces.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-4 py-12 text-center text-sm text-muted-foreground">
                    {loading ? (
                      "Đang tải..."
                    ) : (
                      <>
                        <strong className="mb-1 block text-sm text-[var(--foreground-secondary)]">
                          Không có request nào khớp bộ lọc
                        </strong>
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
                    <tr
                      key={`${trace.request_id}-${trace.created_at}`}
                      onClick={() => router.push(`/admin/traces/${encodeURIComponent(trace.request_id)}`)}
                      className="cursor-pointer transition-colors hover:bg-[var(--surface-subtle)]"
                    >
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5 text-xs tabular-nums text-muted-foreground">
                        {formatClock(trace.created_at)}
                        <div className="text-[11px] text-[var(--foreground-muted)]">
                          {formatDay(trace.created_at)}
                        </div>
                      </td>
                      <td className="border-b border-[var(--border)]/60 px-3.5 py-2.5">
                        <span className="font-mono text-[11px] font-semibold tracking-wide text-muted-foreground">
                          {trace.method}
                        </span>
                        <div
                          className="max-w-[300px] truncate font-mono text-xs text-foreground"
                          title={trace.path}
                        >
                          {trace.path}
                        </div>
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5">
                        <Badge variant={statusVariant(trace.status_code)} className="tabular-nums">
                          {trace.status_code}
                        </Badge>
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5 text-right">
                        {/* Thanh nền sau cột thời lượng: quét mắt một cái là thấy
                            dòng nào chậm, không phải đọc từng con số. Tỉ lệ theo
                            dòng chậm nhất của TRANG đang xem. */}
                        <span className="relative inline-block min-w-[64px] overflow-hidden rounded px-2 py-1 text-right tabular-nums">
                          <span
                            className={cn(
                              "absolute inset-y-0 left-0",
                              trace.duration_ms >= 3000
                                ? "bg-[var(--status-abnormal-bg)]"
                                : "bg-[var(--brand-soft)]",
                            )}
                            style={{ width: `${share}%` }}
                            aria-hidden="true"
                          />
                          <span className="relative font-medium text-foreground">
                            {formatMs(trace.duration_ms)}
                          </span>
                        </span>
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5 text-right tabular-nums">
                        {trace.db_query_count}
                        <div className="text-[11px] text-[var(--foreground-muted)]">{formatMs(trace.db_ms)}</div>
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5 text-right tabular-nums">
                        {trace.llm_call_count > 0 ? (
                          <>
                            {trace.llm_call_count}
                            {trace.llm_error_count > 0 ? (
                              <span className="font-semibold text-[var(--status-critical-fg)]">
                                {" "}
                                · {trace.llm_error_count} lỗi
                              </span>
                            ) : null}
                            <div className="text-[11px] text-[var(--foreground-muted)]">
                              {formatMs(trace.llm_ms)}
                            </div>
                          </>
                        ) : (
                          <span className="text-[var(--foreground-muted)]">—</span>
                        )}
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5 text-xs text-muted-foreground">
                        {trace.user_role ?? "—"}
                      </td>
                      <td className="whitespace-nowrap border-b border-[var(--border)]/60 px-3.5 py-2.5">
                        {/* Cắt bằng CSS chứ KHÔNG cắt chuỗi trong JSX: select-all
                            chỉ copy được phần đã render, nên render 12 ký tự là
                            dán ra 12 ký tự vô dụng. */}
                        <code
                          className="inline-block max-w-[104px] cursor-text select-all truncate align-middle font-mono text-[11px] text-[var(--foreground-muted)]"
                          title={trace.request_id}
                          onClick={(event) => event.stopPropagation()}
                        >
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

        <div className="flex items-center justify-between gap-4 border-t border-[var(--border)] px-4 py-3 text-xs tabular-nums text-muted-foreground">
          <span>
            {total === 0
              ? "0 request"
              : `${offset + 1}–${Math.min(offset + PAGE_SIZE, total)} trên ${total} request`}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={offset === 0 || loading}
              onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
            >
              Trước
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={offset + PAGE_SIZE >= total || loading}
              onClick={() => setOffset(offset + PAGE_SIZE)}
            >
              Sau
            </Button>
          </div>
        </div>
      </Card>
    </div>
  );
}
