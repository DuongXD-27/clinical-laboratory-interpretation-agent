export const MANUAL_ANALYTES = Object.freeze([
  // Huyết học
  { name: "WBC", label: "Bạch cầu (WBC)", unit: "10^9/L", category: "Huyết học" },
  { name: "RBC", label: "Hồng cầu (RBC)", unit: "10^12/L", category: "Huyết học" },
  { name: "HGB", label: "Hemoglobin (HGB)", unit: "g/L", category: "Huyết học" },
  { name: "HCT", label: "Hematocrit (HCT)", unit: "%", category: "Huyết học" },
  { name: "MCV", label: "MCV", unit: "fL", category: "Huyết học" },
  { name: "MCH", label: "MCH", unit: "pg", category: "Huyết học" },
  { name: "MCHC", label: "MCHC", unit: "g/L", category: "Huyết học" },
  { name: "RDW-CV", label: "RDW-CV", unit: "%", category: "Huyết học" },
  { name: "PLT", label: "Tiểu cầu (PLT)", unit: "10^9/L", category: "Huyết học" },
  { name: "Neutrophils %", label: "Bạch cầu trung tính % (NEUT%)", unit: "%", category: "Huyết học" },
  { name: "Neutrophils abs", label: "Bạch cầu trung tính tuyệt đối (NEUT#)", unit: "10^9/L", category: "Huyết học" },
  { name: "Lymphocytes %", label: "Lympho bào % (LYM%)", unit: "%", category: "Huyết học" },
  { name: "Lymphocytes abs", label: "Lympho bào tuyệt đối (LYM#)", unit: "10^9/L", category: "Huyết học" },
  { name: "Monocytes %", label: "Bạch cầu mono % (MONO%)", unit: "%", category: "Huyết học" },
  { name: "Monocytes abs", label: "Bạch cầu mono tuyệt đối (MONO#)", unit: "10^9/L", category: "Huyết học" },
  { name: "Eosinophils %", label: "Bạch cầu ái toan % (EOS%)", unit: "%", category: "Huyết học" },
  { name: "Eosinophils abs", label: "Bạch cầu ái toan tuyệt đối (EOS#)", unit: "10^9/L", category: "Huyết học" },
  
  // Điện giải
  { name: "Sodium", label: "Natri (Sodium)", unit: "mmol/L", category: "Điện giải" },
  { name: "Potassium", label: "Kali (Potassium)", unit: "mmol/L", category: "Điện giải" },
  { name: "Chloride", label: "Clor (Chloride)", unit: "mmol/L", category: "Điện giải" },
  
  // Đường huyết
  { name: "Fasting plasma glucose", label: "Đường huyết lúc đói", unit: "mmol/L", category: "Đường huyết" },
  { name: "HbA1c", label: "HbA1c", unit: "%", category: "Đường huyết" },
  
  // Chức năng thận
  { name: "Creatinine", label: "Creatinine", unit: "umol/L", category: "Chức năng thận" },
  { name: "Urea", label: "Urea", unit: "mmol/L", category: "Chức năng thận" },
  { name: "Uric acid", label: "Acid Uric (Uric acid)", unit: "umol/L", category: "Chức năng thận" },
  
  // Chức năng gan
  { name: "AST", label: "AST (SGOT)", unit: "U/L", category: "Chức năng gan" },
  { name: "ALT", label: "ALT (SGPT)", unit: "U/L", category: "Chức năng gan" },
  { name: "GGT", label: "GGT", unit: "U/L", category: "Chức năng gan" },
  { name: "Total bilirubin", label: "Bilirubin toàn phần", unit: "umol/L", category: "Chức năng gan" },
  { name: "Total protein", label: "Protein toàn phần", unit: "g/L", category: "Chức năng gan" },
  { name: "Albumin", label: "Albumin", unit: "g/L", category: "Chức năng gan" },
  
  // Mỡ máu
  { name: "Total cholesterol", label: "Cholesterol toàn phần", unit: "mmol/L", category: "Mỡ máu" },
  { name: "Triglyceride", label: "Triglyceride", unit: "mmol/L", category: "Mỡ máu" },
  { name: "LDL-C", label: "LDL-C", unit: "mmol/L", category: "Mỡ máu" },
  { name: "HDL-C", label: "HDL-C", unit: "mmol/L", category: "Mỡ máu" },
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
