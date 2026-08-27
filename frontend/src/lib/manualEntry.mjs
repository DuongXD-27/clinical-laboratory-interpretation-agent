import { GENERATED_MANUAL_ANALYTES } from "../generated/analyteCatalog.mjs";

export const MANUAL_GROUP_LABELS = Object.freeze({
  hematology: "Huyết học", electrolytes: "Điện giải", glucose: "Đường huyết",
  renal: "Chức năng thận", liver: "Chức năng gan", lipids: "Mỡ máu",
});
export const MANUAL_SUPPORT_STATUS_LABELS = Object.freeze({
  APPROVED: "Được hỗ trợ", HOLD: "Tạm giữ", UNSUPPORTED: "Chưa hỗ trợ",
});

const MANUAL_LABELS = Object.freeze({
  WBC: "Bạch cầu (WBC)", RBC: "Hồng cầu (RBC)", HGB: "Hemoglobin (HGB)",
  HCT: "Hematocrit (HCT)", PLT: "Tiểu cầu (PLT)",
  "Neutrophils %": "Bạch cầu trung tính % (NEUT%)",
  "Neutrophils abs": "Bạch cầu trung tính tuyệt đối (NEUT#)",
  "Lymphocytes %": "Lympho bào % (LYM%)", "Lymphocytes abs": "Lympho bào tuyệt đối (LYM#)",
  "Monocytes %": "Bạch cầu mono % (MONO%)", "Monocytes abs": "Bạch cầu mono tuyệt đối (MONO#)",
  "Eosinophils %": "Bạch cầu ái toan % (EOS%)", "Eosinophils abs": "Bạch cầu ái toan tuyệt đối (EOS#)",
  Sodium: "Natri (Sodium)", Potassium: "Kali (Potassium)", Chloride: "Clor (Chloride)",
  "Fasting plasma glucose": "Đường huyết lúc đói", "Uric acid": "Acid Uric (Uric acid)",
  AST: "AST (SGOT)", ALT: "ALT (SGPT)", "Total bilirubin": "Bilirubin toàn phần",
  "Total protein": "Protein toàn phần", "Total cholesterol": "Cholesterol toàn phần",
});

/** @typedef {{name:string,label:string,unit:string,category:string,analyteId:string,canonicalGroup:string,runtimeStatus:"APPROVED"|"HOLD"|"UNSUPPORTED"}} ManualAnalyte */
/** @type {readonly ManualAnalyte[]} */
export const MANUAL_ANALYTES = Object.freeze(GENERATED_MANUAL_ANALYTES.map((analyte) => Object.freeze({
  ...analyte,
  label: MANUAL_LABELS[analyte.name] || analyte.name,
  category: MANUAL_GROUP_LABELS[analyte.canonicalGroup] || analyte.canonicalGroup,
})));

export function manualAnalyteAttentionMessage(analyte) {
  if (!analyte || analyte.runtimeStatus === "APPROVED") return "";
  if (analyte.runtimeStatus === "HOLD") return "Chỉ số này đang ở trạng thái tạm giữ và chưa được hệ thống phân loại tự động.";
  return "Chỉ số này chưa được hệ thống phân loại tự động.";
}

export function buildManualIndicators(values) {
  const indicators = [];
  for (const analyte of MANUAL_ANALYTES) {
    const raw = values[analyte.name];
    if (raw === undefined || String(raw).trim() === "") continue;
    const value = typeof raw === "number" ? raw : Number(raw);
    if (!Number.isFinite(value) || value < 0) throw new Error(`Giá trị ${analyte.label} phải là số không âm hợp lệ.`);
    indicators.push({ name: analyte.name, value, unit: analyte.unit });
  }
  if (indicators.length === 0) throw new Error("Hãy nhập ít nhất một chỉ số xét nghiệm.");
  return indicators;
}
