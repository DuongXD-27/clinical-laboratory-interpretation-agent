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
  { key: "verified", label: "Đã xử lý", countKey: "verified" },
];

export default function QueueTabs({ active, counts, onChange }: Props) {
  return (
    <div className="queue-tabs" role="tablist" aria-label="Lọc hàng đợi kiểm chứng">
      {TABS.map((tab) => {
        const count = counts?.[tab.countKey];
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={active === tab.key}
            className={`queue-tab${active === tab.key ? " active" : ""}${count === 0 ? " is-empty" : ""}`}
            onClick={() => onChange(tab.key)}
          >
            <span>{tab.label}</span>
            <span className="queue-tab__count">{count ?? ""}</span>
          </button>
        );
      })}
    </div>
  );
}
