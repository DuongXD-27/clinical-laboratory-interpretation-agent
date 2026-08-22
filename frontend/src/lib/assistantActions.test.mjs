import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import {
  actionDestination,
  ASSISTANT_ACTION_ALLOWLIST,
  proseNavigationDestination,
  sanitizeSuggestedAction,
  shouldOfferOcrConfirm,
} from "./assistantActions.mjs";

test("assistant action allowlist is exactly the frozen seven variants", () => {
  assert.deepEqual(ASSISTANT_ACTION_ALLOWLIST, [
    "OPEN_REPORT",
    "VIEW_ABNORMAL",
    "VIEW_HISTORY",
    "VIEW_TREND",
    "VIEW_DOCTOR_QUESTIONS",
    "CONFIRM_OCR",
    "RETRY",
  ]);
});

test("action renderer rejects unknown actions and arbitrary navigation payloads", () => {
  assert.equal(sanitizeSuggestedAction({ action: "OPEN_URL", url: "https://evil.example" }), null);
  assert.equal(sanitizeSuggestedAction({ action: "VIEW_HISTORY", url: "https://evil.example" }), null);
  assert.equal(sanitizeSuggestedAction({ action: "VIEW_TREND", analyte_id: "WBC", href: "/patient/history" }), null);
  assert.equal(sanitizeSuggestedAction({ action: "VIEW_HISTORY", patient_id: 1 }), null);
  assert.equal(sanitizeSuggestedAction({ action: "RETRY", reason_code: "javascript:alert(1)" }), null);
});

test("navigation destinations are derived only from valid structured actions", () => {
  assert.equal(actionDestination({ action: "VIEW_HISTORY" }), "/patient/history");
  assert.equal(actionDestination({ action: "OPEN_REPORT", report_ref: "42" }), "/patient/reports/42");
  assert.equal(actionDestination({ action: "VIEW_TREND", analyte_id: "HbA1c" }), "/patient/trends?analyte=HbA1c");
  assert.equal(actionDestination({ action: "VIEW_HISTORY", url: "javascript:alert(1)" }), null);
});

test("guest protected actions do not produce patient data destinations", () => {
  assert.equal(actionDestination({ action: "VIEW_HISTORY" }, "guest"), null);
  assert.equal(actionDestination({ action: "VIEW_TREND", analyte_id: "WBC" }, "guest"), null);
  assert.equal(actionDestination({ action: "OPEN_REPORT", report_ref: "42" }, "guest"), null);
});

test("OCR review action routes only to the existing OCR review interface", () => {
  const response = {
    reason_code: "OCR_REVIEW_REQUIRED",
    suggested_actions: [{ action: "CONFIRM_OCR", review_ref: "ocr-review" }],
  };

  assert.equal(shouldOfferOcrConfirm(response), true);
  assert.equal(actionDestination(response.suggested_actions[0]), "/patient/analysis?mode=ocr");
  assert.equal(sanitizeSuggestedAction({ action: "CONFIRM_OCR", review_ref: "ocr-review", skip: true }), null);
});

test("assistant never creates navigation from prose text", () => {
  assert.equal(proseNavigationDestination("xem lịch sử"), null);
  assert.equal(proseNavigationDestination("https://evil.example"), null);
  assert.equal(proseNavigationDestination("javascript:alert(1)"), null);
});

test("patient shell mounts the assistant launcher and component owns onboarding UI", () => {
  const shell = readFileSync("src/components/patient/PatientShell.tsx", "utf8");
  const widget = readFileSync("src/components/patient/AssistantWidget.tsx", "utf8");
  const panel = readFileSync("src/components/patient/assistant/ChatPanel.tsx", "utf8");
  const controller = readFileSync("src/components/patient/assistant/useOrchestratorChat.ts", "utf8");
  const css = readFileSync("src/app/globals.css", "utf8");

  assert.match(shell, /<AssistantWidget role=\{session\.role\} \/>/);
  assert.match(widget, /aria-label=\{open \? "Đóng trợ lý AI" : "Mở trợ lý AI"\}/);
  assert.match(widget, /acknowledgeOrchestratorOnboarding/);
  assert.match(controller, /ONBOARDING_REQUIRED/);
  assert.match(panel, /Trước khi bắt đầu/);
  assert.match(css, /\.assistant-panel/);
  assert.match(css, /height: 100dvh/);
});
