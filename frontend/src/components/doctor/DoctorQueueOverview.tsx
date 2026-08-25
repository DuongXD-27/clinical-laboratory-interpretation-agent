import type { DoctorQueueCounts } from "@/types/doctor";
import { AlertCircle, FileSearch, MessageCircle, FileText, CheckCircle2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type Props = {
  counts: DoctorQueueCounts | null;
};

export default function DoctorQueueOverview({ counts }: Props) {
  if (!counts) return null;

  return (
    <Card variant="glass" className="doctor-overview">
      <CardHeader>
        <CardTitle>Tổng quan hoạt động</CardTitle>
      </CardHeader>
      <CardContent className="doctor-overview__grid">
        <div className="doctor-metric doctor-metric--pending">
          <FileText aria-hidden="true" />
          <span>Chờ đánh giá</span>
          <strong>{counts.pending}</strong>
        </div>
        <div className="doctor-metric doctor-metric--critical">
          <AlertCircle aria-hidden="true" />
          <span>Nguy kịch</span>
          <strong>{counts.critical}</strong>
        </div>
        <div className="doctor-metric doctor-metric--ocr">
          <FileSearch aria-hidden="true" />
          <span>OCR cần kiểm tra</span>
          <strong>{counts.ocr}</strong>
        </div>
        <div className="doctor-metric doctor-metric--question">
          <MessageCircle aria-hidden="true" />
          <span>Có câu hỏi</span>
          <strong>{counts.questions}</strong>
        </div>
        <div className="doctor-metric doctor-metric--verified">
          <CheckCircle2 aria-hidden="true" />
          <span>Đã xác minh</span>
          <strong>{counts.verified}</strong>
        </div>
      </CardContent>
    </Card>
  );
}
