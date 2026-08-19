import type { DoctorQueueCounts } from "@/types/doctor";
import type { DoctorQueueTab } from "@/lib/api";

type Props = {
  active: DoctorQueueTab;
  counts: DoctorQueueCounts | null;
  onChange: (tab: DoctorQueueTab) => void;
};

const TABS: { key: DoctorQueueTab; label: string; countKey: keyof DoctorQueueCounts }[] = [
  { key: "pending", label: "Tất cả đang chờ", countKey: "pending" },
  { key: "critical", label: "Nguy kịch", countKey: "critical" },
  { key: "ocr", label: "OCR cần kiểm tra", countKey: "ocr" },
  { key: "questions", label: "Có câu hỏi", countKey: "questions" },
  { key: "verified", label: "Đã xác minh", countKey: "verified" },
];

import { cn } from "@/lib/utils";

export default function QueueTabs({ active, counts, onChange }: Props) {
  return (
    <div className="flex flex-wrap items-center gap-2 mb-6" aria-label="Lọc hàng đợi kiểm chứng">
      {TABS.map((tab) => {
        const count = counts?.[tab.countKey];
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            aria-pressed={isActive}
            className={cn(
              "inline-flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors relative outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
              isActive 
                ? "bg-[var(--glass-surface)] backdrop-blur-md shadow-[0_4px_16px_rgba(0,0,0,0.04),inset_0_1px_1px_rgba(255,255,255,0.8)] border border-[var(--holo-cyan)]/30 text-foreground"
                : "bg-[var(--surface)] border border-[var(--border)] text-[var(--foreground-secondary)] hover:bg-[var(--surface-subtle)] hover:text-foreground",
              count === 0 && !isActive ? "opacity-60" : ""
            )}
            onClick={() => onChange(tab.key)}
          >
            <span>{tab.label}</span>
            {count !== undefined && count > 0 && (
              <span className={cn(
                "inline-flex items-center justify-center min-w-[24px] px-1.5 py-0.5 rounded-full text-xs font-semibold",
                isActive 
                  ? "bg-[var(--brand-soft)] text-[var(--brand-strong)]" 
                  : "bg-[var(--surface-subtle)] text-[var(--foreground-secondary)] group-hover:bg-[var(--border)]"
              )}>
                {count}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
