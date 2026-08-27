import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("OCR review presents unsupported analytes separately from confidence review", () => {
  const panel = readFileSync("src/components/OcrReviewPanel.tsx", "utf8");

  assert.match(panel, /Chỉ số chưa được hỗ trợ/);
  assert.match(panel, /Độ tin cậy OCR thấp/);
  assert.match(panel, /row\.unsupported_reason/);
});
