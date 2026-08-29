export function formatDate(value) {
  if (!value) return "Chưa có";
  const datePart = String(value).slice(0, 10);
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(datePart);
  return match ? `${match[3]}/${match[2]}/${match[1]}` : String(value);
}

export function formatMoment(value) {
  if (!value) return "";
  const text = String(value).trim();
  const parseableValue = /^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(text)
    && !/(?:Z|[+-]\d{2}:?\d{2})$/.test(text)
    ? `${text.replace(" ", "T")}Z`
    : text;
  const parsed = new Date(parseableValue);
  return Number.isNaN(parsed.getTime())
    ? String(value)
    : parsed.toLocaleString("vi-VN", {
        timeZone: "Asia/Ho_Chi_Minh",
        day: "2-digit",
        month: "2-digit",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
}

export function indicatorStatusText(status, critical_status) {
  if (critical_status) {
    const critNormalized = String(critical_status).toUpperCase();
    if (critNormalized === "CRITICAL_HIGH") return "Nguy kịch – cao";
    if (critNormalized === "CRITICAL_LOW") return "Nguy kịch – thấp";
    if (critNormalized === "CRITICAL") return "Nguy kịch";
  }
  const labels = {
    NORMAL: "Bình thường",
    LOW: "Thấp",
    HIGH: "Cao",
    CRITICAL: "Nguy kịch",
    CRITICAL_HIGH: "Nguy kịch – cao",
    CRITICAL_LOW: "Nguy kịch – thấp",
    ABNORMAL: "Bất thường",
    UNKNOWN: "Chưa thể đánh giá",
    HOLD: "Chưa thể đánh giá",
    VERY_HIGH: "Rất cao",
    VERY_LOW: "Rất thấp",
    BORDERLINE_HIGH: "Cao mức biên",
    PREDIABETES: "Tiền đái tháo đường",
    PROVISIONAL_DIABETES: "Nghi ngờ đái tháo đường",
    OPTIMAL: "Tối ưu",
    DESIRABLE: "Mong muốn",
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
  if (normalized === "UNKNOWN" || normalized === "HOLD") return "unknown";
  if (normalized === "CRITICAL" || normalized === "CRITICAL_HIGH" || normalized === "CRITICAL_LOW") return "critical";
  if (normalized === "NORMAL" || normalized === "OPTIMAL" || normalized === "DESIRABLE") return "normal";
  return "abnormal";
}

/**
 * Display-only ordering for the analysis result list: critical findings first,
 * then abnormal, then unknown, then normal. Order within each group is
 * preserved. Purely presentational — never mutates stored data and never
 * reclassifies a backend-provided status.
 */
const SEVERITY_RANK = { critical: 0, abnormal: 1, unknown: 2, normal: 3 };

export function sortIndicatorsBySeverity(indicators) {
  if (!Array.isArray(indicators)) return [];
  return indicators
    .map((indicator, index) => ({ indicator, index }))
    .sort((a, b) => {
      const rankA = SEVERITY_RANK[reportTone(a.indicator.status)] ?? 4;
      const rankB = SEVERITY_RANK[reportTone(b.indicator.status)] ?? 4;
      return rankA - rankB || a.index - b.index;
    })
    .map((entry) => entry.indicator);
}

export function sourceHostname(source) {
  try {
    return new URL(source).hostname.replace(/^www\./, "");
  } catch {
    return source;
  }
}

export function renderReferenceRange(indicator) {
  if (indicator.status === "unknown" || indicator.status === "HOLD") {
    return null;
  }
  
  if (indicator.rule_type) {
    if (indicator.rule_type === "CDL" || indicator.rule_type === "BAND") {
      return null;
    }
    if (indicator.rule_type === "ONE_SIDED_LIMIT") {
      if (indicator.upper_operator && indicator.reference_high !== null && indicator.reference_high !== undefined) {
        return `Ngưỡng: ${indicator.upper_operator} ${indicator.reference_high} ${indicator.unit}`;
      }
      if (indicator.reference_low !== null && indicator.reference_low !== undefined) {
        const op = indicator.upper_operator === "<" || indicator.upper_operator === "<=" ? ">" : (indicator.upper_operator || ">");
        return `Ngưỡng: ${op} ${indicator.reference_low} ${indicator.unit}`;
      }
      return null;
    }
    if (indicator.reference_low !== null || indicator.reference_high !== null) {
      return `Khoảng tham chiếu hệ thống: ${indicator.reference_low ?? "-"} – ${indicator.reference_high ?? "-"}`;
    }
    return null;
  }

  // Legacy case: rule_type is null
  if (indicator.reference_low !== null && indicator.reference_high !== null) {
    return `Khoảng tham chiếu hệ thống: ${indicator.reference_low} – ${indicator.reference_high}`;
  }

  return "Chi tiết quy tắc tham chiếu không được lưu ở phiên bản này.";
}

export function formatClinicalAssessment(value) {
  if (!value) return "Chưa rõ";
  const normalized = String(value).trim().toUpperCase();
  const map = {
    NORMAL: "Bình thường",
    HIGH: "Cao",
    LOW: "Thấp",
    CRITICAL: "Giá trị khẩn cấp",
    CRITICAL_HIGH: "Nguy kịch – cao",
    CRITICAL_LOW: "Nguy kịch – thấp",
    ABNORMAL: "Bất thường",
    UNKNOWN: "Chưa thể đánh giá",
    HOLD: "Chưa thể đánh giá",
    PENDING: "Đang chờ",
    REVIEWED: "Đã đánh giá",
    APPROVED: "Đã duyệt",
    REJECTED: "Đã từ chối",
    CANCELLED: "Đã huỷ",
    OPTIMAL: "Tối ưu",
    DESIRABLE: "Mong muốn",
  };
  return map[normalized] ?? indicatorStatusText(normalized);
}

export function formatPatientDemographics(gender, age) {
  const g = gender === "male" ? "Nam" : gender === "female" ? "Nữ" : gender === "other" ? "Khác" : "Chưa có";
  if (age !== null && age !== undefined && age !== "" && age !== "-" && Number.isFinite(Number(age))) {
    return `${g} · ${age} tuổi`;
  }
  return g;
}
