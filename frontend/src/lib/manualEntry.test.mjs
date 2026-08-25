import assert from "node:assert/strict";
import test from "node:test";

import {
  buildManualIndicators,
  MANUAL_ANALYTES,
  MANUAL_GROUP_LABELS,
  manualAnalyteAttentionMessage,
} from "./manualEntry.mjs";

test("manual form contains exactly 35 analytes without duplicates", () => {
  assert.equal(MANUAL_ANALYTES.length, 35);
  const names = MANUAL_ANALYTES.map(a => a.name);
  assert.equal(new Set(names).size, 35);
});

test("manual form carries canonical group and support status metadata", () => {
  const approved = MANUAL_ANALYTES.filter(a => a.runtimeStatus === "APPROVED").map(a => a.name).sort();
  assert.deepEqual(approved, [
    "ALT",
    "AST",
    "Albumin",
    "Chloride",
    "Creatinine",
    "Eosinophils %",
    "Eosinophils abs",
    "Fasting plasma glucose",
    "GGT",
    "HCT",
    "HDL-C",
    "HGB",
    "HbA1c",
    "LDL-C",
    "Lymphocytes %",
    "Lymphocytes abs",
    "MCH",
    "MCHC",
    "MCV",
    "Monocytes %",
    "Monocytes abs",
    "Neutrophils %",
    "Neutrophils abs",
    "PLT",
    "Potassium",
    "RBC",
    "RDW-CV",
    "Sodium",
    "Total bilirubin",
    "Total cholesterol",
    "Total protein",
    "Triglyceride",
    "Urea",
    "Uric acid",
    "WBC",
  ]);

  for (const analyte of MANUAL_ANALYTES) {
    assert.ok(analyte.analyteId);
    assert.ok(MANUAL_GROUP_LABELS[analyte.canonicalGroup]);
    assert.equal(analyte.category, MANUAL_GROUP_LABELS[analyte.canonicalGroup]);
    assert.ok(["APPROVED", "HOLD", "UNSUPPORTED"].includes(analyte.runtimeStatus));
  }
});

test("all locked manual analytes are approved after final runtime activation", () => {
  const uricAcid = MANUAL_ANALYTES.find(a => a.name === "Uric acid");

  assert.equal(uricAcid.runtimeStatus, "APPROVED");
  assert.equal(manualAnalyteAttentionMessage(uricAcid), "");
});

test("blank fields are omitted and configured units are preserved", () => {
  assert.deepEqual(
    buildManualIndicators({ WBC: "7.5", HCT: "0.43", RBC: "", "Fasting plasma glucose": "5.2", HbA1c: "5.6", Potassium: "4.2" }),
    [
      { name: "WBC", value: 7.5, unit: "10^9/L" },
      { name: "HCT", value: 0.43, unit: "L/L" },
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
