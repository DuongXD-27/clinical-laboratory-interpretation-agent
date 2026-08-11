export const MANUAL_ANALYTES = Object.freeze([
  { name: "WBC", label: "Bạch cầu (WBC)", unit: "10^9/L", category: "Huyết học" },
  { name: "RBC", label: "Hồng cầu (RBC)", unit: "10^12/L", category: "Huyết học" },
  { name: "Glucose", label: "Đường huyết lúc đói", unit: "mmol/L", category: "Đường huyết" },
  { name: "Creatinine", label: "Creatinine", unit: "µmol/L", category: "Chức năng thận" },
]);

/**
 * Convert the manual form into the API indicator list. Blank fields are
 * omitted, while invalid and negative laboratory values are rejected.
 *
 * @param {Record<string, string | number>} values
 */
export function buildManualIndicators(values) {
  const indicators = [];

  for (const analyte of MANUAL_ANALYTES) {
    const raw = values[analyte.name];
    if (raw === undefined || String(raw).trim() === "") continue;

    const value = typeof raw === "number" ? raw : Number(raw);
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`Giá trị ${analyte.label} phải là số không âm hợp lệ.`);
    }
    indicators.push({ name: analyte.name, value, unit: analyte.unit });
  }

  if (indicators.length === 0) {
    throw new Error("Hãy nhập ít nhất một chỉ số xét nghiệm.");
  }

  return indicators;
}
