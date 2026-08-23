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
import { formatTrendDate } from "@/lib/trendUi.mjs";
import type { TrendPoint } from "@/types/analysis";

/* ── Types ────────────────────────────────────────── */

/** A series of test-date/value observations for one analyte. */
type MetricSeries = {
  name: string;
  unit: string;
  color: string;
  points: TrendPoint[];
};

/** Raw health data the component expects. */
export type HealthChartData = {
  ldl_c: TrendPoint[];
  hdl_c: TrendPoint[];
  glucose: TrendPoint[];
  hba1c: TrendPoint[];
};

/* ── Constants ────────────────────────────────────── */

const CHART_HEIGHT = 280;

/** Colorblind-safe palette for the 4 metrics. */
const COLORS = {
  ldl_c: "#2563eb", // blue-600
  hdl_c: "#059669", // green-600
  glucose: "#dc2626", // red-600
  hba1c: "#7c3aed", // purple-600
} as const;

/* ── Helpers ──────────────────────────────────────── */

/**
 * Merge multiple series onto a shared time X-axis.
 * Returns sorted array where each entry has: date, timestamp, + one key per series.
 */
function mergeSeries(seriesList: MetricSeries[]): Record<string, unknown>[] {
  const allDates = new Set<string>();
  seriesList.forEach((s) => s.points.forEach((p) => allDates.add(p.test_date)));

  return Array.from(allDates)
    .sort(
      (a, b) =>
        new Date(a).getTime() - new Date(b).getTime(),
    )
    .map((date) => {
      const obj: Record<string, unknown> = {
        date,
        timestamp: new Date(`${date}T00:00:00`).getTime(),
      };
      seriesList.forEach((s) => {
        const match = s.points.find((p) => p.test_date === date);
        obj[s.name] = match ? match.value : null;
      });
      return obj;
    });
}

/** Build a name→unit map so tooltips show the right unit per analyte. */
function unitMap(seriesList: MetricSeries[]): Record<string, string> {
  const map: Record<string, string> = {};
  seriesList.forEach((s) => {
    map[s.name] = s.unit;
  });
  return map;
}

function colorMap(seriesList: MetricSeries[]): Record<string, string> {
  const map: Record<string, string> = {};
  seriesList.forEach((s) => {
    map[s.name] = s.color;
  });
  return map;
}

/* ── Shared tooltip ───────────────────────────────── */

type TooltipEntry = { payload?: Record<string, unknown>; value?: number; dataKey?: string };

interface SharedTooltipProps {
  active?: boolean;
  payload?: TooltipEntry[];
  label?: string;
  units: Record<string, string>;
  colors: Record<string, string>;
}

/**
 * Shared tooltip — displays Date, Metric Name, Value, and Unit.
 * Looks up unit & color per dataKey from the passed-in maps.
 */
function HealthTooltip({ active, payload, label, units, colors }: SharedTooltipProps) {
  if (!active || !payload || payload.length === 0) return null;

  const dateValue = (payload[0]?.payload as { date?: string })?.date ?? label ?? "";

  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-md text-xs">
      <p className="font-semibold text-slate-900">{formatTrendDate(dateValue)}</p>
      <div className="mt-1 space-y-0.5">
        {payload
          .filter((entry) => entry?.value !== null && entry?.value !== undefined)
          .map((entry, idx) => {
            const key = entry.dataKey ?? "";
            const col = colors[key] ?? "#94a3b8";
            return (
              <div key={idx} className="flex items-center gap-1.5">
                <span className="inline-block h-2 w-2 rounded-full" style={{ backgroundColor: col }} />
                <span className="font-medium" style={{ color: col }}>
                  {key}
                </span>
                <span className="text-slate-700">
                  {entry.value} {units[key] ?? ""}
                </span>
              </div>
            );
          })}
      </div>
    </div>
  );
}

/** Shared legend rendered above each chart. */
function Legend({ series }: { series: MetricSeries[] }) {
  return (
    <div className="mb-2 flex flex-wrap gap-3 text-xs">
      {series.map((s) => (
        <div key={s.name} className="flex items-center gap-1.5">
          <span className="inline-block h-3 w-3 rounded-full" style={{ backgroundColor: s.color }} />
          <span className="text-slate-600">
            {s.name} ({s.unit})
          </span>
        </div>
      ))}
    </div>
  );
}

/* ── Chart 1: Lipid Profile (shared Y-axis) ──────── */

/**
 * Chart 1 — Lipid Profile (Mỡ máu).
 * LDL-C and HDL-C share the unit mmol/L → single shared Y-axis, domain starts at 0.
 */
