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
