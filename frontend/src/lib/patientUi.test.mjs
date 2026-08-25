import assert from "node:assert/strict";
import test from "node:test";
import {
  formatDate,
  formatMoment,
  indicatorStatusText,
  reportStatusText,
  reportTone,
  sortIndicatorsBySeverity,
  sourceHostname,
} from "./patientUi.mjs";

test("formats ISO dates for Vietnamese display without changing the stored value", () => {
  assert.equal(formatDate("2026-08-11"), "11/08/2026");
  assert.equal(formatDate("2026-08-11T10:30:00Z"), "11/08/2026");
});

test("formats moments in Vietnam timezone regardless of browser timezone", () => {
  const formatted = formatMoment("2026-08-15T00:30:00Z");

  assert.match(formatted, /15\/08\/2026/);
  assert.match(formatted, /07:30/);
});

test("treats backend timestamps without timezone as UTC moments", () => {
  const isoWithoutZone = formatMoment("2026-08-15T06:37:31.521820");
  const sqlWithoutZone = formatMoment("2026-08-15 06:37:31.521820");

  assert.match(isoWithoutZone, /13:37/);
  assert.match(sqlWithoutZone, /13:37/);
});

test("maps backend statuses only at the presentation layer", () => {
  assert.equal(indicatorStatusText("NORMAL"), "Bình thường");
  assert.equal(indicatorStatusText("LOW"), "Thấp");
  assert.equal(indicatorStatusText("HIGH"), "Cao");
  assert.equal(indicatorStatusText("HIGH", "critical_high"), "Nguy kịch – cao");
  assert.equal(indicatorStatusText("LOW", "critical_low"), "Nguy kịch – thấp");
  assert.equal(indicatorStatusText("CRITICAL"), "Nguy kịch");
  assert.equal(indicatorStatusText("critical_high"), "Nguy kịch – cao");
  assert.equal(indicatorStatusText("critical_low"), "Nguy kịch – thấp");
  assert.equal(indicatorStatusText("ABNORMAL"), "Bất thường");
  assert.equal(reportStatusText("ABNORMAL"), "Có chỉ số bất thường");
  assert.equal(reportTone("LOW"), "abnormal");
});

test("orders result cards by severity without mutating the input", () => {
  const indicators = [
    { name: "HbA1c", status: "normal" },
    { name: "WBC", status: "high" },
    { name: "Uric acid", status: "unknown" },
    { name: "Potassium", status: "critical_high" },
    { name: "Glucose", status: "high" },
  ];
  const ordered = sortIndicatorsBySeverity(indicators);

  assert.deepEqual(
    ordered.map((i) => i.name),
    ["Potassium", "WBC", "Glucose", "Uric acid", "HbA1c"],
  );
  // original array untouched
  assert.equal(indicators[0].name, "HbA1c");
});

test("severity ordering keeps within-group order stable and handles empty input", () => {
  const indicators = [
    { name: "A", status: "high" },
    { name: "B", status: "high" },
  ];
  assert.deepEqual(
    sortIndicatorsBySeverity(indicators).map((i) => i.name),
    ["A", "B"],
  );
  assert.deepEqual(sortIndicatorsBySeverity(undefined), []);
});

test("uses a compact source label while preserving the original URL", () => {
  assert.equal(sourceHostname("https://www.mayoclinic.org/tests"), "mayoclinic.org");
});
