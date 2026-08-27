"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AlertTriangle, RefreshCw, Search } from "lucide-react";
import {
  ForbiddenError,
  UnauthorizedError,
  clearSession,
  fetchTraceLatency,
  fetchTraceSlo,
  fetchTraceTimeseries,
  fetchTraceSummary,
  fetchTraces,
  fetchTracingStatus,
} from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import AdminCharts from "@/components/admin/AdminCharts";
import { errorLabel } from "@/lib/chartPalette.mjs";
import { cn } from "@/lib/utils";
import type {
  LatencyGroup,
  LatencyGroups,
  RequestTrace,
  SloReport,
  Timeseries,
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

// `ReactNode` chu khong chi `string | number`: o "Trang thai SLO" can to mau
// rieng cho tung trang thai, va nhet mau vao trong chuoi thi khong lam duoc.
type KpiProps = { label: string; value: React.ReactNode; hint: string; alert?: boolean };

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

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

/** Chi phí LLM: token và tiền.
 *
 * Trước đây màn này chỉ có "GỌI LLM: 27 lượt" — biết số lượt mà không biết tốn
 * bao nhiêu tiền, endpoint nào tốn nhất.
 *
 * Hai điều bảng này phải nói thật:
 *
 * 1. `cost_usd === null` hiện dấu gạch kèm lời giải thích, KHÔNG hiện "$0.00".
 *    `$0.00` đọc như miễn phí, dấu gạch đọc như không biết.
 * 2. `unpriced_call_count > 0` phải cảnh báo: con số chi phí đang báo thấp hơn
 *    thực tế vì có lượt gọi model chưa có trong bảng giá.
 */
const SLO_TONE: Record<string, { label: string; cls: string }> = {
  HEALTHY: { label: "ỔN", cls: "text-[var(--status-normal-fg)]" },
  AT_RISK: { label: "SẮP HẾT NGÂN SÁCH", cls: "text-[var(--status-abnormal-fg)]" },
  BREACHED: { label: "VI PHẠM", cls: "text-[var(--status-critical-fg)]" },
  NO_DATA: { label: "CHƯA CÓ DỮ LIỆU", cls: "text-muted-foreground" },
};

function sloByName(slo: SloReport, name: string) {
  return slo.slos.find((item) => item.name === name) ?? null;
}

/** Sáu ô trả lời "có vấn đề không" trong một cái nhìn.
 *
 * Không có ô "Trung bình", và không có ô "Gọi LLM" trần: cả hai đều là con số
 * đúng mà trả lời sai câu hỏi. Sáu ô ở đây đều là con số có ngưỡng để so.
 */
function KpiRow({ latency, slo }: { latency: LatencyGroups; slo: SloReport }) {
  const ai = latency.ai;
  const quality = sloByName(slo, "quality");
  const tone = SLO_TONE[slo.overall_status] ?? SLO_TONE.NO_DATA;

  const p95 = ai.p95_ms;
  const errorRate = ai.error_rate_pct;

  return (
    <section className="grid grid-cols-2 gap-3 sm:grid-cols-3">
      <Kpi
        label="Tần suất request"
        value={ai.requests_per_min === null ? "—" : `${ai.requests_per_min}/phút`}
        hint="chỉ đường AI"
      />
      <Kpi
        label="P95 độ trễ"
        value={p95 === null ? "—" : p95 >= 1000 ? `${(p95 / 1000).toFixed(2)}s` : `${Math.round(p95)}ms`}
        hint="SLO: dưới 8s"
        alert={p95 !== null && p95 >= 8000}
      />
      <Kpi
        label="Tỉ lệ lỗi"
        value={errorRate === null ? "—" : `${errorRate}%`}
        hint="chỉ 5xx · SLO: dưới 0.5%"
        alert={errorRate !== null && errorRate > 0.5}
      />
      <Kpi
        label="Chi phí LLM"
        value={ai.cost_usd === null ? "—" : `$${ai.cost_usd.toFixed(4)}`}
        hint={ai.unpriced_call_count > 0 ? "đang báo THẤP hơn thực tế" : "ước lượng theo bảng giá"}
        alert={ai.unpriced_call_count > 0}
      />
      <Kpi
        label="Không phải thay văn bản"
        value={quality?.actual_pct === null || quality === null ? "—" : `${quality.actual_pct}%`}
        hint="đo được — KHÔNG phải groundedness"
        alert={quality?.status === "BREACHED"}
      />
      <Kpi
        label="Trạng thái SLO"
        value={<span className={tone.cls}>{tone.label}</span>}
        hint={`lấy theo SLO tệ nhất trong ${slo.slos.length}`}
        alert={slo.overall_status === "BREACHED"}
      />
    </section>
  );
}

/** SLO, error budget, và phân bố nhóm lỗi.
 *
 * Error budget mới là phần đổi cách làm việc: SLO 99.5% nghĩa là ĐƯỢC PHÉP 0.5%
 * lỗi, và ngân sách biến con số đó thành một lượng cụ thể. Hết ngân sách thì
 * việc cần làm không phải bàn xem 0.5% có hợp lý không, mà là dừng thả tính năng.
 */
function SloPanel({ slo }: { slo: SloReport }) {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            SLO và ngân sách lỗi
          </span>
          {slo.thresholds_provisional ? (
            /* Nói ra rằng ngưỡng chưa được nhóm chốt. Trình bày một ngưỡng đề
               xuất như đã thống nhất là cách chắc nhất để sau này không ai dám
               sửa nó, kể cả khi số đo cho thấy nó sai. */
            <span className="text-xs text-[var(--status-abnormal-fg)]">
              Ngưỡng là ĐỀ XUẤT, chọn từ số đo thật — nhóm cần chốt lại
            </span>
          ) : null}
        </div>

        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] border-collapse text-sm tabular-nums">
            <thead>
              <tr className="border-b border-[var(--border)] text-left text-[11px] uppercase tracking-wider text-muted-foreground">
                <th className="py-2 pr-3 font-semibold">SLO</th>
                <th className="py-2 px-3 text-right font-semibold">Mục tiêu</th>
                <th className="py-2 px-3 text-right font-semibold">Thực tế</th>
                <th className="py-2 px-3 text-right font-semibold">Ngân sách đã dùng</th>
                <th className="py-2 pl-3 text-right font-semibold">Còn lại</th>
              </tr>
            </thead>
            <tbody>
              {slo.slos.map((item) => {
                const tone = SLO_TONE[item.status] ?? SLO_TONE.NO_DATA;
                const over = (item.budget_used_pct ?? 0) > 100;
                return (
                  <tr key={item.name} className="border-b border-[var(--border)]/50 last:border-0">
                    <td className="py-2.5 pr-3">
                      <span className="block font-medium text-foreground">{item.detail}</span>
                      <span className={cn("block text-xs", tone.cls)}>{tone.label}</span>
                    </td>
                    <td className="py-2.5 px-3 text-right text-muted-foreground">{item.target_pct}%</td>
                    <td className="py-2.5 px-3 text-right font-semibold">
                      {item.actual_pct === null ? <span className="text-muted-foreground">—</span> : `${item.actual_pct}%`}
                    </td>
                    <td className={cn("py-2.5 px-3 text-right", over && "font-semibold text-[var(--status-critical-fg)]")}>
                      {item.budget_used_pct === null ? "—" : `${item.budget_used_pct}%`}
                    </td>
                    <td className="py-2.5 pl-3 text-right text-muted-foreground">
                      {item.budget_remaining === null ? "—" : item.budget_remaining}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>

        {slo.errors.length > 0 ? (
          <div className="mt-4 border-t border-[var(--border)] pt-3">
            {/* Bien card "Loi 5xx = 3" thanh doc duoc: ba loi do la gi. */}
            <span className="mb-2 block text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
              Lỗi theo nhóm
            </span>
            <ul className="m-0 flex list-none flex-col gap-1 p-0 text-sm">
              {slo.errors.map((item) => (
                <li key={item.error_type} className="flex items-baseline justify-between gap-3">
                  <span>
                    {errorLabel(item.error_type)}
                    {item.example_exception ? (
                      <code className="ml-2 font-mono text-xs text-muted-foreground">
                        {item.example_exception}
                      </code>
                    ) : null}
                  </span>
                  <span className="tabular-nums font-medium">{item.count}</span>
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

function CostPanel({ latency }: { latency: LatencyGroups }) {
  const ai = latency.ai;
  const totalTokens = ai.input_tokens + ai.output_tokens;
  const unpriced = ai.unpriced_call_count;

  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            Chi phí LLM
          </span>
          <span className="text-xs text-muted-foreground">
            {/* Giá là số CẤU HÌNH, không phải số đo được — nhà cung cấp đổi giá
                mà không hỏi ai. Nói ngày cập nhật để người đọc biết nó cũ bao
                nhiêu, thay vì trình bày như sự thật đo lường. */}
            Ước lượng theo bảng giá cập nhật {latency.pricing_updated ?? "—"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
          <div>
            <span className="block text-xs text-muted-foreground">Token vào</span>
            <strong className="block text-lg font-semibold tabular-nums">
              {formatTokens(ai.input_tokens)}
            </strong>
          </div>
          <div>
            <span className="block text-xs text-muted-foreground">Token ra</span>
            <strong className="block text-lg font-semibold tabular-nums">
              {formatTokens(ai.output_tokens)}
            </strong>
          </div>
          <div>
            <span className="block text-xs text-muted-foreground">Chi phí</span>
            <strong className="block text-lg font-semibold tabular-nums">
              {ai.cost_usd === null ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                `$${ai.cost_usd.toFixed(4)}`
              )}
            </strong>
          </div>
          <div>
            <span className="block text-xs text-muted-foreground">Mỗi lượt gọi</span>
            <strong className="block text-lg font-semibold tabular-nums">
              {ai.cost_per_call_usd === null ? (
                <span className="text-muted-foreground">—</span>
              ) : (
                `$${ai.cost_per_call_usd.toFixed(5)}`
              )}
            </strong>
          </div>
        </div>

        {ai.cost_usd === null && totalTokens > 0 ? (
          <p className="m-0 mt-3 text-xs leading-relaxed text-muted-foreground">
            Đã đếm được {formatTokens(totalTokens)} token nhưng chưa có giá cho model đang dùng, nên
            không quy ra tiền được. Token thì đo được, giá thì phải khai trong{" "}
            <code className="font-mono">llm_cost.py</code>.
          </p>
        ) : null}

        {unpriced > 0 ? (
          <p className="m-0 mt-3 rounded border border-[var(--status-abnormal-border)] bg-[var(--status-abnormal-bg)] px-3 py-2 text-xs leading-relaxed text-[var(--status-abnormal-fg)]">
            {unpriced} lượt gọi dùng model chưa có trong bảng giá nên bị bỏ ngoài phép tính. Con số
            chi phí ở trên đang <strong>thấp hơn thực tế</strong>.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
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
  const [series, setSeries] = useState<Timeseries | null>(null);
  const [slo, setSlo] = useState<SloReport | null>(null);
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

      const [statusData, summaryData, latencyData, seriesData, sloData, listData] = await Promise.all([
        fetchTracingStatus(),
        fetchTraceSummary(windowHours),
        fetchTraceLatency(windowHours),
        fetchTraceTimeseries(windowHours),
        fetchTraceSlo(windowHours),
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
      setSeries(seriesData);
      setSlo(sloData);
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

      {/* Thu tu man hinh, theo dung muc tieu "biet he thong dang xau di truoc
          khi user phan anh": SAU CARD tra loi "co van de khong" trong mot cai
          nhin, BON BIEU DO tra loi "xau di tu bao gio", roi moi den BANG TRACE
          de dao vao mot request cu the. Dat bang truoc thi nguoi mo man hinh
          bat dau bang viec doc 1213 dong log. */}
      {latency && slo ? <KpiRow latency={latency} slo={slo} /> : null}

      {slo ? <SloPanel slo={slo} /> : null}

      {series ? <AdminCharts series={series} /> : null}

      {latency ? <LatencyTable latency={latency} /> : null}

      {latency ? <CostPanel latency={latency} /> : null}

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
