export function formatDate(value) {
  if (!value) return "Chưa có";
  const datePart = String(value).slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(datePart);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

export function formatMoment(value) {
  if (!value) return "";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleString("vi-VN", {
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
}

export function indicatorStatusText(status) {
  const labels = {
    NORMAL: "Bình thường",
    LOW: "Thấp",
    HIGH: "Cao",
    CRITICAL: "Nguy kịch",
    CRITICAL_HIGH: "Nguy kịch – cao",
    CRITICAL_LOW: "Nguy kịch – thấp",
    ABNORMAL: "Bất thường",
  };
  return labels[String(status).toUpperCase()] ?? String(status);
}

export function reportStatusText(status) {
  const normalized = String(status).toUpperCase();
  if (normalized === "CRITICAL") return "Có chỉ số nguy kịch";
  if (normalized === "ABNORMAL") return "Có chỉ số bất thường";
  return indicatorStatusText(normalized);
}

export function reportTone(status) {
  const normalized = String(status).toUpperCase();
  if (normalized === "CRITICAL" || normalized === "CRITICAL_HIGH" || normalized === "CRITICAL_LOW") return "critical";
  if (normalized === "ABNORMAL" || normalized === "HIGH" || normalized === "LOW") return "abnormal";
  return "normal";
}

export function sourceHostname(source) {
  try {
    return new URL(source).hostname.replace(/^www\./, "");
  } catch {
    return source;
  }
}