function LipidProfileChart({ data }: { data: HealthChartData }) {
  const series: MetricSeries[] = [
    { name: "LDL-C", unit: "mmol/L", color: COLORS.ldl_c, points: data.ldl_c ?? [] },
    { name: "HDL-C", unit: "mmol/L", color: COLORS.hdl_c, points: data.hdl_c ?? [] },
  ];

  const hasData = series.some((s) => s.points.length > 0);
  if (!hasData) {
    return <EmptyState />;
  }

  const chartData = mergeSeries(series);
  const units = unitMap(series);
  const colors = colorMap(series);

  return (
    <div className="w-full max-w-none rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <h3 className="text-sm font-semibold text-slate-800">Mỡ máu (LDL-C / HDL-C)</h3>
      <Legend series={series} />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={chartData} margin={{ top: 12, right: 24, bottom: 12, left: 8 }}>
          <CartesianGrid stroke="#e5edf6" strokeDasharray="4 4" />
          <XAxis
            dataKey="timestamp"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatTrendDate}
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={{ stroke: "#cbd8e8" }}
            tickLine={{ stroke: "#cbd8e8" }}
          />
          <YAxis
            domain={[0, "auto"]}
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={{ stroke: "#cbd8e8" }}
            tickLine={{ stroke: "#cbd8e8" }}
            width={48}
          />
          <Tooltip content={<HealthTooltip units={units} colors={colors} />} />
          {series.map((s) => (
            <Line
              key={s.name}
              type="linear"
              dataKey={s.name}
              stroke={s.color}
              strokeWidth={2}
              dot={{ r: 5, strokeWidth: 2, fill: s.color, stroke: "#fff" }}
              activeDot={{ r: 7, strokeWidth: 2, fill: s.color, stroke: "#fff" }}
              isAnimationActive={false}
              connectNulls
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Chart 2: Blood Sugar Control (dual Y-axis) ──── */

/**
 * Chart 2 — Blood Sugar Control (Đường huyết).
 * Fasting Plasma Glucose (mmol/L) → left Y-axis, HbA1c (%) → right Y-axis.
 * Both axes start from 0.
 */
function BloodSugarChart({ data }: { data: HealthChartData }) {
  const series: MetricSeries[] = [
    { name: "Glucose", unit: "mmol/L", color: COLORS.glucose, points: data.glucose ?? [] },
    { name: "HbA1c", unit: "%", color: COLORS.hba1c, points: data.hba1c ?? [] },
  ];

  const hasData = series.some((s) => s.points.length > 0);
  if (!hasData) {
    return <EmptyState />;
  }

  const chartData = mergeSeries(series);
  const units = unitMap(series);
  const colors = colorMap(series);

  return (
    <div className="w-full max-w-none rounded-xl border border-slate-200 bg-white p-4 sm:p-6">
      <h3 className="text-sm font-semibold text-slate-800">Đường huyết (Glucose / HbA1c)</h3>
      <Legend series={series} />
      <ResponsiveContainer width="100%" height={CHART_HEIGHT}>
        <LineChart data={chartData} margin={{ top: 12, right: 24, bottom: 12, left: 8 }}>
          <CartesianGrid stroke="#e5edf6" strokeDasharray="4 4" />
          <XAxis
            dataKey="timestamp"
            type="number"
            scale="time"
            domain={["dataMin", "dataMax"]}
            tickFormatter={formatTrendDate}
            tick={{ fill: "#64748b", fontSize: 11 }}
            axisLine={{ stroke: "#cbd8e8" }}
            tickLine={{ stroke: "#cbd8e8" }}
          />
          {/* Left Y-axis: Glucose (mmol/L) */}
          <YAxis
            yAxisId="left"
            domain={[0, "auto"]}
            tick={{ fill: COLORS.glucose, fontSize: 11 }}
            axisLine={{ stroke: COLORS.glucose }}
            tickLine={{ stroke: COLORS.glucose }}
            width={48}
            label={{
              value: "mmol/L",
              angle: -90,
              position: "insideLeft",
              style: { fill: COLORS.glucose, fontSize: 10 },
            }}
          />
          {/* Right Y-axis: HbA1c (%) */}
          <YAxis
            yAxisId="right"
            orientation="right"
            domain={[0, "auto"]}
            tick={{ fill: COLORS.hba1c, fontSize: 11 }}
            axisLine={{ stroke: COLORS.hba1c }}
            tickLine={{ stroke: COLORS.hba1c }}
            width={48}
            label={{
              value: "%",
              angle: 90,
              position: "insideRight",
              style: { fill: COLORS.hba1c, fontSize: 10 },
            }}
          />
          <Tooltip content={<HealthTooltip units={units} colors={colors} />} />
          <Line
            yAxisId="left"
            type="linear"
            dataKey="Glucose"
            stroke={COLORS.glucose}
            strokeWidth={2}
            dot={{ r: 5, strokeWidth: 2, fill: COLORS.glucose, stroke: "#fff" }}
            activeDot={{ r: 7, strokeWidth: 2, fill: COLORS.glucose, stroke: "#fff" }}
            isAnimationActive={false}
            connectNulls
          />
          <Line
            yAxisId="right"
            type="linear"
            dataKey="HbA1c"
            stroke={COLORS.hba1c}
            strokeWidth={2}
            dot={{ r: 5, strokeWidth: 2, fill: COLORS.hba1c, stroke: "#fff" }}
            activeDot={{ r: 7, strokeWidth: 2, fill: COLORS.hba1c, stroke: "#fff" }}
            isAnimationActive={false}
            connectNulls
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/* ── Empty state ────────────────────────────────── */

function EmptyState() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 text-center text-sm text-slate-500">
      Chưa có dữ liệu.
    </div>
  );
}

/* ── Public component ───────────────────────────── */

/**
 * Renders two compact health-trend charts:
 *  1. Lipid Profile (LDL-C + HDL-C) — shared Y-axis.
 *  2. Blood Sugar Control (Glucose + HbA1c) — dual Y-axis.
 *
 * Pass real patient data via the `data` prop.
 */
export default function GroupedHealthCharts({ data }: { data: HealthChartData }) {
  return (
    <div className="flex w-full max-w-none flex-col gap-6">
      <LipidProfileChart data={data} />
      <BloodSugarChart data={data} />
    </div>
  );
}
