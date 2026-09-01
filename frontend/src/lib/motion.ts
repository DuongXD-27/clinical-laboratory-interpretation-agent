/**
 * LumiLab Clinical Motion Tokens
 *
 * Canonical motion language foundation:
 * - Quiet, spatial, restrained, clinical.
 * - No bouncy physics, no neon glow, no continuous medical alert animations.
 * - Respects prefers-reduced-motion globally.
 */

export const MOTION_DURATIONS = {
  instant: 100,
  fast: 140,
  base: 220,
  surface: 280,
  signature: 360,
  // Compatibility aliases used by existing clinical surfaces.
  page: 280,
  slow: 320,
  chatOpen: 360,
  chatClose: 200,
} as const;

export const MOTION_EASINGS = {
  standard: "cubic-bezier(0.2, 0.8, 0.2, 1)",
  enter: "cubic-bezier(0.16, 1, 0.3, 1)",
  exit: "cubic-bezier(0.4, 0, 1, 1)",
} as const;

export const MOTION_CSS_VARS = {
  durationInstant: "var(--motion-instant)",
  durationFast: "var(--motion-fast)",
  durationBase: "var(--motion-base)",
  durationSurface: "var(--motion-surface)",
  durationSignature: "var(--motion-signature)",
  durationPage: "var(--motion-page)",
  durationSlow: "var(--motion-slow)",
  durationChatOpen: "var(--motion-chat-open)",
  durationChatClose: "var(--motion-chat-close)",
  easeStandard: "var(--ease-standard)",
  easeEnter: "var(--ease-enter)",
  easeExit: "var(--ease-exit)",
} as const;

/**
 * Maximum items to stagger in a single list to prevent late items from stalling.
 */
export const MAX_STAGGER_ITEMS = 8;
export const STAGGER_INTERVAL_MS = 15;

export type AssistantVisibility = "closed" | "opening" | "open" | "closing";

/** Create a stable CSS custom-ident-safe name for shared ViewTransition elements. */
export function motionElementName(scope: string, id: string | number): string {
  const safeScope = scope.replace(/[^a-zA-Z0-9_-]/g, "-");
  const safeId = String(id).replace(/[^a-zA-Z0-9_-]/g, "-");
  return `lumilens-${safeScope}-${safeId}`;
}
