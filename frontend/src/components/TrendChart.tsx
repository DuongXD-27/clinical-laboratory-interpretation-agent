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

type ChartPoint = TrendPoint & {
  timestamp: number;
};

type TooltipPayload = {
  payload?: ChartPoint;
};

type TooltipProps = {
  active?: boolean;
  payload?: TooltipPayload[];
  label?: number;
  unit: string;
  analyte: string;
};

function TrendTooltip({ active, payload, label, unit, analyte }: TooltipProps) {
  if (!active || !payload?.length) return null;
  const point = payload[0]?.payload;
  if (!point) return null;
  return (
    <div className="trend-tooltip">
      <p className="font-semibold text-slate-950">{formatTrendDate(label ?? point.timestamp)}</p>
      <p className="mt-1 text-sm text-slate-700">
        {analyte}: <span className="font-semibold">{point.value}</span> {unit}
      </p>
      <p className="mt-1 text-xs text-slate-500">Trạng thái: {assessmentText(point.assessment)}</p>
    </div>
  );
}

export default function TrendChart({
  analyte,
  unit,
  points,
  height = 340,
}: {
  analyte: string;
  unit: string;
  points: TrendPoint[];
  height?: number;
}) {
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
          <Tooltip content={<TrendTooltip unit={unit} analyte={analyte} />} />
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
