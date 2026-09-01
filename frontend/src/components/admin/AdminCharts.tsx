"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { Card, CardContent } from "@/components/ui/card";
import {
  categoricalColor,
  errorLabel,
  foldToMaxSeries,
} from "@/lib/chartPalette.mjs";
import type { TimeseriesPoint, Timeseries } from "@/types/admin";

/** Chế độ tối hiện tại. Bộ màu tối là bộ ĐƯỢC CHỌN riêng, không phải bản lật —
 * lật bộ sáng thì hai màu tụt xuống dưới ngưỡng tương phản 3:1 trên nền tối.
 *
 * Ba trạng thái, không phải hai: `data-theme` được đóng dấu khi người dùng chọn
 * rõ, còn mặc định "theo hệ thống" thì không đóng dấu gì và chỉ
 * `prefers-color-scheme` phân biệt được.
 */
function useDarkMode(): boolean {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const read = () => {
      const stamped = document.documentElement.getAttribute("data-theme");
      if (stamped === "dark") return setDark(true);
      if (stamped === "light") return setDark(false);
      return setDark(media.matches);
    };
    read();
    media.addEventListener("change", read);
    const observer = new MutationObserver(read);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      media.removeEventListener("change", read);
      observer.disconnect();
    };
  }, []);

  return dark;
}

const GRID = "var(--border)";
const AXIS_INK = "var(--muted-foreground)";

/** Nhãn trục thời gian. Chỉ giờ:phút khi mốc dưới một ngày — ngày tháng lặp lại
 * trên mọi nhãn chỉ chiếm chỗ mà không phân biệt được điểm nào với điểm nào. */
function timeLabel(iso: string, bucketMinutes: number): string {
  const at = new Date(iso);
  if (Number.isNaN(at.getTime())) return iso;
  const hhmm = at.toLocaleTimeString("vi-VN", { hour: "2-digit", minute: "2-digit" });
  if (bucketMinutes >= 24 * 60) {
    return at.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" });
  }
  if (bucketMinutes >= 6 * 60) {
    return `${at.toLocaleDateString("vi-VN", { day: "2-digit", month: "2-digit" })} ${hhmm}`;
  }
  return hhmm;
}

function ChartFrame({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <Card className="gap-0 py-4">
      <CardContent className="px-4">
        <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
          <span className="text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {title}
          </span>
          <span className="text-xs text-muted-foreground">{hint}</span>
        </div>
        <div className="h-56 w-full">{children}</div>
      </CardContent>
    </Card>
  );
}

/** Không có dữ liệu thì nói ra, không vẽ một biểu đồ trống trông như hệ thống êm. */
function EmptyPlot({ message }: { message: string }) {
  return (
    <p className="m-0 flex h-full items-center justify-center text-center text-sm text-muted-foreground">
      {message}
    </p>
  );
}

const TOOLTIP_STYLE = {
  backgroundColor: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  fontSize: 12,
} as const;

function hasAny(points: TimeseriesPoint[], key: keyof TimeseriesPoint): boolean {
  return points.some((p) => p[key] !== null && p[key] !== undefined && p[key] !== 0);
}

/** 1. Độ trễ theo phân vị, theo thời gian.
 *
 * Ba hue phân loại đã qua validator, KHÔNG phải ba bậc của một hue. Dải một hue
 * là lựa chọn đầu tiên vì phân vị có thứ tự, nhưng đo lại thì bậc nhạt nhất chỉ
 * đạt contrast 2.59 (dưới 3:1) và ΔE giữa hai bậc đậm là 14.3 — dưới sàn 15,
 * tức ngay cả thị lực bình thường cũng khó phân biệt. Thứ tự được nhấn bằng ĐỘ
 * DÀY: P95 vẽ 2px vì nó là con số SLO gắn vào.
 */
