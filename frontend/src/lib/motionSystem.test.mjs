import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(path, "utf8");

test("motion tokens in motion.ts match canonical values", async () => {
  const { MOTION_DURATIONS, MOTION_EASINGS, MAX_STAGGER_ITEMS, STAGGER_INTERVAL_MS, motionElementName } = await import("./motion.ts");

  assert.equal(MOTION_DURATIONS.instant, 100);
  assert.equal(MOTION_DURATIONS.fast, 140);
  assert.equal(MOTION_DURATIONS.base, 220);
  assert.equal(MOTION_DURATIONS.surface, 280);
  assert.equal(MOTION_DURATIONS.signature, 360);
  assert.equal(MOTION_DURATIONS.page, 280);
  assert.equal(MOTION_DURATIONS.slow, 320);
  assert.equal(MOTION_DURATIONS.chatOpen, 360);
  assert.equal(MOTION_DURATIONS.chatClose, 200);

  assert.equal(MOTION_EASINGS.standard, "cubic-bezier(0.2, 0.8, 0.2, 1)");
  assert.equal(MOTION_EASINGS.enter, "cubic-bezier(0.16, 1, 0.3, 1)");
  assert.equal(MOTION_EASINGS.exit, "cubic-bezier(0.4, 0, 1, 1)");

  assert.equal(MAX_STAGGER_ITEMS, 8);
  assert.equal(STAGGER_INTERVAL_MS, 15);
  assert.equal(motionElementName("patient report", "abc/123"), "lumilens-patient-report-abc-123");
});

test("CSS motion foundation defines canonical variables and keyframes in globals.css", () => {
  const css = read("src/app/globals.css");

  assert.match(css, /--motion-instant:\s*100ms;/);
  assert.match(css, /--motion-fast:\s*140ms;/);
  assert.match(css, /--motion-base:\s*220ms;/);
  assert.match(css, /--motion-surface:\s*280ms;/);
  assert.match(css, /--motion-signature:\s*360ms;/);
  assert.match(css, /--motion-page:\s*280ms;/);
  assert.match(css, /--motion-slow:\s*320ms;/);
  assert.match(css, /--motion-chat-open:\s*360ms;/);
  assert.match(css, /--motion-chat-close:\s*200ms;/);

  assert.match(css, /--ease-standard:\s*cubic-bezier\(0\.2,\s*0\.8,\s*0\.2,\s*1\);/);
  assert.match(css, /--ease-enter:\s*cubic-bezier\(0\.16,\s*1,\s*0\.3,\s*1\);/);
  assert.match(css, /--ease-exit:\s*cubic-bezier\(0\.4,\s*0,\s*1,\s*1\);/);

  assert.match(css, /@keyframes lumilab-page-enter/);
  assert.match(css, /@keyframes lumilab-tab-crossfade/);
  assert.match(css, /@keyframes lumilab-row-stagger/);
  assert.match(css, /@keyframes lumilab-chat-open/);
  assert.match(css, /@keyframes lumilab-chat-close/);
  assert.match(css, /@keyframes lumilab-chat-view-backward/);
  assert.match(css, /@keyframes lumilab-chat-view-forward/);
  assert.match(css, /@keyframes lumilab-message-enter/);
  assert.match(css, /@keyframes lumilab-thinking-pulse/);
  assert.match(css, /@keyframes lumilens-resolving-edge/);
  assert.match(css, /::view-transition-group\(\.lumilens-shared-detail\)/);
});

test("all shells delegate route transition to RouteTransition component without remounting shell chrome", () => {
  const patient = read("src/components/patient/PatientShell.tsx");
  const doctor = read("src/components/doctor/DoctorShell.tsx");
  const admin = read("src/components/admin/AdminShell.tsx");
  const routeTransition = read("src/components/common/RouteTransition.tsx");

  assert.match(routeTransition, /export default function RouteTransition/);
  assert.match(routeTransition, /usePathname\(\)/);
  assert.match(routeTransition, /<ViewTransition/);
  assert.match(routeTransition, /data-motion-route=\{variant\}/);

  assert.match(patient, /<RouteTransition variant="patient">{children}<\/RouteTransition>/);
  assert.match(doctor, /<RouteTransition variant="doctor">{children}<\/RouteTransition>/);
  assert.match(admin, /<RouteTransition variant="admin">{children}<\/RouteTransition>/);

  // AppShell itself must NOT be keyed by pathname
  assert.doesNotMatch(patient, /<AppShell[^>]*key=/);
  assert.doesNotMatch(doctor, /<AppShell[^>]*key=/);
  assert.doesNotMatch(admin, /<AppShell[^>]*key=/);
});

test("assistant chatbot implements deterministic visibility state machine and lifecycle", () => {
  const widget = read("src/components/patient/AssistantWidget.tsx");
  const panel = read("src/components/patient/assistant/ChatPanel.tsx");

  assert.match(widget, /useState<AssistantVisibility>\("closed"\)/);
  assert.match(widget, /setVisibility\("opening"\)/);
  assert.match(widget, /setVisibility\("closing"\)/);
  assert.match(widget, /setVisibility\("open"\)/);
  assert.match(widget, /setVisibility\("closed"\)/);
  assert.match(widget, /handleAnimationEnd/);
  assert.match(widget, /onAnimationEnd=\{handleAnimationEnd\}/);

  assert.match(panel, /data-state=\{state\}/);
  assert.match(panel, /onAnimationEnd=\{onAnimationEnd\}/);
});

test("prefers-reduced-motion is explicitly supported across all motion primitives", () => {
  const css = read("src/app/globals.css");

  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
  assert.match(css, /\.motion-route/);
  assert.match(css, /\.motion-row-stagger/);
  assert.match(css, /\.assistant-panel/);
  assert.match(css, /\.assistant-thinking-dots/);
});
