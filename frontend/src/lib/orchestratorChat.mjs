export const SAFE_PROGRESS_LABELS = Object.freeze({
  routing: "Đang hiểu câu hỏi",
  medical_context: "Đang tìm dữ liệu xét nghiệm",
  longitudinal_retrieval: "Đang kiểm tra dữ liệu theo thời gian",
  response_composition: "Đang chuẩn bị câu trả lời",
});

const TERMINAL_EVENTS = new Set(["message.completed", "error"]);
const KNOWN_EVENTS = new Set(["message.started", "progress", ...TERMINAL_EVENTS]);

function isObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function progressLabel(stage) {
  return typeof stage === "string" && Object.hasOwn(SAFE_PROGRESS_LABELS, stage)
    ? SAFE_PROGRESS_LABELS[stage]
    : null;
}

export function composerKeyAction({
  key,
  shiftKey = false,
  ctrlKey = false,
  metaKey = false,
  isComposing = false,
}) {
  if (isComposing || key !== "Enter") return "none";
  if (shiftKey && !ctrlKey && !metaKey) return "newline";
  return "send";
}

export function canSubmitMessage(message, onboardingAccepted, requestActive) {
  return Boolean(onboardingAccepted && !requestActive && typeof message === "string" && message.trim());
}

export function isCurrentRequest(activeRequestId, eventRequestId, aborted) {
  return Boolean(!aborted && activeRequestId && activeRequestId === eventRequestId);
}

export function safeHttpSources(sources) {
  const unique = new Set();
  for (const source of Array.isArray(sources) ? sources : []) {
    if (typeof source !== "string") continue;
    try {
      const url = new URL(source);
      if (url.protocol === "http:" || url.protocol === "https:") unique.add(url.href);
    } catch {
      // Invalid and non-public sources are intentionally omitted.
    }
  }
  return [...unique];
}

export function authoritativeCriticalAlerts(data) {
  if (!isObject(data)) return [];
  if (data.data_type === "analysis" && Array.isArray(data.critical_alerts)) {
    return data.critical_alerts.filter(isObject);
  }
  if (data.data_type === "trend" && isObject(data.trend) && isObject(data.trend.critical_alert)) {
    return [data.trend.critical_alert];
  }
  return [];
}

export function parseSseFrame(frame) {
  if (typeof frame !== "string" || !frame.trim()) return null;
  let wireEvent = null;
  const dataLines = [];
  for (const rawLine of frame.split(/\r?\n/)) {
    if (rawLine.startsWith("event:")) wireEvent = rawLine.slice(6).trim();
    if (rawLine.startsWith("data:")) dataLines.push(rawLine.slice(5).trimStart());
  }
  if (dataLines.length === 0) return null;

  try {
    const parsed = JSON.parse(dataLines.join("\n"));
    if (!isObject(parsed)) return null;
    if (parsed.contract_version !== "1.0") return null;
    if (typeof parsed.event_id !== "string" || typeof parsed.turn_id !== "string") return null;
    if (!Number.isInteger(parsed.sequence) || parsed.sequence < 1) return null;
    if (typeof parsed.event_type !== "string" || !isObject(parsed.payload)) return null;
    if (wireEvent && wireEvent !== parsed.event_type) return null;
    return parsed;
  } catch {
    return null;
  }
}

function isPublicResponse(value) {
  return isObject(value)
    && typeof value.intent === "string"
    && typeof value.status === "string"
    && typeof value.message === "string"
    && typeof value.data_type === "string"
    && isObject(value.data);
}

export function createStreamEventGuard() {
  let lastSequence = 0;
  let publicTurnId = null;
  let started = false;
  let terminal = false;

  return {
    accept(value) {
      if (!isObject(value) || terminal) return null;
      if (!Number.isInteger(value.sequence) || value.sequence <= lastSequence) {
        throw new Error("Invalid stream sequence ordering");
      }

      if (!started) {
        if (value.event_type !== "message.started") {
          if (!KNOWN_EVENTS.has(value.event_type)) return null;
          throw new Error("Stream must start with message.started");
        }
        started = true;
        publicTurnId = value.turn_id;
      } else if (value.turn_id !== publicTurnId) {
        throw new Error("Stream turn changed unexpectedly");
      }

      lastSequence = value.sequence;
      if (!KNOWN_EVENTS.has(value.event_type)) return null;
      if (value.event_type === "message.started" && lastSequence !== 1) {
        throw new Error("Duplicate message.started event");
      }
      if (value.event_type === "progress" && !progressLabel(value.payload.stage)) return null;
      if (value.event_type === "message.completed" && !isPublicResponse(value.payload.response)) {
        throw new Error("Invalid completed response");
      }
      if (value.event_type === "error" && typeof value.payload.message !== "string") {
        throw new Error("Invalid stream error");
      }
      if (TERMINAL_EVENTS.has(value.event_type)) terminal = true;
      return value;
    },
  };
}

export async function consumeSseStream(stream, onEvent) {
  if (!stream || typeof stream.getReader !== "function") {
    throw new Error("Stream response has no readable body");
  }
  const reader = stream.getReader();
  const decoder = new TextDecoder();
  const guard = createStreamEventGuard();
  let buffer = "";
  let terminal = null;

  try {
    while (!terminal) {
      const { done, value } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      const frames = buffer.split(/\r?\n\r?\n/);
      buffer = frames.pop() ?? "";
      for (const rawFrame of frames) {
        const parsed = parseSseFrame(rawFrame);
        if (!parsed) continue;
        const accepted = guard.accept(parsed);
        if (!accepted) continue;
        onEvent(accepted);
        if (TERMINAL_EVENTS.has(accepted.event_type)) {
          terminal = accepted;
          break;
        }
      }
      if (done) break;
    }
  } finally {
    if (terminal) await reader.cancel().catch(() => undefined);
    reader.releaseLock();
  }

  if (!terminal) throw new Error("Stream ended without a terminal event");
  return terminal;
}
