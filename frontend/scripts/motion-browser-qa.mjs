import { mkdirSync, writeFileSync } from "node:fs";
import { resolve } from "node:path";

const ORIGIN = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8000";
const CDP = "http://127.0.0.1:9222";
const artifactDir = resolve(process.cwd(), "..", "artifacts", "motion-qa");
mkdirSync(artifactDir, { recursive: true });

const delay = (ms) => new Promise((resolveDelay) => setTimeout(resolveDelay, ms));

class CdpClient {
  constructor(url) {
    this.url = url;
    this.id = 0;
    this.pending = new Map();
    this.listeners = new Map();
  }

  async connect() {
    this.socket = new WebSocket(this.url);
    await new Promise((resolveOpen, reject) => {
      this.socket.addEventListener("open", resolveOpen, { once: true });
      this.socket.addEventListener("error", reject, { once: true });
    });
    this.socket.addEventListener("message", (event) => {
      const payload = JSON.parse(event.data);
      if (payload.id) {
        const request = this.pending.get(payload.id);
        if (!request) return;
        this.pending.delete(payload.id);
        if (payload.error) request.reject(new Error(`${request.method}: ${payload.error.message}`));
        else request.resolve(payload.result);
        return;
      }
      for (const listener of this.listeners.get(payload.method) ?? []) {
        void listener(payload.params);
      }
    });
  }

  on(method, listener) {
    const listeners = this.listeners.get(method) ?? [];
    listeners.push(listener);
    this.listeners.set(method, listeners);
  }

  send(method, params = {}) {
    const id = ++this.id;
    return new Promise((resolveRequest, reject) => {
      this.pending.set(id, { resolve: resolveRequest, reject, method });
      this.socket.send(JSON.stringify({ id, method, params }));
    });
  }

  close() {
    this.socket.close();
  }
}

async function targetSocket() {
  const targets = await fetch(`${CDP}/json/list`).then((response) => response.json());
  const target = targets.find((item) => item.type === "page" && item.url.startsWith(ORIGIN));
  if (!target) throw new Error("No LumiLab browser target is connected to Chrome DevTools.");
  return target.webSocketDebuggerUrl;
}

const client = new CdpClient(await targetSocket());
await client.connect();
await Promise.all([
  client.send("Page.enable"),
  client.send("Runtime.enable"),
  client.send("Log.enable"),
  client.send("Network.enable"),
]);
await client.send("Page.bringToFront");
await client.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] });

const browserErrors = [];
client.on("Runtime.exceptionThrown", ({ exceptionDetails }) => {
  browserErrors.push(`exception: ${exceptionDetails.text ?? "unknown"}`);
});
client.on("Runtime.consoleAPICalled", ({ type, args }) => {
  if (type !== "error") return;
  browserErrors.push(`console: ${args.map((item) => item.value ?? item.description ?? "").join(" ")}`);
});
client.on("Log.entryAdded", ({ entry }) => {
  if (entry.level === "error") browserErrors.push(`log: ${entry.text}`);
});

async function evaluate(expression) {
  const result = await client.send("Runtime.evaluate", {
    expression,
    awaitPromise: true,
    returnByValue: true,
    userGesture: true,
  });
  if (result.exceptionDetails) throw new Error(result.exceptionDetails.text ?? "Browser evaluation failed");
  return result.result.value;
}

async function navigate(path, settleMs = 480) {
  await client.send("Page.navigate", { url: `${ORIGIN}${path}` });
  for (let attempt = 0; attempt < 40; attempt += 1) {
    await delay(100);
    const state = await evaluate("({ ready: document.readyState, href: location.href })").catch(() => null);
    if (state?.ready === "complete" && state.href.startsWith(ORIGIN)) break;
  }
  await delay(settleMs);
}

