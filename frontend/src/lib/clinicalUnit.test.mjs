import assert from "node:assert/strict";
import test from "node:test";

import {
  canonicalizeClinicalUnitInput,
  formatClinicalText,
  formatClinicalUnit,
  formatClinicalUnitSuffix,
  formatClinicalValue,
} from "./clinicalUnit.mjs";

test("formats required scientific unit and value variants", () => {
  assert.equal(formatClinicalUnit("10^9/L"), "10⁹/L");
  assert.equal(formatClinicalUnit("10^12/L"), "10¹²/L");
  assert.equal(formatClinicalUnit("14.2 x 10^9/L"), "14.2 × 10⁹/L");
  assert.equal(formatClinicalUnit("4.3 x10^12/L"), "4.3 × 10¹²/L");
  assert.equal(formatClinicalUnit("250 g/L"), "250 g/L");
  assert.equal(formatClinicalUnit("500 mmol/L"), "500 mmol/L");
  assert.equal(formatClinicalUnit("10^-3/L"), "10⁻³/L");
});

test("supports spaced input, signed multi-digit exponents and multiplier variants", () => {
  assert.equal(formatClinicalUnit("10 ^ 9/L"), "10⁹/L");
  assert.equal(formatClinicalUnit("10^9 / L"), "10⁹/L");
  assert.equal(formatClinicalUnit("x10^9/L"), "× 10⁹/L");
  assert.equal(formatClinicalUnit("X 10^9/L"), "× 10⁹/L");
  assert.equal(formatClinicalUnit("* 10^9/L"), "× 10⁹/L");
  assert.equal(formatClinicalUnit("· 10^9/l"), "× 10⁹/L");
  assert.equal(formatClinicalUnit("×10^+12/L"), "× 10⁺¹²/L");
  assert.equal(formatClinicalUnit("10 ^ − 12 / l"), "10⁻¹²/L");
});

test("formats value context with one consistent multiplication sign", () => {
  assert.equal(formatClinicalUnitSuffix("10^9/L"), "× 10⁹/L");
  assert.equal(formatClinicalUnitSuffix("g/L"), "g/L");
  assert.equal(formatClinicalValue(14.2, "10^9/L"), "14.2 × 10⁹/L");
  assert.equal(formatClinicalValue("4.3", "10^12/L"), "4.3 × 10¹²/L");
  assert.equal(formatClinicalValue(250, "g/L"), "250 g/L");
});

test("clinical prose gains typography without changing unrelated caret text", () => {
  assert.equal(
    formatClinicalText("Chỉ số WBC của bạn là 14.2 10^9/L."),
    "Chỉ số WBC của bạn là 14.2 × 10⁹/L.",
  );
  assert.equal(formatClinicalText("a^2 + b^2 = c^2"), "a^2 + b^2 = c^2");
  assert.equal(formatClinicalText("Mã nguồn `10^9/L` không đổi."), "Mã nguồn `10^9/L` không đổi.");
  assert.equal(
    formatClinicalText("Xem https://example.test/reference/10^9/L để biết thêm"),
    "Xem https://example.test/reference/10^9/L để biết thêm",
  );
});

test("editable presentation round-trips to the existing canonical unit contract", () => {
  assert.equal(canonicalizeClinicalUnitInput("10⁹/L"), "10^9/L");
  assert.equal(canonicalizeClinicalUnitInput("× 10¹²/L"), "10^12/L");
  assert.equal(canonicalizeClinicalUnitInput("mmol/L"), "mmol/L");
});
