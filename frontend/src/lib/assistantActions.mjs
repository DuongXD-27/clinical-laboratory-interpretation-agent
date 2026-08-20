export const ASSISTANT_ACTION_ALLOWLIST = Object.freeze([
  "OPEN_REPORT",
  "VIEW_ABNORMAL",
  "VIEW_HISTORY",
  "VIEW_TREND",
  "VIEW_DOCTOR_QUESTIONS",
  "CONFIRM_OCR",
  "RETRY",
]);

const ALLOWED_ACTIONS = new Set(ASSISTANT_ACTION_ALLOWLIST);
const PATIENT_ONLY_ACTIONS = new Set(["OPEN_REPORT", "VIEW_ABNORMAL", "VIEW_HISTORY", "VIEW_TREND"]);
const SERVER_REFERENCE_PATTERN = /^[A-Za-z0-9_.%+-]+$/;
const FORBIDDEN_FIELDS = new Set([
  "authorization",
  "href",
  "patient_id",
  "payload",
  "route",
  "token",
  "uid",
  "url",
  "user_id",
]);

function isPlainObject(value) {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value);
}

export function isServerReference(value) {
  return typeof value === "string" && SERVER_REFERENCE_PATTERN.test(value);
}

function hasForbiddenField(action) {
  return Object.keys(action).some((key) => FORBIDDEN_FIELDS.has(key));
}

function hasExecutableString(value) {
  if (typeof value === "string") return value.trim().toLowerCase().startsWith("javascript:");
  if (Array.isArray(value)) return value.some(hasExecutableString);
  if (isPlainObject(value)) return Object.values(value).some(hasExecutableString);
  return false;
}

function hasOnlyKeys(action, keys) {
  const allowed = new Set(keys);
  return Object.keys(action).every((key) => allowed.has(key));
}

export function sanitizeSuggestedAction(action, role = "patient") {
  if (!isPlainObject(action) || typeof action.action !== "string") return null;
  if (!ALLOWED_ACTIONS.has(action.action)) return null;
  if (hasForbiddenField(action) || hasExecutableString(action)) return null;
  if (role !== "patient" && PATIENT_ONLY_ACTIONS.has(action.action)) return null;

  switch (action.action) {
    case "OPEN_REPORT":
      return hasOnlyKeys(action, ["action", "report_ref"]) && isServerReference(action.report_ref)
        ? { action: "OPEN_REPORT", report_ref: action.report_ref }
        : null;
    case "VIEW_ABNORMAL":
      return hasOnlyKeys(action, ["action", "report_ref"])
        && (action.report_ref == null || isServerReference(action.report_ref))
        ? { action: "VIEW_ABNORMAL", report_ref: action.report_ref ?? null }
        : null;
    case "VIEW_HISTORY":
      return hasOnlyKeys(action, ["action"]) ? { action: "VIEW_HISTORY" } : null;
    case "VIEW_TREND":
      return hasOnlyKeys(action, ["action", "analyte_id"]) && isServerReference(action.analyte_id)
        ? { action: "VIEW_TREND", analyte_id: action.analyte_id }
        : null;
    case "VIEW_DOCTOR_QUESTIONS":
      return hasOnlyKeys(action, ["action", "report_ref"])
        && (action.report_ref == null || isServerReference(action.report_ref))
        ? { action: "VIEW_DOCTOR_QUESTIONS", report_ref: action.report_ref ?? null }
        : null;
    case "CONFIRM_OCR":
      return hasOnlyKeys(action, ["action", "review_ref"]) && isServerReference(action.review_ref)
        ? { action: "CONFIRM_OCR", review_ref: action.review_ref }
        : null;
    case "RETRY":
      return hasOnlyKeys(action, ["action", "reason_code"])
        ? { action: "RETRY", reason_code: action.reason_code ?? null }
        : null;
    default:
      return null;
  }
}

export function actionDestination(action, role = "patient") {
  const safeAction = sanitizeSuggestedAction(action, role);
  if (!safeAction) return null;

  switch (safeAction.action) {
    case "OPEN_REPORT":
      return `/patient/reports/${encodeURIComponent(safeAction.report_ref)}`;
    case "VIEW_ABNORMAL":
      return safeAction.report_ref
        ? `/patient/reports/${encodeURIComponent(safeAction.report_ref)}`
        : "/patient/analysis";
    case "VIEW_HISTORY":
      return "/patient/history";
    case "VIEW_TREND":
      return `/patient/trends?analyte=${encodeURIComponent(safeAction.analyte_id)}`;
    case "VIEW_DOCTOR_QUESTIONS":
      return safeAction.report_ref
        ? `/patient/reports/${encodeURIComponent(safeAction.report_ref)}#doctor-questions`
        : "/patient/analysis";
    case "CONFIRM_OCR":
      return "/patient/analysis?mode=ocr";
    case "RETRY":
      return null;
    default:
      return null;
  }
}

export function shouldOfferOcrConfirm(response, role = "patient") {
  if (response?.reason_code !== "OCR_REVIEW_REQUIRED") return false;
  return Array.isArray(response.suggested_actions)
    && response.suggested_actions.some((action) => sanitizeSuggestedAction(action, role)?.action === "CONFIRM_OCR");
}

export function proseNavigationDestination() {
  return null;
}
