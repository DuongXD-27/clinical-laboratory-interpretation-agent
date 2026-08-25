import type { LucideIcon } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

export type ClinicalStatusTone =
  | "critical"
  | "abnormal"
  | "normal"
  | "neutral"
  | "pending"
  | "ocr"
  | "question"
  | "verified";

type Props = {
  children: React.ReactNode;
  tone: ClinicalStatusTone;
  icon?: LucideIcon;
  className?: string;
};

export default function ClinicalStatusChip({ children, tone, icon: Icon, className }: Props) {
  return (
    <Badge
      variant="neutral"
      className={cn("clinical-status-chip", `clinical-status-chip--${tone}`, className)}
    >
      {Icon && <Icon data-icon="inline-start" aria-hidden="true" />}
      <span className="clinical-status-chip__label">{children}</span>
    </Badge>
  );
}
