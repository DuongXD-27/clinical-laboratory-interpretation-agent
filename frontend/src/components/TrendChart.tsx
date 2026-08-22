"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { assessmentText, dedupeTrendPoints, formatTrendDate } from "@/lib/trendUi.mjs";
import type { TrendPoint } from "@/types/analysis";

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
  | { analyte: string; unit: string; points: TrendPoint[] }
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
        {analytes}: <span className="font-semibold">{value}</span> {unit}
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
            <span className="font-semibold">{val}</span> {unit}
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

/* ── Main component ─────────────────────────────── */

export default function TrendChart({ height = 340, ...props }: TrendChartProps) {
  if ("analytes" in props) {
    const { analytes } = props;
    const colors = analytes.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);
    const chartData = buildMultiDatasetData(analytes);

    const analyteNames = analytes.map((ds) => ds.display_name ?? ds.analyte);
    const unit = analytes[0]?.unit ?? "";

    return (
      <div
        className="trend-chart-shell"
        role="img"
        aria-label={`Biểu đồ xu hướng ${unit} (${analyteNames.join(", ")})`}
      >
        <TrendLegend analytes={analyteNames} colors={colors} />
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
            <YAxis
              domain={["auto", "auto"]}
              tick={{ fill: "#64748b", fontSize: 12 }}
              axisLine={{ stroke: "#cbd8e8" }}
              tickLine={{ stroke: "#cbd8e8" }}
              width={52}
            />
            <Tooltip
              content={
                <TrendTooltipGroup
                  unit={unit}
                  analytes={analyteNames.join(", ")}
                />
              }
            />
            {analytes.map((ds, idx) => (
              <Line
                key={ds.analyte}
                type="linear"
                dataKey={ds.analyte}
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
              />
            ))}
          </LineChart>
        </ResponsiveContainer>
      </div>
    );
  }

  // ── Single analyte (legacy) ─────────────────────
  const { analyte, unit, points } = props;
  const chartData: ChartPoint[] = dedupeTrendPoints(points).map((point) => ({
    ...(point as TrendPoint),
    timestamp: new Date(`${point.test_date}T00:00:00`).getTime(),
  }));

  return (
    <div className="trend-chart-shell" role="img" aria-label={`Biểu đồ xu hướng ${analyte}`}>
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
            domain={["auto", "auto"]}
            tick={{ fill: "#64748b", fontSize: 12 }}
            axisLine={{ stroke: "#cbd8e8" }}
            tickLine={{ stroke: "#cbd8e8" }}
            width={52}
          />
          <Tooltip content={<TrendTooltipSingle unit={unit} analytes={analyte} />} />
          <Line
            type="linear"
            dataKey="value"
            stroke="#94a3b8"
            strokeWidth={1.5}
            dot={{ r: 5, strokeWidth: 2, fill: "#1769e0", stroke: "#fff" }}
            activeDot={{ r: 7, strokeWidth: 2, fill: "#1769e0", stroke: "#fff" }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
