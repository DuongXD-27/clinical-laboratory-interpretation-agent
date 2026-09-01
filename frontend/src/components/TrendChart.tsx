"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { assessmentText, dedupeTrendPoints, formatTrendDate } from "@/lib/trendUi.mjs";
import {
  formatClinicalUnit,
  formatClinicalUnitSuffix,
  formatClinicalValue,
} from "@/lib/clinicalUnit.mjs";
import type { TrendPoint } from "@/types/analysis";

/** Minimum number of on-chart points before the chart is allowed to fill the full container width. */
const MIN_POINTS_FOR_FULL_WIDTH = 4;
/** Pixel width budget per point below that threshold, so a 2-3 point chart doesn't look like an empty void. */
const NARROW_WIDTH_PER_POINT = 220;
const NARROW_WIDTH_MIN = 360;

/* ── Types ─────────────────────────────────────────── */

type ChartPoint = TrendPoint & {
  timestamp: number;
};

/** One analyte worth of data for the multi-line chart. */
export type AnalyteDataset = {
  analyte: string;
  display_name?: string;
  unit: string;
  points: TrendPoint[];
  color?: string;
};

type TooltipPayload = {
  payload?: ChartPoint | Record<string, number | null>;
  dataKey?: string;
  color?: string;
  value?: number;
};

type TrendTooltipProps = {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number;
  unit: string;
  analytes: string;
};

type TrendChartProps = {
  height?: number;
} & (
  | {
      analyte: string;
      unit: string;
      points: TrendPoint[];
      /** Khoảng "bình thường" khớp theo sex/age tại lần đo gần nhất (ADR-010 CRIT-TREND-02). */
      referenceLow?: number | null;
      referenceHigh?: number | null;
      /** Ngưỡng nguy kịch active, cùng đơn vị với `unit` (ADR-010 CRIT-TREND-03/05). */
      criticalLow?: number | null;
      criticalHigh?: number | null;
    }
  | { analytes: AnalyteDataset[] }
);

/* ── Color palette (colorblind-safe, 8 colors) ────── */

const CHART_COLORS = [
  "#1769e0", // blue
  "#dc2626", // red
  "#16a34a", // green
  "#ea580c", // orange
  "#9333ea", // purple
  "#0891b2", // cyan
  "#db2777", // pink
  "#65a30d", // lime
];

/* ── Tooltip ─────────────────────────────────────── */

/** Tooltip for single-analyte charts (legacy). */
function TrendTooltipSingle({ active, payload, label, unit, analytes }: TrendTooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0];
  if (!point) return null;
  const chartPoint = point as unknown as ChartPoint;
  const value = chartPoint.value ?? (point.value ?? null);
  const assessment = (chartPoint as TrendPoint).assessment ?? "";
  if (value === null || value === undefined) return null;

  return (
    <div className="trend-tooltip">
      <p className="font-semibold text-slate-950">{formatTrendDate(label ?? chartPoint.timestamp)}</p>
      <p className="mt-1 text-sm text-slate-700">
        {analytes}: <span className="font-semibold">{value}</span> {formatClinicalUnitSuffix(unit)}
      </p>
      <p className="mt-1 text-xs text-slate-500">Trạng thái: {assessmentText(assessment)}</p>
    </div>
  );
}

/** Tooltip for multi-analyte charts — lists every analyte at the hovered timestamp. */
function TrendTooltipGroup({ active, payload, label, unit, analytes }: TrendTooltipProps) {
  if (!active || !payload?.length) return null;
  const ts = payload[0];
  if (!ts) return null;

  const chartPoint = ts as unknown as ChartPoint;
  return (
    <div className="trend-tooltip">
      <p className="font-semibold text-slate-950">
        {formatTrendDate(label ?? chartPoint.timestamp)}
      </p>
      {payload.map((entry, idx) => {
        const val = entry.value ?? null;
        if (val === null || val === undefined) return null;
        const analyteName = entry.dataKey ?? analytes.split(", ")[idx] ?? "";
        return (
          <p key={String(analyteName)} className="mt-1 text-sm text-slate-700">
            <span
              className="inline-block w-2 h-2 rounded-full mr-1"
              style={{ backgroundColor: entry.color ?? "#94a3b8" }}
            />
            {analyteName}:{" "}
            <span className="font-semibold">{val}</span> {formatClinicalUnitSuffix(unit)}
          </p>
        );
      })}
    </div>
  );
}

/* ── Legend ──────────────────────────────────────── */

function TrendLegend({ analytes, colors }: { analytes: string[]; colors: string[] }) {
  return (
    <div className="trend-legend">
      {analytes.map((item, idx) => (
        <span key={item} className="trend-legend-item">
          <span
            className="trend-legend-swatch"
            style={{ backgroundColor: colors[idx % colors.length] }}
          />
          {item}
        </span>
      ))}
    </div>
  );
}

