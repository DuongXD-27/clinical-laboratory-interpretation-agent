import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import {
  authoritativeCriticalAlerts,
  canSubmitMessage,
  composerKeyAction,
  consumeSseStream,
  createStreamEventGuard,
  isCurrentRequest,
  progressLabel,
  safeHttpSources,
} from "./orchestratorChat.mjs";

const response = {
  intent: "EXPLAIN_CURRENT_RESULT",
  status: "success",
  message: "Giải thích an toàn.",
  data_type: "explanation",
  data: { data_type: "explanation", explanation: "Giải thích an toàn.", sources: [] },
};

function event(sequence, eventType, payload) {
  return {
    contract_version: "1.0",
    event_id: `event-${sequence}`,
    event_type: eventType,
    turn_id: "public-turn",
    sequence,
    occurred_at: "2026-08-22T00:00:00Z",
    payload,
  };
}

function frame(value) {
  return `event: ${value.event_type}\nid: ${value.event_id}\ndata: ${JSON.stringify(value)}\n\n`;
}

test("Enter sends, Shift+Enter inserts a newline, and IME Enter never sends", () => {
  assert.equal(composerKeyAction({ key: "Enter" }), "send");
  assert.equal(composerKeyAction({ key: "Enter", shiftKey: true }), "newline");
  assert.equal(composerKeyAction({ key: "Enter", ctrlKey: true }), "send");
  assert.equal(composerKeyAction({ key: "Enter", metaKey: true }), "send");
  assert.equal(composerKeyAction({ key: "Enter", isComposing: true }), "none");
});

test("whitespace and a second active request cannot submit", () => {
  assert.equal(canSubmitMessage("   ", true, false), false);
  assert.equal(canSubmitMessage("WBC", false, false), false);
  assert.equal(canSubmitMessage("WBC", true, true), false);
  assert.equal(canSubmitMessage("WBC", true, false), true);
});

test("only the four frozen progress stages map to patient-facing labels", () => {
  assert.equal(progressLabel("routing"), "Đang hiểu câu hỏi");
  assert.equal(progressLabel("medical_context"), "Đang tìm dữ liệu xét nghiệm");
  assert.equal(progressLabel("longitudinal_retrieval"), "Đang kiểm tra dữ liệu theo thời gian");
  assert.equal(progressLabel("response_composition"), "Đang chuẩn bị câu trả lời");
  assert.equal(progressLabel("private_workflow"), null);
});

test("incremental SSE parsing ignores unknown progress and renders completion atomically", async () => {
  const wire = [
    frame(event(1, "message.started", {})),
    frame(event(2, "progress", { stage: "routing" })),
    frame(event(3, "progress", { stage: "private_workflow" })),
    frame(event(4, "content.delta", { delta: "must not render" })),
    "event: progress\ndata: not-json\n\n",
    frame(event(5, "message.completed", { response })),
  ].join("");
  const chunks = [wire.slice(0, 41), wire.slice(41, 173), wire.slice(173)];
  const stream = new ReadableStream({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(new TextEncoder().encode(chunk));
      controller.close();
    },
  });
  const received = [];
  const terminal = await consumeSseStream(stream, (value) => received.push(value));

  assert.deepEqual(received.map((value) => value.event_type), [
    "message.started",
    "progress",
    "message.completed",
  ]);
  assert.equal(received.some((value) => JSON.stringify(value).includes("must not render")), false);
  assert.deepEqual(terminal.payload.response, response);
});

test("sequence must increase and only the first terminal event is accepted", () => {
  const guard = createStreamEventGuard();
  assert.equal(guard.accept(event(1, "message.started", {}))?.sequence, 1);
  assert.throws(() => guard.accept(event(1, "progress", { stage: "routing" })), /sequence/i);

  const terminalGuard = createStreamEventGuard();
  assert.equal(terminalGuard.accept(event(1, "message.started", {}))?.sequence, 1);
  assert.equal(terminalGuard.accept(event(2, "message.completed", { response }))?.event_type, "message.completed");
  assert.equal(terminalGuard.accept(event(3, "error", { message: "late" })), null);
});

