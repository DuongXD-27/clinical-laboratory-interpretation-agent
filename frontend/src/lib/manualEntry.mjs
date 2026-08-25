export const MANUAL_GROUP_LABELS = Object.freeze({
  hematology: "Huyết học",
  electrolytes: "Điện giải",
  glucose: "Đường huyết",
  renal: "Chức năng thận",
  liver: "Chức năng gan",
  lipids: "Mỡ máu",
});

export const MANUAL_SUPPORT_STATUS_LABELS = Object.freeze({
  APPROVED: "Được hỗ trợ",
  HOLD: "Tạm giữ",
  UNSUPPORTED: "Chưa hỗ trợ",
});

/**
 * @typedef {"APPROVED" | "HOLD" | "UNSUPPORTED"} ManualRuntimeStatus
 * @typedef {{
 *   name: string;
 *   label: string;
 *   unit: string;
 *   category: string;
 *   analyteId: string;
 *   canonicalGroup: string;
 *   runtimeStatus: ManualRuntimeStatus;
 * }} ManualAnalyte
 */

export function manualAnalyteAttentionMessage(analyte) {
  if (!analyte || analyte.runtimeStatus === "APPROVED") return "";
  if (analyte.runtimeStatus === "HOLD") {
    return "Chỉ số này đang ở trạng thái tạm giữ và chưa được hệ thống phân loại tự động.";
  }
  return "Chỉ số này chưa được hệ thống phân loại tự động.";
}

/** @type {readonly ManualAnalyte[]} */
export const MANUAL_ANALYTES = Object.freeze([
  // Huyết học
  { name: "WBC", label: "Bạch cầu (WBC)", unit: "10^9/L", category: "Huyết học", analyteId: "wbc", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "RBC", label: "Hồng cầu (RBC)", unit: "10^12/L", category: "Huyết học", analyteId: "rbc", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "HGB", label: "Hemoglobin (HGB)", unit: "g/L", category: "Huyết học", analyteId: "hgb", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "HCT", label: "Hematocrit (HCT)", unit: "L/L", category: "Huyết học", analyteId: "hct", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "MCV", label: "MCV", unit: "fL", category: "Huyết học", analyteId: "mcv", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "MCH", label: "MCH", unit: "pg", category: "Huyết học", analyteId: "mch", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "MCHC", label: "MCHC", unit: "g/L", category: "Huyết học", analyteId: "mchc", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "RDW-CV", label: "RDW-CV", unit: "%", category: "Huyết học", analyteId: "rdw_cv", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "PLT", label: "Tiểu cầu (PLT)", unit: "10^9/L", category: "Huyết học", analyteId: "plt", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Neutrophils %", label: "Bạch cầu trung tính % (NEUT%)", unit: "%", category: "Huyết học", analyteId: "neutrophils_%", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Neutrophils abs", label: "Bạch cầu trung tính tuyệt đối (NEUT#)", unit: "10^9/L", category: "Huyết học", analyteId: "neutrophils_abs", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Lymphocytes %", label: "Lympho bào % (LYM%)", unit: "%", category: "Huyết học", analyteId: "lymphocytes_%", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Lymphocytes abs", label: "Lympho bào tuyệt đối (LYM#)", unit: "10^9/L", category: "Huyết học", analyteId: "lymphocytes_abs", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Monocytes %", label: "Bạch cầu mono % (MONO%)", unit: "%", category: "Huyết học", analyteId: "monocytes_%", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Monocytes abs", label: "Bạch cầu mono tuyệt đối (MONO#)", unit: "10^9/L", category: "Huyết học", analyteId: "monocytes_abs", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Eosinophils %", label: "Bạch cầu ái toan % (EOS%)", unit: "%", category: "Huyết học", analyteId: "eosinophils_%", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  { name: "Eosinophils abs", label: "Bạch cầu ái toan tuyệt đối (EOS#)", unit: "10^9/L", category: "Huyết học", analyteId: "eosinophils_abs", canonicalGroup: "hematology", runtimeStatus: "APPROVED" },
  
  // Điện giải
  { name: "Sodium", label: "Natri (Sodium)", unit: "mmol/L", category: "Điện giải", analyteId: "sodium", canonicalGroup: "electrolytes", runtimeStatus: "APPROVED" },
  { name: "Potassium", label: "Kali (Potassium)", unit: "mmol/L", category: "Điện giải", analyteId: "potassium", canonicalGroup: "electrolytes", runtimeStatus: "APPROVED" },
  { name: "Chloride", label: "Clor (Chloride)", unit: "mmol/L", category: "Điện giải", analyteId: "chloride", canonicalGroup: "electrolytes", runtimeStatus: "APPROVED" },
  
  // Đường huyết
  { name: "Fasting plasma glucose", label: "Đường huyết lúc đói", unit: "mmol/L", category: "Đường huyết", analyteId: "fasting_plasma_glucose", canonicalGroup: "glucose", runtimeStatus: "APPROVED" },
  { name: "HbA1c", label: "HbA1c", unit: "%", category: "Đường huyết", analyteId: "hba1c", canonicalGroup: "glucose", runtimeStatus: "APPROVED" },
  
  // Chức năng thận
  { name: "Creatinine", label: "Creatinine", unit: "umol/L", category: "Chức năng thận", analyteId: "creatinine", canonicalGroup: "renal", runtimeStatus: "APPROVED" },
  { name: "Urea", label: "Urea", unit: "mmol/L", category: "Chức năng thận", analyteId: "urea", canonicalGroup: "renal", runtimeStatus: "APPROVED" },
  { name: "Uric acid", label: "Acid Uric (Uric acid)", unit: "umol/L", category: "Chức năng thận", analyteId: "uric_acid", canonicalGroup: "renal", runtimeStatus: "APPROVED" },
  
  // Chức năng gan
  { name: "AST", label: "AST (SGOT)", unit: "U/L", category: "Chức năng gan", analyteId: "ast", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  { name: "ALT", label: "ALT (SGPT)", unit: "U/L", category: "Chức năng gan", analyteId: "alt", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  { name: "GGT", label: "GGT", unit: "U/L", category: "Chức năng gan", analyteId: "ggt", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  { name: "Total bilirubin", label: "Bilirubin toàn phần", unit: "umol/L", category: "Chức năng gan", analyteId: "total_bilirubin", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  { name: "Total protein", label: "Protein toàn phần", unit: "g/L", category: "Chức năng gan", analyteId: "total_protein", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  { name: "Albumin", label: "Albumin", unit: "g/L", category: "Chức năng gan", analyteId: "albumin", canonicalGroup: "liver", runtimeStatus: "APPROVED" },
  
  // Mỡ máu
  { name: "Total cholesterol", label: "Cholesterol toàn phần", unit: "mmol/L", category: "Mỡ máu", analyteId: "total_cholesterol", canonicalGroup: "lipids", runtimeStatus: "APPROVED" },
  { name: "Triglyceride", label: "Triglyceride", unit: "mmol/L", category: "Mỡ máu", analyteId: "triglyceride", canonicalGroup: "lipids", runtimeStatus: "APPROVED" },
  { name: "LDL-C", label: "LDL-C", unit: "mmol/L", category: "Mỡ máu", analyteId: "ldl_c", canonicalGroup: "lipids", runtimeStatus: "APPROVED" },
  { name: "HDL-C", label: "HDL-C", unit: "mmol/L", category: "Mỡ máu", analyteId: "hdl_c", canonicalGroup: "lipids", runtimeStatus: "APPROVED" },
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
