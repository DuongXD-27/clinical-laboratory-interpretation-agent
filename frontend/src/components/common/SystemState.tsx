import type { ReactNode } from "react";
import { AlertTriangle, FileQuestion, Inbox, SearchX } from "lucide-react";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { Spinner } from "@/components/ui/spinner";
import { cn } from "@/lib/utils";

type SystemStateKind = "loading" | "empty" | "error" | "not-found";

const ICONS = {
  empty: Inbox,
  error: AlertTriangle,
  "not-found": SearchX,
  loading: FileQuestion,
} as const;

export function SystemState({
  kind,
  title,
  description,
  action,
  compact = false,
  className,
}: {
  kind: SystemStateKind;
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  compact?: boolean;
  className?: string;
}) {
  const Icon = ICONS[kind];
  const loading = kind === "loading";

  return (
    <Empty
      className={cn("system-state", `system-state--${kind}`, compact && "system-state--compact", className)}
      role={kind === "error" ? "alert" : "status"}
      aria-live={loading ? "polite" : undefined}
    >
      <EmptyHeader>
        <EmptyMedia variant="icon">
          {loading ? <Spinner className="size-5" aria-label="Đang tải" /> : <Icon className="size-5" aria-hidden="true" />}
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        {description ? <EmptyDescription>{description}</EmptyDescription> : null}
      </EmptyHeader>
      {action ? <EmptyContent>{action}</EmptyContent> : null}
    </Empty>
  );
}

export function ShellLoadingState({ label }: { label: string }) {
  return (
    <main className="shell-gate">
      <SystemState kind="loading" title={label} compact />
    </main>
  );
}