/* ── Status-colored dots (single-analyte chart) ──── */

/** Maps an indicator's clinical assessment to a color, so abnormal points read at a glance. */
function statusColor(assessment?: string): string {
  switch (assessment) {
    case "critical_high":
    case "critical_low":
      return "#dc2626"; // red-600
    case "high":
    case "low":
      return "#d97706"; // amber-600
    case "normal":
      return "#16a34a"; // green-600
    default:
      return "#94a3b8"; // slate-400 — unknown/unassessed
  }
}

type StatusDotProps = { cx?: number; cy?: number; payload?: ChartPoint };

function StatusDot({ cx, cy, payload, radius }: StatusDotProps & { radius: number }) {
  if (cx === undefined || cy === undefined) return null;
  const color = statusColor(payload?.assessment);
  return <circle cx={cx} cy={cy} r={radius} fill={color} stroke="#fff" strokeWidth={2} />;
}

/* ── "% change vs. previous reading" summary ─────── */

type PercentChange = { pct: number; direction: "up" | "down" | "flat" };

function latestPercentChange(chartData: ChartPoint[]): PercentChange | null {
  if (chartData.length < 2) return null;
  const previous = chartData[chartData.length - 2].value;
  const latest = chartData[chartData.length - 1].value;
  if (!previous) return null;
  const pct = ((latest - previous) / previous) * 100;
  if (Math.round(pct * 10) === 0) return { pct: 0, direction: "flat" };
  return { pct: Math.abs(pct), direction: pct > 0 ? "up" : "down" };
}

function PercentChangeBadge({ change }: { change: PercentChange | null }) {
  if (!change) return null;
  if (change.direction === "flat") {
    return <p className="mb-2 text-xs text-slate-500">Không đổi so với lần đo trước</p>;
  }
  const isUp = change.direction === "up";
  return (
    <p className="mb-2 text-xs font-medium text-slate-600">
      {isUp ? "▲" : "▼"} {change.pct.toFixed(1)}% so với lần đo trước
    </p>
  );
}

/* ── Data merge for multi-analyte ───────────────── */

/**
 * Merge several analyte datasets into a unified recharts data array.
 * Each timestamp gets one object; each analyte contributes a `value` field
 * keyed by its name. Points that don't exist for a given timestamp are `null`.
 */
function buildMultiDatasetData(analytes: AnalyteDataset[]): ChartPoint[] {
  const allDates = new Set<string>();
  analytes.forEach((ds) =>
    ds.points.forEach((p) => allDates.add(p.test_date)),
  );

  return Array.from(allDates)
    .sort()
    .map((test_date) => {
      const obj: Record<string, unknown> = {
        test_date,
        timestamp: new Date(`${test_date}T00:00:00`).getTime(),
      };
      analytes.forEach((ds) => {
        obj[ds.analyte] = ds.points.find((p) => p.test_date === test_date)?.value ?? null;
      });
      return obj as unknown as ChartPoint;
    });
}

/** Earliest recorded value for an analyte — the baseline a normalized chart indexes against. */
function firstBaseline(ds: AnalyteDataset): number | null {
  const sorted = [...ds.points].sort((a, b) => a.test_date.localeCompare(b.test_date));
  const first = sorted.find((p) => typeof p.value === "number");
  return first ? first.value : null;
}

/**
 * Same shape as `buildMultiDatasetData`, but each series is expressed as % change from its
 * own baseline instead of its raw value. Used when 3+ same-unit analytes have wildly
 * different magnitudes (e.g. HbA1c ~5-7 vs. glucose ~4-10 vs. a hormone ~0.01) — plotted on
 * a shared linear axis, the smaller series would otherwise look like a flat line at the
 * bottom. The raw value is kept alongside (`${name}__abs`) so the tooltip can still show it.
 */
function buildNormalizedMultiDatasetData(
  analytes: AnalyteDataset[],
  baselines: Record<string, number>,
): ChartPoint[] {
  const allDates = new Set<string>();
  analytes.forEach((ds) => ds.points.forEach((p) => allDates.add(p.test_date)));

  return Array.from(allDates)
    .sort()
    .map((test_date) => {
      const obj: Record<string, unknown> = {
        test_date,
        timestamp: new Date(`${test_date}T00:00:00`).getTime(),
      };
      analytes.forEach((ds) => {
        const match = ds.points.find((p) => p.test_date === test_date);
        const baseline = baselines[ds.analyte];
        obj[ds.analyte] = match ? ((match.value - baseline) / baseline) * 100 : null;
        obj[`${ds.analyte}__abs`] = match ? match.value : null;
      });
      return obj as unknown as ChartPoint;
    });
}

type NormalizedTooltipProps = {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number;
  unit: string;
};

