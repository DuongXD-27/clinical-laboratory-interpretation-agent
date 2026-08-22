import type { DoctorQueueCounts } from "@/types/doctor";
import { AlertCircle, FileSearch, MessageCircle, FileText, CheckCircle2 } from "lucide-react";

type Props = {
  counts: DoctorQueueCounts | null;
};

export default function DoctorQueueOverview({ counts }: Props) {
  if (!counts) return null;

  return (
    <div className="relative group mb-6">
      <div className="absolute inset-[-4px] rounded-3xl bg-gradient-to-br from-[var(--holo-cyan)]/20 to-[var(--holo-blue)]/10 blur-xl opacity-60 pointer-events-none" aria-hidden="true" />
      
      <div className="bg-[var(--glass-surface)] backdrop-blur-xl border border-white/20 rounded-2xl p-4 sm:p-5 shadow-[0_8px_32px_rgba(0,0,0,0.04),inset_0_1px_1px_rgba(255,255,255,0.8),inset_1px_1px_1px_rgba(71,214,211,0.1),inset_-1px_-1px_1px_rgba(96,165,250,0.1)] relative z-10">
        <h2 className="text-sm font-semibold text-foreground mb-4">Tổng quan hoạt động</h2>
        
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-4">
          <div className="flex flex-col">
            <div className="flex items-center gap-2 text-muted-foreground mb-1">
              <FileText className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs font-medium">Chờ đánh giá</span>
            </div>
            <span className="text-2xl font-bold text-foreground">{counts.pending}</span>
          </div>

          <div className="flex flex-col">
            <div className="flex items-center gap-2 text-[var(--severity-critical)] mb-1">
              <AlertCircle className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs font-semibold">Nguy kịch</span>
            </div>
            <span className="text-2xl font-bold text-[var(--severity-critical)]">{counts.critical}</span>
          </div>

          <div className="flex flex-col">
            <div className="flex items-center gap-2 text-[var(--brand)] mb-1">
              <FileSearch className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs font-medium">OCR cần kiểm tra</span>
            </div>
            <span className="text-2xl font-bold text-[var(--brand-strong)]">{counts.ocr}</span>
          </div>

          <div className="flex flex-col">
            <div className="flex items-center gap-2 text-amber-600 dark:text-amber-500 mb-1">
              <MessageCircle className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs font-medium">Có câu hỏi</span>
            </div>
            <span className="text-2xl font-bold text-amber-700 dark:text-amber-400">{counts.questions}</span>
          </div>

          <div className="flex flex-col sm:col-span-1 md:border-l md:border-[var(--border)] md:pl-4">
            <div className="flex items-center gap-2 text-green-600 dark:text-green-500 mb-1">
              <CheckCircle2 className="w-4 h-4" aria-hidden="true" />
              <span className="text-xs font-medium">Đã xác minh</span>
            </div>
            <span className="text-2xl font-bold text-green-700 dark:text-green-400">{counts.verified}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
