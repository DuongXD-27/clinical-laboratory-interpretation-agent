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
    <div className="doctor-worklist-tabs" role="group" aria-label="Lọc hàng đợi kiểm chứng">
      {TABS.map((tab) => {
        const count = counts?.[tab.countKey];
        const isActive = active === tab.key;
        return (
          <button
            key={tab.key}
            type="button"
            aria-pressed={isActive}
            className={cn("doctor-worklist-tab", isActive && "is-active", count === 0 && !isActive && "is-empty")}
            onClick={() => onChange(tab.key)}
          >
            <span>{tab.label}</span>
            {count !== undefined && <span className="doctor-worklist-tab__count">{count}</span>}
          </button>
        );
      })}
    </div>
  );
}