async function viewport(width, height) {
  await client.send("Emulation.setDeviceMetricsOverride", {
    width,
    height,
    deviceScaleFactor: 1,
    mobile: width <= 430,
    screenWidth: width,
    screenHeight: height,
  });
}

async function screenshot(name) {
  const shot = await client.send("Page.captureScreenshot", {
    format: "png",
    fromSurface: true,
    captureBeyondViewport: false,
  });
  writeFileSync(resolve(artifactDir, `${name}.png`), Buffer.from(shot.data, "base64"));
}

async function apiLogin(username, password) {
  return evaluate(`(async () => {
    const response = await fetch(${JSON.stringify(`${API}/api/v1/auth/login`)}, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(${JSON.stringify({ username, password })}),
    });
    if (!response.ok) return { ok: false, status: response.status };
    const data = await response.json();
    return { ok: true, token: data.access_token, role: data.role, username: data.username };
  })()`);
}

async function setSession(session) {
  await evaluate(`(() => {
    localStorage.setItem("vmec05_token", ${JSON.stringify(session.token)});
    localStorage.setItem("vmec05_role", ${JSON.stringify(session.role)});
    localStorage.setItem("vmec05_username", ${JSON.stringify(session.username)});
  })()`);
}

const sampleTrace = {
  request_id: "qa-motion-trace",
  created_at: "2026-09-01T06:30:00Z",
  method: "POST",
  path: "/api/v1/orchestrator/chat",
  status_code: 200,
  duration_ms: 1820,
  db_query_count: 7,
  db_ms: 120,
  llm_call_count: 1,
  llm_ms: 1380,
  llm_error_count: 0,
  user_role: "patient",
  server_timing: "http-total;dur=1820, db;dur=120, llm;dur=1380",
};

const latencyGroup = {
  group: "ai",
  count: 24,
  p50_ms: 1420,
  p95_ms: 4200,
  p99_ms: 5300,
  max_ms: 5600,
  error_count: 1,
  error_rate_pct: 4.2,
  requests_per_min: 1.6,
  llm_call_count: 22,
  llm_error_count: 1,
  input_tokens: 18400,
  output_tokens: 7200,
  cost_usd: 1.84,
  unpriced_call_count: 0,
  cost_per_call_usd: 0.084,
  ttft_p50_ms: null,
  ttft_p95_ms: null,
  missing_usage_count: 0,
};

const timeseriesPoints = [0, 1, 2, 3].map((index) => ({
  start: `2026-09-01T0${index + 3}:00:00Z`,
  count: 5 + index,
  p50_ms: 1100 + index * 90,
  p95_ms: 3100 + index * 180,
  p99_ms: 3900 + index * 210,
  error_count: index === 2 ? 1 : 0,
  error_rate_pct: index === 2 ? 14.3 : 0,
  errors_by_type: index === 2 ? { provider_timeout: 1 } : {},
  input_tokens: 3200 + index * 400,
  output_tokens: 1200 + index * 180,
  cost_usd: 0.32 + index * 0.05,
  llm_call_count: 4 + index,
  llm_error_count: index === 2 ? 1 : 0,
  guardrail_fallback_count: index === 3 ? 1 : 0,
  guardrail_rewrite_count: 0,
  guardrail_fallback_rate_pct: index === 3 ? 12.5 : 0,
}));

