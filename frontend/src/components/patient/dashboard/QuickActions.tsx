import Link from "next/link";
import { PlusCircle, History, TrendingUp } from "lucide-react";

export default function QuickActions() {
  return (
    <section aria-labelledby="quick-actions-title" className="space-y-4">
      <h2 id="quick-actions-title" className="text-lg font-semibold text-foreground">
        Hành động nhanh
      </h2>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Link 
          href="/patient/analysis" 
          className="flex items-center gap-3 p-4 bg-[var(--glass-surface)] backdrop-blur-xl border border-[var(--glass-border)] rounded-[20px] shadow-[inset_0_1px_1px_rgba(255,255,255,0.8)] transition-all duration-200 motion-reduce:transition-none hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.06),inset_0_1px_2px_rgba(255,255,255,1),0_0_20px_var(--holo-cyan)] hover:border-[var(--holo-cyan)]/40 hover:bg-[var(--surface-elevated)] group"
        >
          <div className="w-10 h-10 rounded-full bg-[var(--brand-soft)] text-[var(--brand)] flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform" aria-hidden="true">
            <PlusCircle className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="font-medium text-sm text-foreground">Phân tích phiếu mới</span>
            <span className="text-xs text-muted-foreground">Tải ảnh hoặc nhập tay</span>
          </div>
        </Link>
        <Link 
          href="/patient/history" 
          className="flex items-center gap-3 p-4 bg-[var(--glass-surface)] backdrop-blur-xl border border-[var(--glass-border)] rounded-[20px] shadow-[inset_0_1px_1px_rgba(255,255,255,0.8)] transition-all duration-200 motion-reduce:transition-none hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.06),inset_0_1px_2px_rgba(255,255,255,1),0_0_20px_var(--holo-blue)] hover:border-[var(--holo-blue)]/40 hover:bg-[var(--surface-elevated)] group"
        >
          <div className="w-10 h-10 rounded-full bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform" aria-hidden="true">
            <History className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="font-medium text-sm text-foreground">Xem lịch sử</span>
            <span className="text-xs text-muted-foreground">Tra cứu kết quả cũ</span>
          </div>
        </Link>
        <Link 
          href="/patient/trends" 
          className="flex items-center gap-3 p-4 bg-[var(--glass-surface)] backdrop-blur-xl border border-[var(--glass-border)] rounded-[20px] shadow-[inset_0_1px_1px_rgba(255,255,255,0.8)] transition-all duration-200 motion-reduce:transition-none hover:-translate-y-0.5 hover:shadow-[0_8px_24px_rgba(0,0,0,0.06),inset_0_1px_2px_rgba(255,255,255,1),0_0_20px_var(--holo-violet)] hover:border-[var(--holo-violet)]/40 hover:bg-[var(--surface-elevated)] group"
        >
          <div className="w-10 h-10 rounded-full bg-[var(--holo-cyan)]/10 text-[var(--holo-cyan)] flex items-center justify-center shrink-0 group-hover:scale-105 transition-transform" aria-hidden="true">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div className="flex flex-col">
            <span className="font-medium text-sm text-foreground">Xu hướng</span>
            <span className="text-xs text-muted-foreground">Theo dõi thay đổi</span>
          </div>
        </Link>
      </div>
    </section>
  );
}
