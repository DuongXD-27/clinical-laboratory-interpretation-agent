import assert from "node:assert/strict";
import { test } from "node:test";

import {
  CATEGORICAL_DARK,
  CATEGORICAL_LIGHT,
  MAX_SERIES,
  OTHER_LABEL,
  categoricalColor,
  errorLabel,
  foldToMaxSeries,
} from "./chartPalette.mjs";

test("hai bộ màu cùng số lượng và bộ tối không phải bản lật của bộ sáng", () => {
  assert.equal(CATEGORICAL_LIGHT.length, CATEGORICAL_DARK.length);
  // Bộ tối được chọn riêng: lật bộ sáng thì hai màu tụt xuống dưới ngưỡng
  // tương phản 3:1 trên nền tối. Không có khẳng định này thì lần sau ai đó
  // "đơn giản hoá" bằng cách dùng một bộ cho cả hai chế độ.
  for (let i = 0; i < CATEGORICAL_LIGHT.length; i += 1) {
    assert.notEqual(CATEGORICAL_LIGHT[i], CATEGORICAL_DARK[i]);
  }
});

test("màu theo chỉ số cố định, không lặp lại khi vượt quá", () => {
  assert.equal(categoricalColor(0), CATEGORICAL_LIGHT[0]);
  assert.equal(categoricalColor(0, true), CATEGORICAL_DARK[0]);
  // KHÔNG chia lấy dư: lặp màu làm hai series khác nhau cùng màu, tức mã hoá
  // danh tính bằng một thứ không còn phân biệt được danh tính.
  assert.equal(categoricalColor(MAX_SERIES), null);
  assert.equal(categoricalColor(-1), null);
  assert.equal(categoricalColor(1.5), null);
});

test("dưới ngưỡng thì giữ nguyên, không chèn Khác vô cớ", () => {
  const entries = [
    { key: "DB_SCHEMA", count: 3 },
    { key: "LLM_PROVIDER", count: 1 },
  ];
  assert.deepEqual(foldToMaxSeries(entries), entries);
});

test("vượt ngưỡng thì gộp phần dư vào Khác, KHÔNG cắt bỏ", () => {
  const entries = Array.from({ length: 8 }, (_, i) => ({ key: `E${i}`, count: 10 - i }));
  const folded = foldToMaxSeries(entries);

  assert.equal(folded.length, MAX_SERIES);
  assert.equal(folded[folded.length - 1].key, OTHER_LABEL);

  // Tổng phải được bảo toàn. Cắt bỏ phần dư làm tổng trên biểu đồ nhỏ hơn tổng
  // trên card, và người đọc không biết vì sao hai con số lệch nhau.
  const before = entries.reduce((s, e) => s + e.count, 0);
  const after = folded.reduce((s, e) => s + e.count, 0);
  assert.equal(after, before);
});

test("mọi mục gộp đều có màu, không mục nào bị null", () => {
  const entries = Array.from({ length: 12 }, (_, i) => ({ key: `E${i}`, count: 1 }));
  const folded = foldToMaxSeries(entries);
  folded.forEach((_, i) => {
    assert.ok(categoricalColor(i), `mục ${i} không có màu`);
  });
});

test("dữ liệu méo không làm nổ", () => {
  assert.deepEqual(foldToMaxSeries(null), []);
  assert.deepEqual(foldToMaxSeries([null, { count: 1 }]), []);
});

test("nhóm lỗi lạ giữ nguyên mã gốc, không đổi thành nhãn chung", () => {
  assert.equal(errorLabel("DB_SCHEMA"), "Lược đồ CSDL");
  // Một nhóm CHƯA KHAI mới đúng là loại cần tra; thay tên nó bằng nhãn chung
  // là làm nó thành không tra được.
  assert.equal(errorLabel("NHOM_MOI_CHUA_KHAI"), "NHOM_MOI_CHUA_KHAI");
  assert.equal(errorLabel(OTHER_LABEL), OTHER_LABEL);
});
