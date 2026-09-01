import { ViewTransition, type ReactElement } from "react";

type MotionBoundaryVariant = "public" | "system";

/**
 * Progressive route boundary for screens outside the authenticated app shells.
 * Auth intentionally does not use this boundary: its shell and card stay fixed,
 * while only the active form panel transitions locally.
 */
export default function MotionBoundary({
  children,
  variant,
}: {
  children: ReactElement;
  variant: MotionBoundaryVariant;
}) {
  return (
    <ViewTransition name="lumilens-public-workspace" default={`lumilens-route-${variant}`}>
      {children}
    </ViewTransition>
  );
}
