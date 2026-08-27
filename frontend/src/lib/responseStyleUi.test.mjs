import assert from "node:assert/strict";
import test from "node:test";
import {
  RESPONSE_STYLES,
  getResponseStyleLabel,
  isValidResponseStyle,
} from "./responseStyleUi.mjs";

test("contains concise, simple, and detailed response style options", () => {
  assert.equal(RESPONSE_STYLES.length, 3);
  const ids = RESPONSE_STYLES.map((s) => s.id);
  assert.deepEqual(ids, ["concise", "simple", "detailed"]);
});

test("returns correct display labels for styles", () => {
  assert.equal(getResponseStyleLabel("concise"), "Ngắn gọn");
  assert.equal(getResponseStyleLabel("simple"), "Dễ hiểu");
  assert.equal(getResponseStyleLabel("detailed"), "Chi tiết");
  assert.equal(getResponseStyleLabel("unknown_style"), "Dễ hiểu");
});

test("validates response style ids correctly", () => {
  assert.equal(isValidResponseStyle("concise"), true);
  assert.equal(isValidResponseStyle("simple"), true);
  assert.equal(isValidResponseStyle("detailed"), true);
  assert.equal(isValidResponseStyle("other"), false);
  assert.equal(isValidResponseStyle(null), false);
});
