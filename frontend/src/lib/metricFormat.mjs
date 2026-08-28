/** Định dạng số liệu vận hành: "chưa đo được" phải khác "bằng không".
 *
 * ## Vì sao `undefined` phải cho ra đúng kết quả như `null`
 *
 * Backend và frontend deploy tách rời — backend đi theo lần Dương sync repo
 * deploy, frontend đi theo một lệnh `vercel --prod` chạy tay — nên luôn có một
 * khoảng thời gian bản web đọc một trường mà API chưa gửi. Trường vắng mặt về
 * tới JavaScript là `undefined`, không phải `null`.
 *
 * Kiểm tra bằng `=== null` thì `undefined` lọt qua. Đo trực tiếp trên đúng biểu
 * thức mà màn `/admin` đang dùng cho TTFT:
 *
 *     ttft_p95_ms vắng mặt  ->  "NaNms"
 *     ttft_p95_ms là null   ->  "—"
 *
 * `NaNms` là một con số bịa, trên đúng cái màn hình tồn tại để không bịa số. Nó
 * cũng tệ hơn `0ms`: `0ms` còn đọc ra là một khẳng định sai, còn `NaNms` làm
 * người xem nghĩ màn hình hỏng và bỏ luôn cả những số bên cạnh đang đúng.
 *
 * ## Vì sao chặn cả số không hữu hạn
 *
 * `NaN` và `Infinity` cũng phải đọc là chưa đo được. Một phép chia cho 0 ở phía
 * backend, hay một trường trả về chuỗi, không được hiện ra thành một con số.
 *
 * ## Vì sao nằm ở `lib/*.mjs`
 *
 * Để `node --test` chạy được mà không cần dựng React. Đây là logic quyết định
 * "biết" hay "không biết" của cả màn quan sát, nên nó cần test riêng chứ không
 * nên nằm rải trong JSX dưới dạng toán tử ba ngôi.
 */

/** Dấu gạch, không phải `0`. Trên màn vận hành hai thứ đó là hai kết luận trái ngược. */
export const NOT_MEASURED = "—";

/** Có một con số thật hay không. `null`, `undefined`, `NaN`, `Infinity`, chuỗi đều là không. */
export function isMeasured(value) {
  return typeof value === "number" && Number.isFinite(value);
}

/** Thời lượng: đổi sang giây từ mốc 1000ms để không hiện "4635ms". */
export function formatMs(value) {
  if (!isMeasured(value)) return NOT_MEASURED;
  return value >= 1000 ? `${(value / 1000).toFixed(2)}s` : `${Math.round(value)}ms`;
}

/** Thời lượng kèm đơn vị tự chọn. Chỉ đơn vị `ms` mới được đổi sang giây. */
export function formatDuration(value, suffix = "ms") {
  if (!isMeasured(value)) return NOT_MEASURED;
  if (suffix === "ms") return formatMs(value);
  return `${Math.round(value)}${suffix}`;
}

/** Tiền: không bao giờ hiện `$0.00` cho một giá trị chưa biết. */
export function formatUsd(value, digits = 4) {
  if (!isMeasured(value)) return NOT_MEASURED;
  return `$${value.toFixed(digits)}`;
}

/** Phần trăm. */
export function formatPct(value) {
  if (!isMeasured(value)) return NOT_MEASURED;
  return `${value}%`;
}

/** Số lượng nguyên. `0` là một con số thật ở đây nên vẫn hiện `0`, không hiện gạch. */
export function formatCount(value) {
  if (!isMeasured(value)) return NOT_MEASURED;
  return String(Math.round(value));
}

/** Đếm dùng để so sánh ngưỡng: trường vắng mặt phải là 0, không phải `NaN`.
 *
 * `undefined > 0` là `false` nên nó tình cờ đúng, nhưng `undefined + 1` thì ra
 * `NaN` và một cảnh báo dựa trên phép cộng đó sẽ im lặng biến mất. Quy về 0 ở
 * một chỗ thì không còn phụ thuộc vào sự tình cờ nữa.
 */
export function countOrZero(value) {
  return isMeasured(value) ? value : 0;
}
