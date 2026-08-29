import type { ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";

export type ContentTier = "standard" | "wide";

export function AppShell({
  role,
  sidebar,
  topbar,
  children,
  tier = "wide",
  floating,
}: {
  role: "patient" | "doctor";
  sidebar: ReactNode;
  topbar: ReactNode;
  children: ReactNode;
  tier?: ContentTier;
  floating?: ReactNode;
}) {
  return (
    <div className={cn("app-shell", `app-shell--${role}`)}>
      <div className="app-shell__atmosphere" aria-hidden="true">
        <span className="app-shell__glow app-shell__glow--teal" />
        <span className="app-shell__glow app-shell__glow--blue" />
        <span className="app-shell__glow app-shell__glow--violet" />
      </div>
      {sidebar}
      <div className="app-shell__frame">
        {topbar}
        <main id={`${role}-main-content`} className="app-shell__main" tabIndex={-1}>
          <ContentRail tier={tier}>{children}</ContentRail>
        </main>
      </div>
      {floating}
    </div>
  );
}

export function ContentRail({
  tier = "standard",
  children,
  className,
}: {
  tier?: ContentTier;
  children: ReactNode;
  className?: string;
}) {
  return <div className={cn("content-rail", `content-rail--${tier}`, className)}>{children}</div>;
}

export function PageHero({
  eyebrow,
  title,
  description,
  actions,
  backHref,
  backLabel = "Quay lại",
  titleId,
  className,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  backHref?: string;
  backLabel?: string;
  titleId?: string;
  className?: string;
}) {
  return (
    <header className={cn("page-hero", className)}>
      {backHref ? (
        <Link className="page-hero__back" href={backHref}>
          <ArrowLeft aria-hidden="true" />
          {backLabel}
        </Link>
      ) : null}
      <div className="page-hero__row">
        <div className="page-hero__copy">
          <p className="type-eyebrow">{eyebrow}</p>
          <h1 id={titleId} className="type-page-title">{title}</h1>
          {description ? <div className="type-page-description">{description}</div> : null}
        </div>
        {actions ? <ActionGroup>{actions}</ActionGroup> : null}
      </div>
    </header>
  );
}

export function ActionGroup({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("action-group", className)}>{children}</div>;
}

export function Surface({
  children,
  material = "clinical",
  className,
}: {
  children: ReactNode;
  material?: "clinical" | "glass";
  className?: string;
}) {
  return <div className={cn("shared-surface", `shared-surface--${material}`, className)}>{children}</div>;
}
