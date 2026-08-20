import assert from "node:assert/strict";
import test from "node:test";

import {
  assessmentText,
  canRenderTrendChart,
  dedupeTrendPoints,
  defaultTrendAnalyte,
  formatTrendDate,
  groupBySection,
  groupableSections,
  sectionFallbackReason,
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
  assert.match(trendReasonMessage("GAP_TOO_LARGE"), /cách nhau quá xa/);
});

test("formats Trend dates and assessments for Vietnamese UI", () => {
  assert.equal(formatTrendDate("2026-08-10"), "10/08/2026");
  assert.equal(formatTrendDate("not-a-date"), "not-a-date");
  assert.equal(assessmentText("high"), "Cao");
  assert.equal(assessmentText("critical_low"), "Rất thấp");
  assert.equal(assessmentText(""), "Không rõ");
});

test("groups items by section_label in the fixed CRIT-TREND-06 display order", () => {
  const groups = groupBySection([
    { analyte_canonical: "LDL-C", section_label: "Mỡ máu & đường huyết" },
    { analyte_canonical: "WBC", section_label: "Huyết học" },
    { analyte_canonical: "Creatinine", section_label: "Sinh hóa thận - gan" },
    { analyte_canonical: "RBC", section_label: "Huyết học" },
  ]);

  assert.deepEqual(
    groups.map((group) => group.label),
    ["Huyết học", "Sinh hóa thận - gan", "Mỡ máu & đường huyết"],
  );
  assert.deepEqual(
    groups[0].items.map((item) => item.analyte_canonical),
    ["WBC", "RBC"],
  );
});

test("items without a section_label fall into a trailing Khác group", () => {
  const groups = groupBySection([
    { analyte_canonical: "LDL-C", section_label: "Mỡ máu & đường huyết" },
    { analyte_canonical: "Mystery" },
  ]);

  assert.deepEqual(
    groups.map((group) => group.label),
    ["Mỡ máu & đường huyết", "Khác"],
  );
  assert.equal(groups[1].items[0].analyte_canonical, "Mystery");
});

test("groupBySection tolerates a missing or empty list", () => {
  assert.deepEqual(groupBySection(undefined), []);
  assert.deepEqual(groupBySection([]), []);
});

test("groupableSections keeps sections with at least one eligible analyte and excludes 'other'", () => {
  const groups = groupableSections([
    { analyte_canonical: "WBC", section: "hematology", section_label: "Huyết học", trend_available: true },
    { analyte_canonical: "RBC", section: "hematology", section_label: "Huyết học", trend_available: true },
    { analyte_canonical: "LDL-C", section: "lipids", section_label: "Mỡ máu & đường huyết", trend_available: true },
    { analyte_canonical: "HbA1c", section: "lipids", section_label: "Mỡ máu & đường huyết", trend_available: false },
    { analyte_canonical: "Creatinine", section: "chemistry", section_label: "Sinh hóa thận - gan", trend_available: true },
    { analyte_canonical: "Mystery", section: "other", section_label: "Khác", trend_available: true },
    { analyte_canonical: "WithoutSection", trend_available: true },
  ]);

  assert.deepEqual(groups, [
    { key: "hematology", label: "Huyết học", eligible: 2 },
    { key: "chemistry", label: "Sinh hóa thận - gan", eligible: 1 },
    { key: "lipids", label: "Mỡ máu & đường huyết", eligible: 1 },
  ]);
});

test("groupableSections returns an empty list when no valid section has an eligible analyte", () => {
  assert.deepEqual(groupableSections([]), []);
  assert.deepEqual(
    groupableSections([
      { analyte_canonical: "HbA1c", section: "lipids", section_label: "Mỡ máu & đường huyết", trend_available: false },
      { analyte_canonical: "Mystery", section: "other", section_label: "Khác", trend_available: true },
    ]),
    [],
  );
  assert.deepEqual(groupableSections(undefined), []);
});

test("sectionFallbackReason maps backend fallback reasons to patient-friendly messages", () => {
  assert.match(sectionFallbackReason("INSUFFICIENT_DATA"), /chưa có đủ chỉ số/);
  assert.match(sectionFallbackReason("GUARDRAIL_BLOCKED"), /chưa đạt chuẩn an toàn/);
  assert.match(sectionFallbackReason("PROVIDER_ERROR"), /chưa khả dụng/);
  assert.match(sectionFallbackReason(null), /chưa khả dụng/);
});

test("dedupeTrendPoints keeps the newest report per test date in original order", () => {
  const points = [
    { report_id: 1, test_date: "2026-08-15", value: 4.0 },
    { report_id: 2, test_date: "2026-08-14", value: 5.0 },
    { report_id: 11, test_date: "2026-08-15", value: 6.0 },
    { report_id: 7, test_date: "2026-08-15", value: 5.5 },
  ];
  assert.deepEqual(
    dedupeTrendPoints(points).map((point) => point.report_id),
    [2, 11],
  );
});

test("dedupeTrendPoints tolerates missing lists and points without report_id", () => {
  assert.deepEqual(dedupeTrendPoints(undefined), []);
  assert.deepEqual(dedupeTrendPoints([]), []);
  const fallback = dedupeTrendPoints([{ test_date: "2026-08-15", value: 1 }]);
  assert.equal(fallback.length, 1);
  assert.deepEqual(dedupeTrendPoints([{ value: 1 }]), []);
});
