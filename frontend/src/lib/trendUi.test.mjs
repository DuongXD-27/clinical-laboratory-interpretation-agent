import assert from "node:assert/strict";
import test from "node:test";

import {
  assessmentText,
  canRenderTrendChart,
  defaultTrendAnalyte,
  formatTrendDate,
  trendReasonMessage,
  TREND_INSUFFICIENT_MESSAGE,
} from "./trendUi.mjs";

test("selects the first eligible analyte as Trend default", () => {
  assert.equal(
    defaultTrendAnalyte([
      { analyte_canonical: "Creatinine", trend_available: false },
      { analyte_canonical: "LDL-C", trend_available: true },
      { analyte_canonical: "Glucose", trend_available: true },
    ]),
    "LDL-C",
  );
  assert.equal(defaultTrendAnalyte([{ analyte_canonical: "Potassium", trend_available: false }]), "");
});

test("chart renders only when backend marks trend available and returns at least three points", () => {
  assert.equal(canRenderTrendChart({ trend_available: true, points: [{}, {}, {}] }), true);
  assert.equal(canRenderTrendChart({ trend_available: true, points: [{}, {}] }), false);
  assert.equal(canRenderTrendChart({ trend_available: false, points: [{}, {}, {}] }), false);
});

test("maps backend Trend reasons to specific Vietnamese messages", () => {
  assert.equal(trendReasonMessage("INSUFFICIENT_DATA"), TREND_INSUFFICIENT_MESSAGE);
  assert.match(trendReasonMessage("DATA_QUALITY_ERROR"), /chưa nhất quán/);
  assert.match(trendReasonMessage("ANALYTE_NOT_FOUND"), /chưa có trong lịch sử/);
});

test("formats Trend dates and assessments for Vietnamese UI", () => {
  assert.equal(formatTrendDate("2026-08-10"), "10/08/2026");
  assert.equal(formatTrendDate("not-a-date"), "not-a-date");
  assert.equal(assessmentText("high"), "Cao");
  assert.equal(assessmentText("critical_low"), "Rất thấp");
  assert.equal(assessmentText(""), "Không rõ");
});