function adminMock(url) {
  if (url.includes("/tracing/status")) {
    return { langfuse_configured: true, langfuse_host: "configured", masked: true, trace_persistence_enabled: true, retention_days: 30 };
  }
  if (url.includes("/traces/timeseries")) {
    return { group: "ai", bucket_minutes: 60, since: "2026-09-01T03:00:00Z", until: "2026-09-01T07:00:00Z", points: timeseriesPoints, error_types: ["provider_timeout"] };
  }
  if (url.includes("/traces/slo")) {
    return { overall_status: "HEALTHY", slos: [{ name: "quality", target_pct: 98, actual_pct: 99.2, status: "HEALTHY", sample_count: 24, budget_used_pct: 40, budget_remaining: 2, detail: "QA fixture" }], errors: [], window_hours: 24, thresholds_provisional: true };
  }
  if (url.includes("/traces/latency")) {
    return { ai: latencyGroup, api: { ...latencyGroup, group: "api", p50_ms: 84, p95_ms: 210, p99_ms: 380, max_ms: 460, llm_call_count: 0, input_tokens: 0, output_tokens: 0, cost_usd: 0, cost_per_call_usd: null }, window_hours: 24, window_minutes: null, streaming_enabled: false, pricing_updated: "2026-08-30" };
  }
  if (url.includes("/traces/summary")) {
    return { request_count: 48, avg_duration_ms: 680, max_duration_ms: 5600, llm_call_count: 22, llm_error_count: 1, server_error_count: 0, window_hours: 24 };
  }
  if (url.endsWith("/qa-motion-trace/spans")) {
    return { request_id: sampleTrace.request_id, rows: [{ name: "http-total", duration_ms: 1820, depth: 0, unaccounted_ms: 320, share_pct: 100 }, { name: "llm", duration_ms: 1380, depth: 1, unaccounted_ms: null, share_pct: 75.8 }, { name: "db", duration_ms: 120, depth: 1, unaccounted_ms: null, share_pct: 6.6 }], aggregates: [{ name: "llm", duration_ms: 1380 }, { name: "db", duration_ms: 120 }], total_ms: 1820 };
  }
  if (url.endsWith("/qa-motion-trace")) return sampleTrace;
  if (url.includes("/traces")) return { total: 1, items: [sampleTrace] };
  return null;
}

client.on("Fetch.requestPaused", async ({ requestId, request }) => {
  const body = adminMock(request.url);
  if (body === null) {
    await client.send("Fetch.continueRequest", { requestId });
    return;
  }
  await client.send("Fetch.fulfillRequest", {
    requestId,
    responseCode: 200,
    responseHeaders: [
      { name: "content-type", value: "application/json; charset=utf-8" },
      { name: "access-control-allow-origin", value: ORIGIN },
      { name: "access-control-allow-methods", value: "GET, OPTIONS" },
      { name: "access-control-allow-headers", value: "authorization, content-type" },
    ],
    body: Buffer.from(JSON.stringify(body)).toString("base64"),
  });
});
await client.send("Fetch.enable", { patterns: [{ urlPattern: `${API}/api/v1/admin/*`, requestStage: "Request" }] });

async function auditRoute(path, viewportName) {
  await navigate(path);
  const audit = await evaluate(`(() => {
    const semantic = [...document.querySelectorAll(".status-indicator, .critical-report-notice, .critical-banner, [data-family='clinical'], [data-family='trust']")];
    const semanticAnimations = semantic.flatMap((element) => element.getAnimations({ subtree: false }).map((animation) => ({
      target: element.className,
      state: element.getAttribute("data-state"),
      playState: animation.playState,
    })));
    const animations = document.getAnimations().map((animation) => {
      const timing = animation.effect?.getComputedTiming?.() ?? {};
      const target = animation.effect?.target;
      return {
        playState: animation.playState,
        duration: timing.duration,
        iterations: timing.iterations,
        name: animation.animationName ?? null,
        target: target instanceof Element ? target.className : null,
        allowedLoadingLoop: target instanceof Element
          ? Boolean(target.closest('[role="status"], [aria-busy="true"], [data-slot="spinner"]'))
          : false,
      };
    });
    const infinite = animations.filter((item) => item.playState === "running" && item.iterations === Infinity);
    return {
      href: location.pathname + location.search,
      title: document.title,
      heading: document.querySelector("h1, h2")?.textContent?.trim() ?? null,
      main: Boolean(document.querySelector("main")),
      overflowX: Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - innerWidth,
      infiniteAnimations: infinite.length,
      unsafeInfiniteAnimations: infinite.filter((item) => !item.allowedLoadingLoop),
      semanticAnimations,
      reduced: matchMedia("(prefers-reduced-motion: reduce)").matches,
      viewTransitions: typeof document.startViewTransition === "function",
    };
  })()`);
  return { viewport: viewportName, requested: path, ...audit };
}

