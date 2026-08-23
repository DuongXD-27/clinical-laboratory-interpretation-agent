import assert from "node:assert/strict";
import test from "node:test";
import { parseServerTiming, splitTimings, timingLabel } from "./serverTiming.mjs";

// Chuoi that lay tu mot request /analyze tren may.
const REAL =
  "analysis-reference-range;dur=4.926, analysis-critical-detector;dur=0.073, " +
  "analysis-analyzer;dur=9426.725, analysis-generate-questions;dur=1.271, " +
  "analysis-guardrail;dur=4.893, analysis-graph-total;dur=9451.978, " +
  "analysis-response-map;dur=0.046, db-query;dur=4.603, http-total;dur=9469.1";

test("tach duoc tung chang tu chuoi Server-Timing that", () => {
  const entries = parseServerTiming(REAL);

  assert.equal(entries.length, 9);
  const analyzer = entries.find((e) => e.name === "analysis-analyzer");
  assert.equal(analyzer.durationMs, 9426.725);
});

test("chang TONG khong duoc tron voi chang chi tiet", () => {
  // http-total bao tron ca request, analysis-graph-total bao tron cac node.
  // Ve chung canh chang con la dem hai lan va moi ti le deu sai.
  const { totals, stages } = splitTimings(REAL);

  assert.deepEqual(
    totals.map((t) => t.name).sort(),
    ["analysis-graph-total", "http-total"],
  );
  assert.ok(!stages.some((s) => s.name === "http-total"));
  assert.ok(!stages.some((s) => s.name === "analysis-graph-total"));
});

test("chang duoc sap cham nhat len truoc", () => {
  // Nguoi mo man nay dang di tim cho ton thoi gian, khong doc trinh tu thuc thi.
  const { stages, slowest } = splitTimings(REAL);

  assert.equal(stages[0].name, "analysis-analyzer");
  assert.equal(slowest, 9426.725);
  for (let i = 1; i < stages.length; i += 1) {
    assert.ok(stages[i - 1].durationMs >= stages[i].durationMs);
  }
});

test("db-query duoc danh dau la cong don", () => {
  // Mot request co the ban nhieu truy van; con so la tong, khong phai mot lan.
  const { stages } = splitTimings(REAL);
  const db = stages.find((s) => s.name === "db-query");

  assert.equal(db.isAccumulated, true);
});

test("chuoi rong hoac hong khong lam vo trang", () => {
  for (const bad of ["", null, undefined, "rac", "a;b", "x;dur=khongphaiso"]) {
    assert.deepEqual(parseServerTiming(bad), [], String(bad));
  }
  const { totals, stages, slowest } = splitTimings(null);
  assert.deepEqual(totals, []);
  assert.deepEqual(stages, []);
  assert.equal(slowest, 0);
});

test("chang la van hien ra, giu nguyen ten goc", () => {
  // Ai them mot timing_span moi thi no phai hien len chu khong bi nuot.
  const { stages } = splitTimings("chang-hoan-toan-moi;dur=12.5");

  assert.equal(stages.length, 1);
  assert.equal(stages[0].name, "chang-hoan-toan-moi");
  assert.equal(timingLabel("chang-hoan-toan-moi"), "chang-hoan-toan-moi");
});

test("chang da biet co nhan tieng Viet", () => {
  assert.equal(timingLabel("analysis-analyzer"), "Sinh giải thích (LLM)");
  assert.equal(timingLabel("db-query"), "Truy vấn CSDL");
});
