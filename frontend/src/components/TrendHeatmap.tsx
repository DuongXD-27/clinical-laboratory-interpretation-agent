"use client";

import { useState } from "react";
import { formatTrendDate } from "@/lib/trendUi.mjs";
import { indicatorStatusText, reportTone } from "@/lib/patientUi.mjs";
import { formatClinicalUnitSuffix, formatClinicalValue } from "@/lib/clinicalUnit.mjs";
import type { HeatmapCell, SectionHeatmapResponse } from "@/types/analysis";

type Tone = "normal" | "abnormal" | "critical" | "unknown";

/** Same tone resolution `IndicatorResultCard` uses: critical_status wins, else `reportTone(status)`. */
function cellTone(cell: HeatmapCell): Tone {
  if (cell.critical_status) return "critical";
  return reportTone(cell.status) as Tone;
}

const LEGEND: { tone: Tone; label: string }[] = [
  { tone: "normal", label: "Bình thường" },
  { tone: "abnormal", label: "Bất thường" },
  { tone: "critical", label: "Nguy kịch" },
  { tone: "unknown", label: "Chưa rõ" },
];

function referenceRangeText(cell: HeatmapCell): string {
  if (cell.reference_low !== null && cell.reference_low !== undefined && cell.reference_high !== null && cell.reference_high !== undefined) {
    return `${cell.reference_low} – ${cell.reference_high} ${formatClinicalUnitSuffix(cell.unit)}`;
  }
  if (cell.reference_high !== null && cell.reference_high !== undefined) return `≤ ${formatClinicalValue(cell.reference_high, cell.unit)}`;
  if (cell.reference_low !== null && cell.reference_low !== undefined) return `≥ ${formatClinicalValue(cell.reference_low, cell.unit)}`;
  return "Chưa xác định khoảng tham chiếu";
}

type SelectedCell = { analyte: string; cell: HeatmapCell };

/** Ma trận chỉ số × phiếu xét nghiệm — thay thế biểu đồ đường khi cần xem nhiều chỉ số
 * cùng lúc hoặc khi dữ liệu thưa (phiếu nào thiếu chỉ số thì ô đó để trống, không nội suy). */
export default function TrendHeatmap({ data }: { data: SectionHeatmapResponse }) {
  const [selected, setSelected] = useState<SelectedCell | null>(null);

  if (data.rows.length === 0 || data.columns.length === 0) {
    return (
      <div className="patient-glass-clinical p-6 text-center text-slate-600">
        Chưa có dữ liệu nào trong nhóm này để hiển thị ma trận.
      </div>
    );
  }

  return (
    <div className="patient-glass-clinical p-4 sm:p-6">
      <div className="mb-3 flex flex-wrap items-center gap-3 text-xs text-slate-600">
        {LEGEND.map((item) => (
          <span key={item.tone} className="inline-flex items-center gap-1.5">
            <span className={`heatmap-swatch heatmap-swatch-${item.tone}`} />
            {item.label}
          </span>
        ))}
        <span className="inline-flex items-center gap-1.5">
          <span className="heatmap-swatch heatmap-swatch-missing" />
          Không có dữ liệu
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="heatmap-table">
          <thead>
            <tr>
              <th className="heatmap-th-sticky">Chỉ số</th>
              {data.columns.map((col) => (
                <th key={col.report_id}>{formatTrendDate(col.test_date)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.rows.map((row) => (
              <tr key={row.analyte_canonical}>
                <th className="heatmap-th-sticky" scope="row">
                  {row.analyte_canonical}
                </th>
                {row.cells.map((cell, idx) => {
                  const column = data.columns[idx];
                  if (!cell) {
                    return (
                      <td key={column.report_id}>
                        <div
                          className="heatmap-cell heatmap-cell-missing"
                          role="img"
                          aria-label={`${row.analyte_canonical} ngày ${formatTrendDate(column.test_date)}: không có dữ liệu`}
                        />
                      </td>
                    );
                  }
                  const tone = cellTone(cell);
                  const isSelected =
                    selected?.analyte === row.analyte_canonical && selected.cell.report_id === cell.report_id;
                  return (
                    <td key={column.report_id}>
                      <button
                        type="button"
                        className={`heatmap-cell heatmap-cell-${tone} ${isSelected ? "heatmap-cell-selected" : ""}`}
                        onClick={() => setSelected({ analyte: row.analyte_canonical, cell })}
                        aria-label={`${row.analyte_canonical} ngày ${formatTrendDate(column.test_date)}: ${formatClinicalValue(cell.value, cell.unit)}, ${indicatorStatusText(cell.status, cell.critical_status)}`}
                      >
                        {cell.value}
                      </button>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {selected && (
        <div className="mt-4 rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-900">{selected.analyte}</h4>
            <button type="button" className="text-xs text-slate-400 hover:text-slate-600" onClick={() => setSelected(null)}>
              Đóng
            </button>
          </div>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1 text-sm text-slate-700 sm:grid-cols-4">
            <div>
              <dt className="text-xs text-slate-500">Giá trị</dt>
              <dd className="font-semibold">
                {formatClinicalValue(selected.cell.value, selected.cell.unit)}
              </dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Khoảng tham chiếu</dt>
              <dd>{referenceRangeText(selected.cell)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Trạng thái</dt>
              <dd>{indicatorStatusText(selected.cell.status, selected.cell.critical_status)}</dd>
            </div>
            <div>
              <dt className="text-xs text-slate-500">Ngày xét nghiệm</dt>
              <dd>{formatTrendDate(selected.cell.test_date)}</dd>
            </div>
          </dl>
        </div>
      )}
    </div>
  );
}
