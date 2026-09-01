import { ViewTransition, type ReactNode } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { cn } from "@/lib/utils";
import { ClinicalSignal } from "@/components/common/BrandSignature";

export type ContentTier = "standard" | "wide";

export function AppShell({
  role,
  sidebar,
  topbar,
  children,
  tier = "wide",
  floating,
  motionKey,
}: {
  role: "patient" | "doctor" | "admin";
  sidebar: ReactNode;
  topbar: ReactNode;
  children: ReactNode;
  tier?: ContentTier;
  floating?: ReactNode;
  motionKey?: string;
}) {
  return (
    <div className={cn("app-shell", `app-shell--${role}`)}>
      <div key={motionKey} className="app-shell__atmosphere" aria-hidden="true">
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
  transitionName,
}: {
  eyebrow: string;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  backHref?: string;
  backLabel?: string;
  titleId?: string;
  className?: string;
  transitionName?: string;
}) {
  const heroCopy = (
    <div className="page-hero__copy">
      <p className="type-eyebrow">{eyebrow}</p>
      <h1 id={titleId} className="type-page-title">{title}</h1>
      {description ? <div className="type-page-description">{description}</div> : null}
    </div>
  );

  const hero = (
    <header className={cn("page-hero", className)} data-motion-layer="header">
      {backHref ? (
        <Link className="page-hero__back" href={backHref} transitionTypes={["nav-back"]}>
          <ArrowLeft aria-hidden="true" />
          {backLabel}
        </Link>
      ) : null}
      <div className="page-hero__row">
        {transitionName ? (
          <ViewTransition name={transitionName} default="none" share="lumilens-shared-detail">
            {heroCopy}
          </ViewTransition>
        ) : heroCopy}
        {actions ? (
          <ViewTransition default="none">
            <ActionGroup>{actions}</ActionGroup>
          </ViewTransition>
        ) : null}
      </div>
      <ClinicalSignal className="page-hero__signal" />
    </header>
  );

  return (
    <ViewTransition default="none" enter="lumilens-layer-header">
      {hero}
    </ViewTransition>
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