function LatencyChart({ series, dark }: { series: Timeseries; dark: boolean }) {
  const data = series.points.map((p) => ({
    label: timeLabel(p.start, series.bucket_minutes),
    p50: p.p50_ms === null ? null : Math.round(p.p50_ms),
    p95: p.p95_ms === null ? null : Math.round(p.p95_ms),
    p99: p.p99_ms === null ? null : Math.round(p.p99_ms),
  }));

  if (!hasAny(series.points, "p95_ms")) {
    return <EmptyPlot message="Chưa có request nào đi qua đường AI trong khoảng này." />;
  }

  const lines = [
    { key: "p95", name: "P95", width: 2 },
    { key: "p50", name: "P50", width: 1.5 },
    { key: "p99", name: "P99", width: 1.5 },
  ];

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -12 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS_INK }} stroke={GRID} interval="preserveStartEnd" />
        <YAxis
          tick={{ fontSize: 11, fill: AXIS_INK }}
          stroke={GRID}
          tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${v}ms`)}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value, name) => [`${Number(value ?? 0)} ms`, String(name)]}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {/* Ngưỡng SLO độ trễ. Vẽ ra để P95 có mốc so, chứ một đường 6.6s không
            tự nói được nó tốt hay xấu. */}
        <ReferenceLine
          y={8000}
          stroke="var(--status-abnormal-border)"
          strokeDasharray="6 4"
          label={{ value: "SLO 8s", position: "insideTopRight", fontSize: 10, fill: AXIS_INK }}
        />
        {lines.map((line, index) => (
          <Line
            key={line.key}
            type="monotone"
            dataKey={line.key}
            name={line.name}
            stroke={categoricalColor(index, dark) ?? undefined}
            strokeWidth={line.width}
            dot={false}
            activeDot={{ r: 4 }}
            connectNulls={false}
            isAnimationActive={false}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}

/** 2. Lỗi theo nhóm, theo thời gian. Cột xếp chồng — cùng đơn vị, một trục. */
function ErrorsChart({ series, dark }: { series: Timeseries; dark: boolean }) {
  const folded = useMemo(() => {
    const totals = new Map<string, number>();
    for (const point of series.points) {
      for (const [key, count] of Object.entries(point.errors_by_type ?? {})) {
        totals.set(key, (totals.get(key) ?? 0) + count);
      }
    }
    const entries = [...totals.entries()]
      .map(([key, count]) => ({ key, count }))
      .sort((a, b) => b.count - a.count);
    return foldToMaxSeries(entries) as Array<{ key: string; count: number }>;
  }, [series.points]);

  const keptKeys = new Set(folded.map((f) => f.key));

  const data = series.points.map((point) => {
    const row: Record<string, string | number> = {
      label: timeLabel(point.start, series.bucket_minutes),
    };
    for (const item of folded) row[item.key] = 0;
    for (const [key, count] of Object.entries(point.errors_by_type ?? {})) {
      // Nhóm bị gộp thì cộng vào "Khác" thay vì bỏ — bỏ đi làm tổng trên biểu đồ
      // nhỏ hơn tổng trên card và người đọc không biết vì sao lệch.
      const target = keptKeys.has(key) ? key : "Khác";
      row[target] = ((row[target] as number) ?? 0) + count;
    }
    return row;
  });

  if (folded.length === 0) {
    return <EmptyPlot message="Không có lỗi nào trong khoảng này. Đây là tin tốt, không phải thiếu dữ liệu." />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS_INK }} stroke={GRID} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 11, fill: AXIS_INK }} stroke={GRID} allowDecimals={false} />
        <Tooltip contentStyle={TOOLTIP_STYLE} />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {folded.map((item, index) => (
          <Bar
            key={item.key}
            dataKey={item.key}
            name={errorLabel(item.key)}
            stackId="errors"
            fill={categoricalColor(index, dark) ?? undefined}
            // Khe 2px giữa các đoạn xếp chồng, theo đúng đặc tả mark: không có
            // khe thì hai đoạn màu gần nhau đọc thành một khối liền.
            stroke="var(--surface)"
            strokeWidth={2}
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 3. Token theo thời gian, chi phí trong tooltip.
 *
 * KHÔNG dùng hai trục y. Token (đơn vị đếm) và tiền (USD) khác thang hoàn toàn,
 * và biểu đồ hai trục cho phép đặt hai đường cạnh nhau ở bất kỳ tỉ lệ nào — tức
 * là để người vẽ quyết định câu chuyện thay vì để dữ liệu quyết định.
 *
 * Token vào và token ra thì CÙNG đơn vị nên xếp chồng được, và chi phí đi vào
 * tooltip: nó suy ra tuyến tính từ token nên vẽ riêng một đường gần như trùng
 * hình là thêm mực mà không thêm thông tin.
 */
function TokenCostChart({ series, dark }: { series: Timeseries; dark: boolean }) {
  const data = series.points.map((p) => ({
    label: timeLabel(p.start, series.bucket_minutes),
    input: p.input_tokens,
    output: p.output_tokens,
    cost: p.cost_usd,
  }));

  if (!hasAny(series.points, "input_tokens") && !hasAny(series.points, "output_tokens")) {
    return <EmptyPlot message="Chưa đếm được token nào trong khoảng này." />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -8 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS_INK }} stroke={GRID} interval="preserveStartEnd" />
        <YAxis
          tick={{ fontSize: 11, fill: AXIS_INK }}
          stroke={GRID}
          tickFormatter={(v: number) => (v >= 1000 ? `${(v / 1000).toFixed(0)}k` : String(v))}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value, name) => {
            if (String(name) === "Chi phí") {
              // `null` = chưa có giá cho model, khác hẳn $0.00 (miễn phí).
              return [value == null ? "chưa có giá" : `$${Number(value).toFixed(5)}`, String(name)];
            }
            return [`${Number(value ?? 0).toLocaleString("vi-VN")} token`, String(name)];
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar
          dataKey="input"
          name="Token vào"
          stackId="tokens"
          fill={categoricalColor(0, dark) ?? undefined}
          stroke="var(--surface)"
          strokeWidth={2}
          radius={[0, 0, 0, 0]}
          isAnimationActive={false}
        />
        <Bar
          dataKey="output"
          name="Token ra"
          stackId="tokens"
          fill={categoricalColor(1, dark) ?? undefined}
          stroke="var(--surface)"
          strokeWidth={2}
          radius={[2, 2, 0, 0]}
          isAnimationActive={false}
        />
        {/* Chi phí chỉ hiện trong tooltip: nó suy ra tuyến tính từ token nên một
            đường riêng gần như trùng hình, mà lại đòi trục thứ hai. */}
        <Bar dataKey="cost" name="Chi phí" fill="transparent" stackId="hidden" legendType="none" isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  );
}

/** 4. Chất lượng theo thời gian — tỉ lệ lượt phải thay bằng văn bản dựng sẵn.
 *
 * ĐÂY KHÔNG PHẢI groundedness. Groundedness cần một bộ đánh giá trực tuyến chấm
 * điểm từng câu trả lời, mà hệ thống chưa có; đặt một con số phần trăm về độ
 * đúng y khoa mà không đo được là loại bịa nguy hiểm nhất.
 *
 * Cái đo được thật: guardrail phải thay văn bản của LLM bằng văn bản dựng sẵn
 * bao nhiêu lần. Khác 0 nghĩa là bệnh nhân nhận nội dung xuống cấp trong khi
 * response vẫn 200 và không có mã lỗi nào — đúng cái bẫy CLAUDE.md ghi lại.
 *
 * Một series nên KHÔNG có legend: tiêu đề đã gọi tên nó.
 */
function QualityChart({ series, dark }: { series: Timeseries; dark: boolean }) {
  const data = series.points.map((p) => ({
    label: timeLabel(p.start, series.bucket_minutes),
    rate: p.guardrail_fallback_rate_pct,
    groundedness: p.groundedness_pct,
    faithfulness: p.faithfulness_pct,
    relevance: p.relevance_pct,
  }));

  const measured = series.points.some((p) => p.guardrail_fallback_rate_pct !== null || p.groundedness_pct !== null);
  if (!measured) {
    return <EmptyPlot message="Chưa có lượt trả lời nào để đo trong khoảng này." />;
  }

  return (
    <ResponsiveContainer width="100%" height="100%">
      <LineChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: -20 }}>
        <CartesianGrid stroke={GRID} strokeDasharray="4 4" vertical={false} />
        <XAxis dataKey="label" tick={{ fontSize: 11, fill: AXIS_INK }} stroke={GRID} interval="preserveStartEnd" />
        <YAxis
          tick={{ fontSize: 11, fill: AXIS_INK }}
          stroke={GRID}
          tickFormatter={(v: number) => `${v}%`}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value) => [`${Number(value ?? 0)}%`, "Phải thay văn bản"]}
        />
        <ReferenceLine
          y={2}
          stroke="var(--status-abnormal-border)"
          strokeDasharray="6 4"
          label={{ value: "SLO 2%", position: "insideTopRight", fontSize: 10, fill: AXIS_INK }}
        />
        <Line
          type="monotone"
          dataKey="rate"
          stroke={categoricalColor(3, dark) ?? undefined}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
          connectNulls={false}
          isAnimationActive={false}
        />
        <Line type="monotone" dataKey="groundedness" name="Groundedness" stroke={categoricalColor(0, dark) ?? undefined} dot={false} connectNulls={false} />
        <Line type="monotone" dataKey="faithfulness" name="Faithfulness" stroke={categoricalColor(1, dark) ?? undefined} dot={false} connectNulls={false} />
        <Line type="monotone" dataKey="relevance" name="Relevance" stroke={categoricalColor(2, dark) ?? undefined} dot={false} connectNulls={false} />
      </LineChart>
    </ResponsiveContainer>
  );
}

export default function AdminCharts({ series }: { series: Timeseries }) {
  const dark = useDarkMode();
  const chatDegraded = series.points.reduce((sum, point) => sum + (point.chat_degraded_count ?? 0), 0);
  const chatBlocked = series.points.reduce((sum, point) => sum + (point.chat_blocked_count ?? 0), 0);
  const blockedReasons = series.points.reduce<Record<string, number>>((totals, point) => {
    Object.entries(point.chat_blocked_reasons ?? {}).forEach(([reason, count]) => {
      totals[reason] = (totals[reason] ?? 0) + count;
    });
    return totals;
  }, {});
  const safetyEscapes = series.points.reduce((sum, point) => sum + (point.safety_final_escape_count ?? 0), 0);
  const judgeSamples = series.points.reduce((sum, point) => sum + (point.judge_sample_count ?? 0), 0);
  const ragRetrievals = series.points.reduce((sum, point) => sum + (point.rag_retrieval_count ?? 0), 0);
  const ragLatency = series.points.reduce((sum, point) => sum + (point.rag_retrieval_ms ?? 0), 0);
  const ragSources = series.points.reduce((sum, point) => sum + (point.rag_source_count ?? 0), 0);
  const ragTopK = Math.max(0, ...series.points.map((point) => point.rag_top_k ?? 0));

  return (
    <section className="grid grid-cols-1 gap-3 xl:grid-cols-2">
      <div className="rounded-lg border border-[var(--border)] bg-[var(--surface)] p-4 xl:col-span-2">
        <p className="text-sm font-semibold">
          Trạng thái RAG: {series.rag_status === "disabled" ? "ĐANG TẮT" : (series.rag_status ?? "CHƯA ĐO ĐƯỢC")}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          Judge samples: {judgeSamples} · Safety Final Escape: {safetyEscapes} · RAG usage: {ragRetrievals}
          {series.rag_status === "disabled" ? "" : ` · top-k ${ragTopK} · ${ragLatency.toFixed(1)}ms · ${ragSources} nguồn`}
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {series.rag_status === "disabled"
            ? "Production không chạy RAG, vì vậy chưa có groundedness hay retrieval để đo; số 0 không được hiểu là hệ thống đang khỏe."
            : `RAG ${series.rag_required ? "là thành phần bắt buộc" : "là thành phần tùy chọn"}; groundedness vẫn chưa được chấm tự động.`}
        </p>
        <p className="mt-2 text-xs text-muted-foreground">
          Chat suy giảm: {chatDegraded} · Chat bị chặn: {chatBlocked}
          {Object.keys(blockedReasons).length
            ? ` · Lý do: ${Object.entries(blockedReasons).map(([reason, count]) => `${reason} ${count}`).join(", ")}`
            : ""}
        </p>
      </div>
      <ChartFrame
        title="Độ trễ đường AI theo phân vị"
        hint={`mốc ${series.bucket_minutes} phút`}
      >
        <LatencyChart series={series} dark={dark} />
      </ChartFrame>

      <ChartFrame title="Lỗi theo nhóm" hint="chỉ 5xx">
        <ErrorsChart series={series} dark={dark} />
      </ChartFrame>

      <ChartFrame title="Token, chi phí trong tooltip" hint="một trục — token và tiền khác thang">
        <TokenCostChart series={series} dark={dark} />
      </ChartFrame>

      <ChartFrame
        title="Chat quality theo thời gian"
        hint="fallback và LLM-as-Judge sampling"
      >
        <QualityChart series={series} dark={dark} />
      </ChartFrame>
    </section>
  );
}
