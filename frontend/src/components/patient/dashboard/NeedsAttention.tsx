import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { LabReportDetail } from "@/types/history";
import type { IndicatorResult } from "@/types/analysis";
import StatusIndicator from "@/components/common/StatusIndicator";
import { formatClinicalUnitSuffix } from "@/lib/clinicalUnit.mjs";

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
    <section aria-labelledby="needs-attention-title" className="dashboard-section">
      <h2 id="needs-attention-title" className="text-lg font-semibold text-foreground">
        Chỉ số cần lưu ý
      </h2>
      
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        {criticalIndicators.map((indicator, idx) => (
          <article 
            key={`critical-${idx}`} 
            className="dashboard-attention-card dashboard-attention-card--critical"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-semibold text-foreground break-words">{indicator.name}</h3>
              <StatusIndicator state="critical" label="Cần chú ý khẩn cấp" />
            </div>
            <div className="mt-auto pt-2 flex items-baseline gap-1">
              <span className="text-2xl font-bold text-foreground">{indicator.value}</span>
              <span className="text-sm text-muted-foreground">{formatClinicalUnitSuffix(indicator.unit)}</span>
            </div>
          </article>
        ))}

        {attentionIndicators.map((indicator, idx) => (
          <article 
            key={`attention-${idx}`} 
            className="dashboard-attention-card dashboard-attention-card--attention"
          >
            <div className="flex items-start justify-between gap-2 mb-2">
              <h3 className="font-medium text-foreground break-words">{indicator.name}</h3>
              <StatusIndicator state="abnormal" label="Cần lưu ý" />
            </div>
            <div className="mt-auto pt-2 flex items-baseline gap-1">
              <span className="text-xl font-semibold text-foreground">{indicator.value}</span>
              <span className="text-sm text-muted-foreground">{formatClinicalUnitSuffix(indicator.unit)}</span>
            </div>
          </article>
        ))}
      </div>

      <div className="pt-2">
        <Link 
          href={`/patient/reports/${report.id}`}
          transitionTypes={["nav-forward"]}
          className="inline-flex items-center gap-2 text-sm font-medium text-[var(--brand)] hover:underline"
        >
          Xem phân tích chi tiết cho các chỉ số này
          <ArrowRight data-icon="inline-end" className="size-4" aria-hidden="true" />
        </Link>
      </div>
    </section>
  );
}
