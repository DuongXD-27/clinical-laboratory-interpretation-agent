import Link from "next/link";
import { FilePlus } from "lucide-react";

export default function PatientDashboardEmpty() {
  return (
    <section className="flex flex-col items-center justify-center p-8 sm:p-12 text-center bg-[var(--surface)] border border-[var(--border)] rounded-xl shadow-sm">
      <div className="w-12 h-12 rounded-full bg-[var(--surface-subtle)] flex items-center justify-center text-[var(--brand)] mb-4" aria-hidden="true">
        <FilePlus className="w-6 h-6" />
      </div>
      <h3 className="text-lg font-semibold text-foreground mb-2">Bạn chưa có kết quả xét nghiệm nào</h3>
      <p className="text-muted-foreground text-sm max-w-md mx-auto mb-6">
        Phân tích phiếu xét nghiệm đầu tiên để bắt đầu theo dõi sức khỏe và xem lịch sử chỉ số của bạn.
      </p>
      <Link href="/patient/analysis" className="inline-flex items-center justify-center h-10 px-6 font-medium text-sm text-[var(--brand-strong)] bg-[var(--brand-soft)] hover:bg-[var(--brand-soft)]/80 rounded-lg transition-colors">
        Phân tích xét nghiệm
      </Link>
    </section>
  );
}
