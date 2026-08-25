import assert from "node:assert/strict";
import test from "node:test";

import { tokenizeInlineMarkdown } from "./inlineMarkdown.mjs";

test("plain text with no markdown returns a single text token", () => {
  assert.deepEqual(tokenizeInlineMarkdown("Vào menu Lịch sử kết quả."), [
    { type: "text", value: "Vào menu Lịch sử kết quả." },
  ]);
});

test("bold segment is tokenized separately from surrounding text", () => {
  assert.deepEqual(tokenizeInlineMarkdown('Bấm **"Tải ảnh phiếu"** để tiếp tục.'), [
    { type: "text", value: "Bấm " },
    { type: "bold", value: '"Tải ảnh phiếu"' },
    { type: "text", value: " để tiếp tục." },
  ]);
});

test("inline code segment is tokenized separately", () => {
  assert.deepEqual(tokenizeInlineMarkdown("Xem route `/patient/history`."), [
    { type: "text", value: "Xem route " },
    { type: "code", value: "/patient/history" },
    { type: "text", value: "." },
  ]);
});

test("multiple bold segments across lines all tokenize", () => {
  const text = '1. Chọn **"Nhập tay"**.\n2. Bấm **"Phân tích kết quả"**.';
  const tokens = tokenizeInlineMarkdown(text);
  const bold = tokens.filter((t) => t.type === "bold").map((t) => t.value);
  assert.deepEqual(bold, ['"Nhập tay"', '"Phân tích kết quả"']);
  // Line breaks must survive untouched inside text tokens (CSS handles
  // rendering them via white-space: pre-wrap).
  assert.ok(tokens.some((t) => t.type === "text" && t.value.includes("\n")));
});

test("unmatched ** or backtick (odd count) is left as literal text", () => {
  assert.deepEqual(tokenizeInlineMarkdown("giá trị 5** trên 10"), [
    { type: "text", value: "giá trị 5** trên 10" },
  ]);
});

test("empty string returns no tokens", () => {
  assert.deepEqual(tokenizeInlineMarkdown(""), []);
});