await navigate("/login");
const patient = await apiLogin("benhnhan", "benhnhan123");
const doctor = await apiLogin("bacsi", "bacsi123");
if (!patient.ok || !doctor.ok) throw new Error(`Demo login failed: patient=${patient.status}, doctor=${doctor.status}`);

await setSession(patient);
await navigate("/patient/history");
const patientReportHref = await evaluate(`document.querySelector('a[href^="/patient/reports/"]')?.getAttribute("href") ?? "/patient/reports/1"`);
const patientReportId = patientReportHref.split("/").at(-1).split("?")[0];

await setSession(doctor);
await navigate("/doctor");
const doctorReportHref = await evaluate(`document.querySelector('a[href^="/doctor/reports/"]')?.getAttribute("href") ?? "/doctor/reports/1"`);
await navigate("/doctor/trend-reviews");
const doctorTrendHref = await evaluate(`document.querySelector('a[href^="/doctor/trend-reviews/"]')?.getAttribute("href") ?? "/doctor/trend-reviews/1"`);

const publicRoutes = ["/", "/privacy", "/login", "/route-that-does-not-exist"];
const patientRoutes = ["/patient", "/patient/analysis", "/patient/history", `/patient/history/${patientReportId}`, patientReportHref, "/patient/trends", "/patient/profile"];
const doctorRoutes = ["/doctor", doctorReportHref, "/doctor/trend-reviews", doctorTrendHref];
const adminRoutes = ["/admin", "/admin/traces/qa-motion-trace"];
const viewports = [
  [375, 667, "375x667"],
  [390, 844, "390x844"],
  [430, 932, "430x932"],
  [768, 1024, "768x1024"],
  [1024, 768, "1024x768"],
  [1366, 768, "1366x768"],
  [1440, 900, "1440x900"],
  [1920, 1080, "1920x1080"],
];

const audits = [];
for (const [width, height, viewportName] of viewports) {
  await viewport(width, height);
  for (const route of publicRoutes) audits.push(await auditRoute(route, viewportName));
  await setSession(patient);
  for (const route of patientRoutes) audits.push(await auditRoute(route, viewportName));
  await setSession(doctor);
  for (const route of doctorRoutes) audits.push(await auditRoute(route, viewportName));
  await setSession({ token: "qa-admin-token", role: "admin", username: "motion.qa" });
  for (const route of adminRoutes) audits.push(await auditRoute(route, viewportName));

  const representative = width <= 430
    ? "/patient/analysis"
    : width <= 768
      ? patientReportHref
      : width <= 1024
        ? "/patient/trends"
        : width <= 1366
          ? "/doctor"
          : width <= 1440
            ? doctorReportHref
            : "/admin";
  const role = representative.startsWith("/doctor") ? doctor : representative.startsWith("/admin") ? { token: "qa-admin-token", role: "admin", username: "motion.qa" } : patient;
  await setSession(role);
  await navigate(representative);
  await screenshot(`${viewportName}-${representative.replaceAll("/", "-").replace(/^-/, "") || "landing"}`);
}

// Auth panel rapid switching: the shell/card stays fixed while only the keyed form panel resolves.
await viewport(390, 844);
await navigate("/login");
const authRapid = await evaluate(`(async () => {
  const tabs = [...document.querySelectorAll('[role="tab"]')];
  for (let index = 0; index < 10; index += 1) tabs[index % tabs.length].click();
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 260));
  return {
    selected: tabs.find((tab) => tab.getAttribute("aria-selected") === "true")?.id,
    panelCount: document.querySelectorAll("#auth-access-panel").length,
    cardRect: document.querySelector(".auth-card")?.getBoundingClientRect().toJSON(),
  };
})()`);

