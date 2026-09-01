import type { DoctorQueueCounts } from "@/types/doctor";
import { AlertCircle, FileSearch, MessageCircle, FileText, CheckCircle2 } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

type Props = {
  counts: DoctorQueueCounts | null;
};

export default function DoctorQueueOverview({ counts }: Props) {
  if (!counts) {
    return (
      <div className="doctor-summary-strip doctor-summary-strip--loading" role="status" aria-label="Đang tải tổng quan hàng đợi">
        {Array.from({ length: 5 }).map((_, index) => <Skeleton key={index} className="doctor-summary-strip__skeleton" />)}
      </div>
    );
  }

  const metrics = [
    { key: "pending", label: "Chờ đánh giá", value: counts.pending, icon: FileText },
    { key: "critical", label: "Nguy kịch", value: counts.critical, icon: AlertCircle },
    { key: "ocr", label: "OCR cần kiểm tra", value: counts.ocr, icon: FileSearch },
    { key: "question", label: "Có câu hỏi", value: counts.questions, icon: MessageCircle },
    { key: "verified", label: "Đã xác minh", value: counts.verified, icon: CheckCircle2 },
  ] as const;

  return (
    <section className="doctor-summary-strip" aria-labelledby="doctor-summary-title">
      <h2 id="doctor-summary-title" className="sr-only">Tổng quan hoạt động</h2>
      <dl>
        {metrics.map((metric) => {
          const Icon = metric.icon;
          return (
            <div key={metric.key} className="doctor-summary-metric" data-tone={metric.key}>
              <Icon aria-hidden="true" />
              <dt>{metric.label}</dt>
              <dd>{metric.value}</dd>
            </div>
          );
        })}
      </dl>
    </section>
  );
}
