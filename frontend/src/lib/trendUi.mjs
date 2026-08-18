export const TREND_INSUFFICIENT_MESSAGE =
  "Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên trong phạm vi đã chọn.";

export function defaultTrendAnalyte(analytes) {
  return analytes.find((item) => item?.trend_available)?.analyte_canonical ?? "";
}

export function canRenderTrendChart(trend) {
  return Boolean(
    trend?.trend_available
    && Array.isArray(trend.points)
    && trend.points.length >= 3,
  );
}

export function trendReasonMessage(reason) {
  if (reason === "DATA_QUALITY_ERROR") {
    return "Dữ liệu chuẩn hóa của chỉ số này chưa nhất quán nên chưa thể vẽ biểu đồ an toàn.";
  }
  if (reason === "ANALYTE_NOT_FOUND") {
    return "Chỉ số này chưa có trong lịch sử xét nghiệm của bạn.";
  }
  if (reason === "GAP_TOO_LARGE") {
    return "Các lần xét nghiệm gần nhất cách nhau quá xa theo cấu hình của chỉ số này nên chưa thể tạo xu hướng liên tục.";
  }
  return TREND_INSUFFICIENT_MESSAGE;
}

export function formatTrendDate(value) {
  const date = new Date(typeof value === "number" ? value : `${value}T00:00:00`);
  if (Number.isNaN(date.getTime())) return String(value);
  return new Intl.DateTimeFormat("vi-VN", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  }).format(date);
}

export function assessmentText(value) {
  if (value === "critical_high") return "Rất cao";
  if (value === "critical_low") return "Rất thấp";
  if (value === "high") return "Cao";
  if (value === "low") return "Thấp";
  if (value === "normal") return "Bình thường";
  return value || "Không rõ";
}

// ADR-010 CRIT-TREND-06: thứ tự nhóm chức năng cố định trên UI — "Khác" luôn ở
// cuối, khớp với business description ("Huyết học / Sinh hóa thận gan / Mỡ máu
// đường huyết"). Không phải thứ tự bảng chữ cái vì đó là thói quen đọc chuyên môn.
export const SECTION_LABEL_ORDER = [
  "Huyết học",
  "Sinh hóa thận - gan",
  "Mỡ máu & đường huyết",
  "Khác",
];

/**
 * Gom một danh sách chỉ số (chỉ số xu hướng hoặc indicator một phiếu) theo
 * `section_label`, giữ nguyên thứ tự bên trong mỗi nhóm và trả nhóm theo đúng thứ
 * tự SECTION_LABEL_ORDER. Chỉ số thiếu section_label rơi vào nhóm "Khác".
 *
 * @template {{ section_label?: string | null }} T
 * @param {T[] | null | undefined} items
 * @returns {{ label: string, items: T[] }[]}
 */
export function groupBySection(items) {
  const groups = new Map();
  for (const item of items ?? []) {
    const label = item?.section_label || "Khác";
    if (!groups.has(label)) groups.set(label, []);
    groups.get(label).push(item);
  }
  const ordered = SECTION_LABEL_ORDER.filter((label) => groups.has(label)).map((label) => ({
    label,
    items: groups.get(label),
  }));
  const extras = [...groups.keys()]
    .filter((label) => !SECTION_LABEL_ORDER.includes(label))
    .map((label) => ({ label, items: groups.get(label) }));
  return [...ordered, ...extras];
}
