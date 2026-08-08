import assert from "node:assert/strict";
import test from "node:test";

import { parseFiniteLabValue } from "./ocrReviewValidation.mjs";

test("rejects empty values instead of converting them to zero", () => {
  assert.equal(parseFiniteLabValue(""), null);
  assert.equal(parseFiniteLabValue("   "), null);
});

test("rejects non-finite values", () => {
  assert.equal(parseFiniteLabValue(Number.NaN), null);
  assert.equal(parseFiniteLabValue(Number.POSITIVE_INFINITY), null);
  assert.equal(parseFiniteLabValue("Infinity"), null);
});

test("accepts finite numeric values including a real zero", () => {
  assert.equal(parseFiniteLabValue("5.2"), 5.2);
  assert.equal(parseFiniteLabValue(0), 0);
  assert.equal(parseFiniteLabValue("0"), 0);
});
