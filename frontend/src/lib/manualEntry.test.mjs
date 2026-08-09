import assert from "node:assert/strict";
import test from "node:test";

import { buildManualIndicators, MANUAL_ANALYTES } from "./manualEntry.mjs";

test("manual form contains exactly the four currently approved analytes", () => {
  assert.deepEqual(
    MANUAL_ANALYTES.map((item) => item.name),
    ["WBC", "RBC", "Glucose", "Creatinine"],
  );
});

test("blank fields are omitted and configured units are preserved", () => {
  assert.deepEqual(
    buildManualIndicators({ WBC: "7.5", RBC: "", Glucose: "5.2" }),
    [
      { name: "WBC", value: 7.5, unit: "10^9/L" },
      { name: "Glucose", value: 5.2, unit: "mmol/L" },
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
