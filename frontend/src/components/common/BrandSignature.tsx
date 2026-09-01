import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span className={cn("brand-signature", className)} aria-hidden="true">
      <span className="brand-signature__halo" />
      <span className="brand-signature__lens brand-signature__lens--left" />
      <span className="brand-signature__lens brand-signature__lens--right" />
      <span className="brand-signature__core" />
    </span>
  );
}

export function BrandLockup({
  context,
  compact = false,
  className,
}: {
  context?: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <span className={cn("brand-lockup", compact && "brand-lockup--compact", className)}>
      <BrandMark />
      <span className="brand-lockup__copy">
        <span className="brand-lockup__name">LumiLab</span>
        {context ? <span className="brand-lockup__context">{context}</span> : null}
      </span>
    </span>
  );
}

export function ClinicalSignal({ className }: { className?: string }) {
  return (
    <span className={cn("clinical-signal", className)} aria-hidden="true">
      <span className="clinical-signal__line" />
      <span className="clinical-signal__node clinical-signal__node--one" />
      <span className="clinical-signal__node clinical-signal__node--two" />
      <span className="clinical-signal__node clinical-signal__node--three" />
    </span>
  );
}
