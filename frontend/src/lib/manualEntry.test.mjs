import assert from "node:assert/strict";
import test from "node:test";

import { buildManualIndicators, MANUAL_ANALYTES } from "./manualEntry.mjs";

test("manual form contains exactly 35 analytes without duplicates", () => {
  assert.equal(MANUAL_ANALYTES.length, 35);
  const names = MANUAL_ANALYTES.map(a => a.name);
  assert.equal(new Set(names).size, 35);
});

test("blank fields are omitted and configured units are preserved", () => {
  assert.deepEqual(
    buildManualIndicators({ WBC: "7.5", RBC: "", "Fasting plasma glucose": "5.2", HbA1c: "5.6", Potassium: "4.2" }),
    [
      { name: "WBC", value: 7.5, unit: "10^9/L" },
      { name: "Potassium", value: 4.2, unit: "mmol/L" },
      { name: "Fasting plasma glucose", value: 5.2, unit: "mmol/L" },
      { name: "HbA1c", value: 5.6, unit: "%" },
    ],
  );
});

test("at least one value is required", () => {
  assert.throws(() => buildManualIndicators({}), /ít nhất một chỉ số/);
});

test("negative and non-finite values are rejected", () => {
  assert.throws(() => buildManualIndicators({ WBC: "-1" }), /số không âm/);
  assert.throws(() => buildManualIndicators({ WBC: "Infinity" }), /số không âm/);
});
