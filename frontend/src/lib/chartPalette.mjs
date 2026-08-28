/** Bảng màu cho biểu đồ vận hành — đã chạy validator, không phải chọn bằng mắt.
 *
 * ## Bằng chứng, không phải ý kiến
 *
 * Cả hai bộ dưới đây đều đi qua `validate_palette.js` và **pass sạch, không
 * WARN** — kiểm dải sáng, sàn chroma, tách màu cho người mù màu, sàn thị lực
 * bình thường, và độ tương phản với nền:
 *
 *     sáng: #0B6E99,#C2410C,#6D28D9,#BE185D,#A16207   -> ALL CHECKS PASS
 *     tối : #3489BC,#D96A3E,#8B6BE0,#DB5F96,#B98A34   -> ALL CHECKS PASS
 *
 * Bộ tối là bộ **được chọn riêng**, không phải lật tự động từ bộ sáng: thử lật
 * thì `#6D28D9` và `#BE185D` tụt xuống contrast 2.45 và 2.88 trên nền tối, dưới
 * ngưỡng 3:1.
 *
 * ## Vì sao chỉ 5 màu
 *
 * Sáu hue tách nhau sạch là bất khả với ngưỡng này — mọi bộ 6 tôi thử đều vướng
 * cặp amber↔green hoặc pink↔green dưới ΔE 8 khi mô phỏng mù màu. Nên nhóm lỗi
 * thứ 5 trở đi gộp vào "Khác" thay vì sinh thêm hue. Hệ này thực tế có ~4 nhóm.
 *
 * ## Vì sao P50/P95/P99 KHÔNG dùng dải một hue
 *
 * Đó là lựa chọn đầu tiên của tôi, vì phân vị là ba mức của cùng một đại lượng
 * nên một dải sáng→đậm mã hoá đúng thứ tự đó. Nhưng đo lại thì nó thất bại về
 * mặt đọc được: bậc nhạt nhất có contrast 2.59 trên nền trắng (dưới 3:1), và
 * ΔE giữa hai bậc đậm chỉ 14.3 — dưới sàn 15, tức **ngay cả người thị lực bình
 * thường cũng khó phân biệt**. Ba đường chồng nhau mà khó phân biệt là lỗi thật,
 * nặng hơn cái lợi ngữ nghĩa.
 *
 * Nên ba phân vị dùng ba hue phân loại đã pass, và thứ tự được nhấn bằng ĐỘ DÀY:
 * P95 vẽ 2px vì nó là con số SLO gắn vào, P50 và P99 vẽ 1.5px.
 */

/** Thứ tự cố định. Màu đi theo THỰC THỂ, không theo hạng.
 *
 * Một filter làm giảm số series không được phép sơn lại những series còn lại —
 * nếu không thì hôm nay `DB_SCHEMA` màu xanh, mai lọc bớt một nhóm là nó thành
 * màu cam, và người đọc mất luôn khả năng nhận ra nó qua các lần xem.
 */
export const CATEGORICAL_LIGHT = ["#0B6E99", "#C2410C", "#6D28D9", "#BE185D", "#A16207"];
export const CATEGORICAL_DARK = ["#3489BC", "#D96A3E", "#8B6BE0", "#DB5F96", "#B98A34"];

/** Số series tối đa trước khi gộp vào "Khác". Bằng số màu, không hơn. */
export const MAX_SERIES = CATEGORICAL_LIGHT.length;

export const OTHER_LABEL = "Khác";

/** Màu theo chỉ số trong thứ tự cố định. Không bao giờ chia lấy dư để lặp lại.
 *
 * Lặp màu làm hai series khác nhau cùng màu trên một biểu đồ, tức là mã hoá
 * danh tính bằng một thứ không còn phân biệt được danh tính.
 */
export function categoricalColor(index, dark = false) {
  const palette = dark ? CATEGORICAL_DARK : CATEGORICAL_LIGHT;
  if (!Number.isInteger(index) || index < 0 || index >= palette.length) return null;
  return palette[index];
}

/** Gộp danh sách nhóm thành tối đa `MAX_SERIES` mục, phần dư thành "Khác".
 *
 * Nhận `[{key, count}]` đã sắp giảm dần. Trả về `[{key, count}]` với mục cuối
 * là "Khác" khi có phần dư — chứ không cắt bỏ phần dư, vì cắt bỏ làm tổng trên
 * biểu đồ nhỏ hơn tổng trên card và người đọc không biết vì sao.
 */
export function foldToMaxSeries(entries) {
  const list = Array.isArray(entries) ? entries.filter((e) => e && e.key) : [];
  if (list.length <= MAX_SERIES) return list.map((e) => ({ ...e }));

  const kept = list.slice(0, MAX_SERIES - 1).map((e) => ({ ...e }));
  const rest = list.slice(MAX_SERIES - 1);
  kept.push({
    key: OTHER_LABEL,
    count: rest.reduce((sum, e) => sum + (Number(e.count) || 0), 0),
  });
  return kept;
}

/** Nhãn tiếng Việt cho nhóm lỗi. Nhóm lạ giữ nguyên mã gốc.
 *
 * Giữ nguyên chứ không đổi thành "Khác": một nhóm CHƯA KHAI mới đúng là loại
 * cần tra, và thay tên nó bằng một nhãn chung là làm nó thành không tra được.
 */
const ERROR_LABELS = {
  DB_CONNECTION: "Kết nối CSDL",
  DB_SCHEMA: "Lược đồ CSDL",
  DB_INTEGRITY: "Ràng buộc CSDL",
  DB_TIMEOUT: "CSDL quá hạn",
  LLM_PROVIDER: "Nhà cung cấp LLM",
  LLM_RATE_LIMIT: "LLM chặn tần suất",
  LLM_TIMEOUT: "LLM quá hạn",
  OCR_ERROR: "OCR",
  VALIDATION: "Dữ liệu vào không hợp lệ",
  INTERNAL_EXCEPTION: "Chưa phân loại",
};

export function errorLabel(key) {
  if (key === OTHER_LABEL) return OTHER_LABEL;
  return ERROR_LABELS[key] || key;
}
