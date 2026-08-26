import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("OCR review presents ambiguous analytes as needing review", () => {
  const panel = readFileSync("src/components/OcrReviewPanel.tsx", "utf8");

  assert.match(panel, /Một số chỉ số cần được xem lại/);
  assert.match(panel, /row\.unsupported_reason/);
  assert.doesNotMatch(panel, /Một số chỉ số hiện chưa được hỗ trợ/);
});
