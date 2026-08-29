import assert from "node:assert/strict";
import { test } from "node:test";

import {
  NOT_MEASURED,
  countOrZero,
  formatCount,
  formatDuration,
  formatMs,
  formatPct,
  formatUsd,
  isMeasured,
} from "./metricFormat.mjs";

// --- điều kiện chính: trường vắng mặt đọc y như chưa đo được ------------------

test("truong vang mat cho ra dung ket qua nhu null", () => {
  // Đây là cả lý do file này tồn tại. Backend deploy tách rời frontend, nên bản
  // web luôn có lúc đọc một trường API chưa gửi.
  for (const format of [formatMs, formatUsd, formatPct, formatCount]) {
    assert.equal(format(undefined), format(null), `${format.name} doi xu khac nhau`);
    assert.equal(format(undefined), NOT_MEASURED);
  }
});

test("khong bao gio hien NaN — day la loi da do duoc tren man admin", () => {
  // Trước khi có file này, đúng biểu thức của ô TTFT cho ra "NaNms" khi backend
  // cũ không gửi `ttft_p95_ms`.
  const objectThieuTruong = {};
  assert.equal(formatMs(objectThieuTruong.ttft_p95_ms), NOT_MEASURED);
  for (const value of [NaN, Infinity, -Infinity]) {
    assert.equal(formatMs(value), NOT_MEASURED, `${value} phai doc la chua do duoc`);
  }
});

test("chuoi tu API khong duoc hien ra nhu mot con so", () => {
  // Một trường trả về chuỗi là lỗi phía backend. Hiện nó ra như số thì lỗi đó
  // trông giống một số đo thật.
  assert.equal(formatMs("1234"), NOT_MEASURED);
  assert.equal(formatUsd("1.5"), NOT_MEASURED);
  assert.equal(isMeasured("7"), false);
});

// --- 0 là một con số thật, không phải "chưa biết" ----------------------------

test("0 van hien ra la 0, khong bien thanh dau gach", () => {
  // Nhầm hướng này cũng sai: `0ms` là một số đo thật và che nó đi thì mất dữ
  // liệu. Chỉ `null`/`undefined` mới là chưa biết.
  assert.equal(formatMs(0), "0ms");
  assert.equal(formatUsd(0), "$0.0000");
  assert.equal(formatPct(0), "0%");
  assert.equal(formatCount(0), "0");
  assert.equal(isMeasured(0), true);
});

// --- định dạng ---------------------------------------------------------------

test("doi sang giay tu moc 1000ms", () => {
  assert.equal(formatMs(999), "999ms");
  assert.equal(formatMs(1000), "1.00s");
  assert.equal(formatMs(4635.545), "4.64s");
});

test("chi don vi ms moi duoc doi sang giay", () => {
  // `formatDuration(x, "ms")` phải giống hệt `formatMs(x)`.
  assert.equal(formatDuration(4635.545, "ms"), formatMs(4635.545));
  // Còn một đơn vị khác thì đổi sang giây là vô nghĩa.
  assert.equal(formatDuration(4635.545, " lượt"), "4636 lượt");
  assert.equal(formatDuration(null, " lượt"), NOT_MEASURED);
});

test("so chu so cua tien la tham so", () => {
  assert.equal(formatUsd(1.23456789), "$1.2346");
  assert.equal(formatUsd(0.0000123, 5), "$0.00001");
});

// --- đếm dùng để so ngưỡng --------------------------------------------------

test("countOrZero quy truong vang mat ve 0 thay vi de NaN lan vao phep tinh", () => {
  assert.equal(countOrZero(undefined), 0);
  assert.equal(countOrZero(null), 0);
  assert.equal(countOrZero(NaN), 0);
  assert.equal(countOrZero(3), 3);
  // Điểm quan trọng: cộng dồn không được ra NaN.
  assert.equal(countOrZero(undefined) + countOrZero(2), 2);
});
