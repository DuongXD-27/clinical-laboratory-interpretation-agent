import type { DoctorQueueCounts } from "@/types/doctor";
import type { DoctorQueueTab } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

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

export default function QueueTabs({ active, counts, onChange }: Props) {
  return (
    <Tabs value={active} onValueChange={(value) => onChange(value as DoctorQueueTab)} className="doctor-worklist-tabs">
      <TabsList variant="line" aria-label="Lọc hàng đợi kiểm chứng">
        {TABS.map((tab) => {
          const count = counts?.[tab.countKey];
          return (
            <TabsTrigger key={tab.key} value={tab.key} data-empty={count === 0 && active !== tab.key ? "true" : undefined}>
              <span>{tab.label}</span>
              {count !== undefined ? <span className="doctor-worklist-tab__count">{count}</span> : null}
            </TabsTrigger>
          );
        })}
      </TabsList>
    </Tabs>
  );
}
