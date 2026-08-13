"use client";

import { useEffect, useMemo, useState } from "react";

export type MetricDefinition = {
  name: string;
  label: string;
  unit: string;
  category?: string;
};

type Props = {
  open: boolean;
  catalog: readonly MetricDefinition[];
  selectedNames: string[];
  onAdd: (metric: MetricDefinition) => void;
  onClose: () => void;
};

function normalize(value: string) {
  return value
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLocaleLowerCase("vi");
}

export default function MetricSelector({ open, catalog, selectedNames, onAdd, onClose }: Props) {
  const [query, setQuery] = useState("");
  const selected = useMemo(() => new Set(selectedNames), [selectedNames]);
  const filtered = useMemo(() => {
    const normalizedQuery = normalize(query.trim());
    if (!normalizedQuery) return catalog;
    return catalog.filter((metric) => normalize(`${metric.label} ${metric.name} ${metric.category ?? ""}`).includes(normalizedQuery));
  }, [catalog, query]);

  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  return (
    <div className="modal-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="metric-selector-title"
        className="metric-modal"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-start justify-between gap-4 px-5 pb-4 pt-5 sm:px-6">
          <div>
            <h2 id="metric-selector-title" className="text-lg font-semibold text-slate-950">
              Thêm chỉ số xét nghiệm
            </h2>
            <p className="mt-1 text-sm text-slate-500">Chọn chỉ số có trên phiếu của bạn.</p>
          </div>
          <button type="button" onClick={onClose} className="icon-button" aria-label="Đóng danh sách chỉ số">
            ×
          </button>
        </div>

        <div className="border-y border-slate-100 px-5 py-4 sm:px-6">
          <label className="sr-only" htmlFor="metric-search">Tìm chỉ số xét nghiệm</label>
          <input
            id="metric-search"
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Tìm chỉ số..."
            className="form-control"
            autoFocus
          />
        </div>

        <div className="max-h-[min(55vh,28rem)] overflow-y-auto p-3 sm:p-4">
          {filtered.length === 0 ? (
            <p className="px-3 py-10 text-center text-sm text-slate-500">Không tìm thấy chỉ số phù hợp.</p>
          ) : (
            <ul className="space-y-2">
              {filtered.map((metric) => {
                const isSelected = selected.has(metric.name);
                return (
                  <li key={metric.name} className="metric-option">
                    <div className="min-w-0">
                      <p className="font-semibold text-slate-900">{metric.label}</p>
                      <p className="mt-1 text-xs text-slate-500">
                        {[metric.category, metric.unit].filter(Boolean).join(" · ")}
                      </p>
                    </div>
                    <button
                      type="button"
                      disabled={isSelected}
                      onClick={() => onAdd(metric)}
                      className="secondary-button shrink-0 px-3 py-2"
                    >
                      {isSelected ? "Đã thêm" : "Thêm"}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </section>
    </div>
  );
}
