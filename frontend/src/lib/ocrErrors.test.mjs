import assert from "node:assert/strict";
import test from "node:test";

import { friendlyOcrError } from "./ocrErrors.mjs";

test("stable OCR reason takes precedence over provider detail", () => {
  assert.match(friendlyOcrError(503, "internal provider detail", "PROVIDER_UNAVAILABLE"), /tạm thời/);
});

test("safe client detail remains available for uncategorized validation failures", () => {
  assert.equal(friendlyOcrError(422, "Hãy xác nhận dữ liệu.", null), "Hãy xác nhận dữ liệu.");
});

test("server failure does not expose arbitrary provider detail", () => {
  assert.doesNotMatch(friendlyOcrError(500, "secret upstream failure", null), /secret/);
});
