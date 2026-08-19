import Link from "next/link";
import { AlertCircle, AlertTriangle, ArrowRight } from "lucide-react";
import type { LabReportDetail } from "@/types/history";
import type { IndicatorResult } from "@/types/analysis";

interface NeedsAttentionProps {
  report: LabReportDetail;
}

export default function NeedsAttention({ report }: NeedsAttentionProps) {
  const criticalIndicators: IndicatorResult[] = [];
  const attentionIndicators: IndicatorResult[] = [];

  for (const indicator of report.indicators) {
    if (indicator.is_critical) {
      criticalIndicators.push(indicator);
    } else if (indicator.status === "high" || indicator.status === "low") {
      attentionIndicators.push(indicator);
    }
  }

  if (criticalIndicators.length === 0 && attentionIndicators.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby="needs-attention-title" className="space-y-4">
      <h2 id="needs-attention-title" className="text-lg font-semibold text-foreground">
        Chỉ số cần lưu ý
      </h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {criticalIndicators.map((indicator, idx) => (
          <article 
            key={`critical-${idx}`} 
            className="bg-[var(--surface)] border border-[var(--status-critical-bg)] border-l-4 border-l-[var(--status-critical-fg)] rounded-xl p-4 shadow-sm flex flex-col"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-semibold text-foreground break-words">{indicator.name}</h3>
              <div className="flex items-center gap-1 text-[var(--status-critical-fg)] bg-[var(--status-critical-bg)] px-2 py-0.5 rounded text-xs font-medium shrink-0">
                <AlertCircle className="w-3 h-3" />
                <span>Cần chú ý khẩn cấp</span>
              </div>
            </div>
            <div className="mt-auto pt-2 flex items-baseline gap-1">
              <span className="text-2xl font-bold text-foreground">{indicator.value}</span>
              <span className="text-sm text-muted-foreground">{indicator.unit}</span>
            </div>
          </article>
        ))}

        {attentionIndicators.map((indicator, idx) => (
          <article 
            key={`attention-${idx}`} 
            className="bg-[var(--surface)] border border-[var(--border)] rounded-xl p-4 shadow-sm flex flex-col"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-medium text-foreground break-words">{indicator.name}</h3>
              <div className="flex items-center gap-1 text-[var(--status-warning-fg)] bg-[var(--status-warning-bg)] px-2 py-0.5 rounded text-xs font-medium shrink-0">
                <AlertTriangle className="w-3 h-3" />
                <span>Cần lưu ý</span>
              </div>
            </div>
            <div className="mt-auto pt-2 flex items-baseline gap-1">
              <span className="text-xl font-semibold text-foreground">{indicator.value}</span>
              <span className="text-sm text-muted-foreground">{indicator.unit}</span>
            </div>
          </article>
        ))}
      </div>

      <div className="pt-2">
        <Link 
          href={`/patient/reports/${report.id}`}
          className="inline-flex items-center gap-2 text-sm font-medium text-[var(--brand)] hover:underline"
        >
          Xem phân tích chi tiết cho các chỉ số này
          <ArrowRight className="w-4 h-4" />
        </Link>
      </div>
    </section>
  );
}
