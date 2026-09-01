"use client";

import { useMemo, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Search } from "lucide-react";
import StatusIndicator from "@/components/common/StatusIndicator";
import { formatClinicalUnit } from "@/lib/clinicalUnit.mjs";

export type MetricDefinition = {
  name: string;
  label: string;
  unit: string;
  category?: string;
  runtimeStatus?: "APPROVED" | "HOLD" | "UNSUPPORTED";
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
  const grouped = useMemo(() => {
    const groups = new Map<string, MetricDefinition[]>();
    for (const metric of filtered) {
      const category = metric.category ?? "Khác";
      const items = groups.get(category) ?? [];
      items.push(metric);
      groups.set(category, items);
    }
    return Array.from(groups, ([label, items]) => ({ label, items }));
  }, [filtered]);

  return (
    <Dialog open={open} onOpenChange={(nextOpen) => { if (!nextOpen) onClose(); }}>
      <DialogContent className="metric-modal gap-0 p-0 sm:max-w-3xl">
        <DialogHeader className="px-5 pb-4 pt-5 sm:px-6">
          <DialogTitle id="metric-selector-title" className="text-lg font-semibold text-foreground">
            Thêm chỉ số xét nghiệm
          </DialogTitle>
          <DialogDescription>Chọn chỉ số theo nhóm có sẵn trên phiếu của bạn.</DialogDescription>
        </DialogHeader>

        <div className="border-y border-[var(--border)]/70 px-5 py-4 sm:px-6">
          <label className="sr-only" htmlFor="metric-search">Tìm chỉ số xét nghiệm</label>
          <div className="metric-search-control">
            <Search aria-hidden="true" />
            <input
              id="metric-search"
              type="search"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Tìm theo tên hoặc nhóm chỉ số..."
              autoFocus
            />
          </div>
        </div>

        <div className="max-h-[min(62vh,34rem)] overflow-y-auto p-4 sm:p-5">
          {filtered.length === 0 ? (
            <p className="px-3 py-10 text-center text-sm text-muted-foreground">Không tìm thấy chỉ số phù hợp.</p>
          ) : (
            <div className="flex flex-col gap-5">
              {grouped.map((group) => (
                <section key={group.label} aria-labelledby={`metric-group-${normalize(group.label).replace(/\s+/g, "-")}`}>
                  <div className="metric-group-heading">
                    <h3 id={`metric-group-${normalize(group.label).replace(/\s+/g, "-")}`}>{group.label}</h3>
                    <span>{group.items.length} chỉ số</span>
                  </div>
                  <ul className="mt-2 grid gap-2 sm:grid-cols-2">
                    {group.items.map((metric) => {
                      const isSelected = selected.has(metric.name);
                      const statusLabel = metric.runtimeStatus === "HOLD"
                        ? "Tạm giữ"
                        : metric.runtimeStatus === "UNSUPPORTED"
                          ? "Chưa hỗ trợ"
                          : "";
                      return (
                        <li key={metric.name}>
                          <button
                            type="button"
                            disabled={isSelected}
                            onClick={() => onAdd(metric)}
                            className="metric-option w-full text-left"
                            aria-label={`${isSelected ? "Đã thêm" : "Thêm"} ${metric.label}`}
                          >
                            <span className="min-w-0">
                              <span className="flex flex-wrap items-center gap-2">
                                <strong>{metric.label}</strong>
                                {statusLabel && (
                                  <StatusIndicator state={metric.runtimeStatus === "UNSUPPORTED" ? "unsupported" : "input-review"} label={statusLabel} />
                                )}
                              </span>
                              <small>{formatClinicalUnit(metric.unit)}</small>
                            </span>
                            <span className="metric-option-state">{isSelected ? "Đã thêm" : "+ Thêm"}</span>
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              ))}
            </div>
           )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