/** Tooltip for the normalized (%-change) multi-analyte chart — shows both % and the raw value. */
function TrendTooltipNormalized({ active, payload, label, unit }: NormalizedTooltipProps) {
  if (!active || !payload?.length) return null;
  const ts = payload[0];
  if (!ts) return null;
  const chartPoint = ts as unknown as ChartPoint;

  return (
    <div className="trend-tooltip">
      <p className="font-semibold text-slate-950">{formatTrendDate(label ?? chartPoint.timestamp)}</p>
      {payload.map((entry) => {
        const pct = entry.value ?? null;
        if (pct === null || pct === undefined) return null;
        const name = String(entry.dataKey ?? "");
        const abs = (entry.payload as Record<string, number | null> | undefined)?.[`${name}__abs`];
        return (
          <p key={name} className="mt-1 text-sm text-slate-700">
            <span
              className="inline-block w-2 h-2 rounded-full mr-1"
              style={{ backgroundColor: entry.color ?? "#94a3b8" }}
            />
            {name}: <span className="font-semibold">{pct > 0 ? "+" : ""}{pct.toFixed(1)}%</span>
            {abs !== null && abs !== undefined ? ` (${formatClinicalValue(abs, unit)})` : ""}
          </p>
        );
      })}
    </div>
  );
}

/* ── Main component ─────────────────────────────── */

