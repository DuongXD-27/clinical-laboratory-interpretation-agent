"use client";

import { usePathname } from "next/navigation";
import { ViewTransition, type ReactNode } from "react";
import { cn } from "@/lib/utils";

interface RouteTransitionProps {
  children: ReactNode;
  className?: string;
  variant?: "patient" | "doctor" | "admin";
}

/**
 * RouteTransition
 *
 * Provides a quiet, calm clinical entrance for main workspace content
 * when navigating between routes. The application shell (sidebar, topbar,
 * atmospheric background) remains completely static and persistent.
 */
export default function RouteTransition({
  children,
  className,
  variant = "patient",
}: RouteTransitionProps) {
  const pathname = usePathname();
  const transitionClass = `lumilens-route-${variant}`;

  return (
    <ViewTransition
      name="lumilens-workspace"
      default="none"
      enter={{ "nav-forward": "lumilens-detail-enter", "nav-back": "lumilens-back-enter", "nav-route": transitionClass, default: "none" }}
      exit={{ "nav-forward": "lumilens-detail-exit", "nav-back": "lumilens-back-exit", "nav-route": transitionClass, default: "none" }}
    >
      <div
        key={pathname}
        className={cn("motion-route", `motion-route--${variant}`, className)}
        data-motion-route={variant}
      >
        {children}
      </div>
    </ViewTransition>
  );
}