test("an SSE error is terminal and missing terminal fails safely", async () => {
  const errorWire = frame(event(1, "message.started", {})) + frame(event(2, "error", { message: "safe" }));
  const errorStream = new Blob([errorWire]).stream();
  assert.equal((await consumeSseStream(errorStream, () => {})).event_type, "error");

  const incomplete = new Blob([frame(event(1, "message.started", {}))]).stream();
  await assert.rejects(consumeSseStream(incomplete, () => {}), /terminal/i);
});

test("late events from an aborted or replaced request are ignored", () => {
  assert.equal(isCurrentRequest("request-a", "request-a", false), true);
  assert.equal(isCurrentRequest("request-a", "request-a", true), false);
  assert.equal(isCurrentRequest("request-b", "request-a", false), false);
  assert.equal(isCurrentRequest(null, "request-a", false), false);
});

test("source disclosure accepts only unique HTTP(S) URLs", () => {
  assert.deepEqual(
    safeHttpSources([
      "https://vmec.example/reference",
      "javascript:alert(1)",
      "file:///private/rag.txt",
      "https://vmec.example/reference",
      "http://who.example/fact",
    ]),
    ["https://vmec.example/reference", "http://who.example/fact"],
  );
});

test("critical presentation requires an authoritative alert and never infers from ordinary HIGH", () => {
  assert.deepEqual(authoritativeCriticalAlerts({
    data_type: "analysis",
    indicators: [{ name: "WBC", status: "HIGH", is_critical: false }],
    critical_alerts: [],
  }), []);
  const alert = { indicator_name: "Glucose", value: 0, unit: "mmol/L", message: "Cảnh báo có thẩm quyền" };
  assert.deepEqual(authoritativeCriticalAlerts({ data_type: "analysis", critical_alerts: [alert] }), [alert]);
  assert.deepEqual(authoritativeCriticalAlerts({ data_type: "trend", trend: { critical_alert: alert } }), [alert]);
});

test("component contract includes stop, retry, focus restoration, critical alerts, and safe sources", () => {
  const widget = readFileSync("src/components/patient/AssistantWidget.tsx", "utf8");
  const panel = readFileSync("src/components/patient/assistant/ChatPanel.tsx", "utf8");
  const composer = readFileSync("src/components/patient/assistant/ChatComposer.tsx", "utf8");
  const sources = readFileSync("src/components/patient/assistant/ChatSources.tsx", "utf8");
  const turn = readFileSync("src/components/patient/assistant/AssistantTurn.tsx", "utf8");
  const controller = readFileSync("src/components/patient/assistant/useOrchestratorChat.ts", "utf8");

  assert.match(widget, /launcherRef\.current\?\.focus/);
  assert.match(controller, /Đã dừng/);
  assert.match(turn, /Thử lại/);
  assert.match(panel, /Tin nhắn mới ↓/);
  assert.match(panel, /role="log"/);
  assert.match(composer, /isComposing/);
  assert.match(turn, /Cần chú ý khẩn/);
  assert.match(sources, /Nguồn tham khảo/);
  assert.doesNotMatch(turn, /indicator\.status === "HIGH".*CriticalAlert/s);
});

test("opening the assistant loads history metadata but never an old transcript", () => {
  const controller = readFileSync("src/components/patient/assistant/useOrchestratorChat.ts", "utf8");
  const panel = readFileSync("src/components/patient/assistant/ChatPanel.tsx", "utf8");

  assert.match(controller, /useEffect\(\(\) => \{[\s\S]*refreshConversations\(\)/);
  assert.doesNotMatch(controller, /pickInitialConversation|localStorage/);
  assert.match(controller, /POST \/conversations là contract New Chat/);
  assert.match(panel, /"conversation" \| "history"/);
  assert.match(panel, /view === "history"/);
  assert.match(panel, /<ChatThreadList/);
});

test("responsive and reduced-motion CSS contract is explicit", () => {
  const css = readFileSync("src/app/globals.css", "utf8");
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*\.assistant-panel[\s\S]*height: 100dvh/);
  assert.match(css, /env\(safe-area-inset-bottom\)/);
  assert.match(css, /body\.assistant-mobile-open/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*\.assistant-panel/);
});