export default function TrendChart({ height = 340, ...props }: TrendChartProps) {
  if ("analytes" in props) {
    const { analytes } = props;
    const colors = analytes.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
    const analyteNames = analytes.map((ds) => ds.display_name ?? ds.analyte);
    const unit = analytes[0]?.unit ?? "";

    // 3+ same-unit series with very different magnitudes flatten out on one linear axis
    // (e.g. HbA1c % vs. a hormone at 0.01 mmol/L). Index each to its own baseline instead.
    const baselines: Record<string, number> = {};
    let baselinesUsable = analytes.length >= 3;
    analytes.forEach((ds) => {
      const baseline = firstBaseline(ds);
      if (baseline !== null && baseline !== 0) {
        baselines[ds.analyte] = baseline;
      } else {
        baselinesUsable = false;
      }
    });
    const useNormalized = baselinesUsable;
    const useDualAxis = !useNormalized && analytes.length === 2;

    const chartData = useNormalized
      ? buildNormalizedMultiDatasetData(analytes, baselines)
      : buildMultiDatasetData(analytes);
    const narrowMaxWidth =
      chartData.length > 0 && chartData.length < MIN_POINTS_FOR_FULL_WIDTH
        ? Math.max(NARROW_WIDTH_MIN, chartData.length * NARROW_WIDTH_PER_POINT)
        : null;

    return (
      <div
        className="trend-chart-shell"
        role="img"
        aria-label={`Biểu đồ xu hướng ${formatClinicalUnit(unit)} (${analyteNames.join(", ")})`}
      >
        <TrendLegend analytes={analyteNames} colors={colors} />
        {useNormalized && (
          <p className="mb-2 text-xs text-slate-500">
            Quy đổi về % thay đổi so với lần đo đầu tiên — các chỉ số có thang giá trị chênh lệch lớn nên không thể so sánh trực tiếp trên cùng một trục.
          </p>
        )}
        <div style={{ maxWidth: narrowMaxWidth ?? "100%", margin: narrowMaxWidth ? "0 auto" : undefined }}>
          <ResponsiveContainer width="100%" height={height}>
            <LineChart data={chartData} margin={{ top: 18, right: 32, bottom: 18, left: 8 }}>
              <CartesianGrid stroke="#e5edf6" strokeDasharray="4 4" />
              <XAxis
                dataKey="timestamp"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatTrendDate}
                tick={{ fill: "#64748b", fontSize: 12 }}
                axisLine={{ stroke: "#cbd8e8" }}
                tickLine={{ stroke: "#cbd8e8" }}
              />
              {useDualAxis ? (
                <>
                  <YAxis
                    yAxisId="left"
                    domain={["auto", "auto"]}
                    tick={{ fill: colors[0], fontSize: 12 }}
                    axisLine={{ stroke: colors[0] }}
                    tickLine={{ stroke: colors[0] }}
                    width={52}
                  />
                  <YAxis
                    yAxisId="right"
                    orientation="right"
                    domain={["auto", "auto"]}
                    tick={{ fill: colors[1], fontSize: 12 }}
                    axisLine={{ stroke: colors[1] }}
                    tickLine={{ stroke: colors[1] }}
                    width={52}
                  />
                </>
              ) : (
                <YAxis
                  domain={["auto", "auto"]}
                  tick={{ fill: "#64748b", fontSize: 12 }}
                  axisLine={{ stroke: "#cbd8e8" }}
                  tickLine={{ stroke: "#cbd8e8" }}
                  width={52}
                  label={
                    useNormalized
                      ? { value: "% thay đổi", angle: -90, position: "insideLeft", style: { fill: "#64748b", fontSize: 10 } }
                      : undefined
                  }
                />
              )}
              {useNormalized && <ReferenceLine y={0} stroke="#cbd8e8" strokeDasharray="3 3" />}
              <Tooltip
                content={
                  useNormalized ? (
                    <TrendTooltipNormalized unit={unit} />
                  ) : (
                    <TrendTooltipGroup unit={unit} analytes={analyteNames.join(", ")} />
                  )
                }
              />
              {analytes.map((ds, idx) => (
                <Line
                  key={ds.analyte}
                  type="linear"
                  dataKey={ds.analyte}
                  yAxisId={useDualAxis ? (idx === 0 ? "left" : "right") : undefined}
                  stroke={colors[idx % colors.length]}
                  strokeWidth={1.5}
                  dot={{
                    r: 5,
                    strokeWidth: 2,
                    fill: colors[idx % colors.length],
                    stroke: "#fff",
                  }}
                  activeDot={{
                    r: 7,
                    strokeWidth: 2,
                    fill: colors[idx % colors.length],
                    stroke: "#fff",
                  }}
                  isAnimationActive={false}
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    );
  }

  // ── Single analyte (legacy) ─────────────────────
  const { analyte, unit, points, referenceLow, referenceHigh, criticalLow, criticalHigh } = props;
  const chartData: ChartPoint[] = dedupeTrendPoints(points).map((point) => ({
    ...(point as TrendPoint),
    timestamp: new Date(`${point.test_date}T00:00:00`).getTime(),
  }));

  const yBounds = [referenceLow, referenceHigh, criticalLow, criticalHigh].filter(
    (bound): bound is number => typeof bound === "number",
  );
  const change = latestPercentChange(chartData);
  const narrowMaxWidth =
    chartData.length > 0 && chartData.length < MIN_POINTS_FOR_FULL_WIDTH
      ? Math.max(NARROW_WIDTH_MIN, chartData.length * NARROW_WIDTH_PER_POINT)
      : null;

  return (
    <div className="trend-chart-shell" role="img" aria-label={`Biểu đồ xu hướng ${analyte}`}>
      <PercentChangeBadge change={change} />
      <div style={{ maxWidth: narrowMaxWidth ?? "100%", margin: narrowMaxWidth ? "0 auto" : undefined }}>
        <ResponsiveContainer width="100%" height={height}>
          <LineChart data={chartData} margin={{ top: 18, right: 18, bottom: 18, left: 8 }}>
            <CartesianGrid stroke="#e5edf6" strokeDasharray="4 4" />
            <XAxis
              dataKey="timestamp"
              type="number"
              scale="time"
              domain={["dataMin", "dataMax"]}
              tickFormatter={formatTrendDate}
              tick={{ fill: "#64748b", fontSize: 12 }}
              axisLine={{ stroke: "#cbd8e8" }}
              tickLine={{ stroke: "#cbd8e8" }}
            />
            <YAxis
              domain={[
                (dataMin: number) => Math.min(dataMin, ...yBounds),
                (dataMax: number) => Math.max(dataMax, ...yBounds),
              ]}
              tick={{ fill: "#64748b", fontSize: 12 }}
              axisLine={{ stroke: "#cbd8e8" }}
              tickLine={{ stroke: "#cbd8e8" }}
              width={52}
            />
            {referenceHigh !== null && referenceHigh !== undefined && (
              <ReferenceArea
                y1={referenceLow ?? 0}
                y2={referenceHigh}
                fill="#16a34a"
                fillOpacity={0.08}
                stroke="none"
                ifOverflow="extendDomain"
              />
            )}
            {typeof criticalLow === "number" && (
              <ReferenceLine
                y={criticalLow}
                stroke="#dc2626"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
                label={{ value: "Ngưỡng nguy kịch", position: "insideBottomLeft", fill: "#dc2626", fontSize: 10 }}
              />
            )}
            {typeof criticalHigh === "number" && (
              <ReferenceLine
                y={criticalHigh}
                stroke="#dc2626"
                strokeDasharray="4 4"
                strokeWidth={1.5}
                ifOverflow="extendDomain"
                label={{ value: "Ngưỡng nguy kịch", position: "insideTopLeft", fill: "#dc2626", fontSize: 10 }}
              />
            )}
            <Tooltip content={<TrendTooltipSingle unit={unit} analytes={analyte} />} />
            <Line
              type="linear"
              dataKey="value"
              stroke="#94a3b8"
              strokeWidth={1.5}
              dot={<StatusDot radius={5} />}
              activeDot={<StatusDot radius={7} />}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