// Patient route transition and chat portal lifecycle, including interrupted open/close.
await setSession(patient);
await navigate("/patient");
const patientTransition = await evaluate(`(async () => {
  document.querySelector('a[href="/patient/history"]')?.click();
  await new Promise((resolveDelay) => setTimeout(resolveDelay, 90));
  return { href: location.pathname, animations: document.getAnimations().filter((item) => item.playState === "running").length };
})()`);
await delay(450);
await navigate("/patient");
await evaluate(`document.querySelector(".assistant-launcher")?.click()`);
await delay(120);
await screenshot("chat-portal-opening-120ms");
await evaluate(`document.querySelector(".assistant-close")?.click()`);
await delay(260);
await evaluate(`document.querySelector(".assistant-launcher")?.click()`);
await delay(40);
await evaluate(`document.querySelector(".assistant-close")?.click()`);
await delay(260);
const chatRapid = await evaluate(`({
  panelState: document.querySelector(".assistant-panel")?.getAttribute("data-state"),
  panelHidden: document.querySelector(".assistant-panel")?.hidden,
  launcherVisible: Boolean(document.querySelector(".assistant-launcher")),
  activeLabel: document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.tagName,
})`);

// Reduced motion: no route sweep, shared morph, scale, stagger, chart draw, or chat portal transform.
await client.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "reduce" }] });
await setSession(patient);
await navigate("/patient");
await evaluate(`document.querySelector(".assistant-launcher")?.click()`);
await delay(40);
const reducedMotion = await evaluate(`(() => {
  const panel = document.querySelector(".assistant-panel");
  const semantic = [...document.querySelectorAll(".status-indicator")];
  return {
    media: matchMedia("(prefers-reduced-motion: reduce)").matches,
    panelState: panel?.getAttribute("data-state"),
    panelTransform: panel ? getComputedStyle(panel).transform : null,
    routeAfterDisplay: getComputedStyle(document.querySelector(".motion-route"), "::after").display,
    runningAnimations: document.getAnimations().filter((item) => item.playState === "running").length,
    semanticAnimations: semantic.reduce((count, element) => count + element.getAnimations({ subtree: false }).length, 0),
  };
})()`);
await screenshot("reduced-motion-patient");
await client.send("Emulation.setEmulatedMedia", { features: [{ name: "prefers-reduced-motion", value: "no-preference" }] });

const report = {
  generatedAt: new Date().toISOString(),
  routeCount: new Set(audits.map((item) => item.requested)).size,
  viewportCount: viewports.length,
  auditCount: audits.length,
  failures: audits.filter((item) => !item.main || item.overflowX > 2 || item.semanticAnimations.length > 0 || item.unsafeInfiniteAnimations.length > 0),
  unexpectedDestinations: audits.filter((item) => item.href !== item.requested && !item.requested.startsWith("/route-that-does-not-exist")),
  browserErrors: [...new Set(browserErrors)].filter((message) => !message.includes("favicon") && !message.includes("status of 404")),
  capability: audits[0] ? { viewTransitions: audits[0].viewTransitions } : null,
  authRapid,
  patientTransition,
  chatRapid,
  reducedMotion,
  routes: audits,
};

writeFileSync(resolve(artifactDir, "motion-browser-qa.json"), JSON.stringify(report, null, 2));
process.stdout.write(JSON.stringify({
  artifactDir,
  routeCount: report.routeCount,
  viewportCount: report.viewportCount,
  auditCount: report.auditCount,
  failureCount: report.failures.length,
  unexpectedDestinationCount: report.unexpectedDestinations.length,
  browserErrorCount: report.browserErrors.length,
  authRapid,
  patientTransition,
  chatRapid,
  reducedMotion,
}, null, 2));

client.close();
