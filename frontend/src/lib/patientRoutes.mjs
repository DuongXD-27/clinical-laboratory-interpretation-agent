/**
 * Canonical Patient Route Constants & Navigation Configuration.
 *
 * This module is the single authoritative source of truth for all patient-facing
 * URLs in the application. It is imported by PatientSidebar, PatientTopbar,
 * Dashboard QuickActions, and verified by patientRoutes.test.mjs against the
 * actual Next.js App Router filesystem structure.
 */

export const PATIENT_ROUTES = Object.freeze({
  HOME: "/patient",
  ANALYSIS: "/patient/analysis",
  HISTORY: "/patient/history",
  TRENDS: "/patient/trends",
  PROFILE: "/patient/profile",
  REPORTS: "/patient/reports",
  REPORT_DETAIL_TEMPLATE: "/patient/reports/[reportId]",
  HISTORY_REPORT_DETAIL_TEMPLATE: "/patient/history/[reportId]",
  reportDetail: (reportId) => `/patient/reports/${reportId}`,
});

export const CANONICAL_PATIENT_NAV_ITEMS = Object.freeze([
  {
    href: PATIENT_ROUTES.HOME,
    label: "Tổng quan",
    exact: true,
    patientOnly: false,
    iconKey: "dashboard",
  },
  {
    href: PATIENT_ROUTES.ANALYSIS,
    label: "Phân tích xét nghiệm",
    exact: false,
    patientOnly: false,
    iconKey: "analysis",
  },
  {
    href: PATIENT_ROUTES.HISTORY,
    label: "Lịch sử kết quả",
    exact: false,
    patientOnly: true,
    iconKey: "history",
  },
  {
    href: PATIENT_ROUTES.TRENDS,
    label: "Xu hướng chỉ số",
    exact: false,
    patientOnly: true,
    iconKey: "trends",
  },
  {
    href: PATIENT_ROUTES.PROFILE,
    label: "Thông tin cá nhân",
    exact: false,
    patientOnly: true,
    iconKey: "profile",
  },
]);

export const CANONICAL_PATIENT_SUBROUTES = Object.freeze([
  { href: PATIENT_ROUTES.REPORT_DETAIL_TEMPLATE, label: "Chi tiết phiếu xét nghiệm" },
  { href: PATIENT_ROUTES.HISTORY_REPORT_DETAIL_TEMPLATE, label: "Chi tiết phiếu xét nghiệm (lịch sử)" },
]);

/**
 * Determine whether a navigation item is active given the current pathname.
 * @param {string} pathname
 * @param {{ href: string, exact?: boolean }} item
 * @returns {boolean}
 */
export function isNavActive(pathname, item) {
  if (item.exact) return pathname === item.href;
  if (item.href === PATIENT_ROUTES.HISTORY) {
    return pathname.startsWith(item.href) || pathname.startsWith("/patient/reports/");
  }
  return pathname.startsWith(item.href);
}

/**
 * Derive the patient page title from the current pathname.
 * @param {string} pathname
 * @returns {string}
 */
export function getPatientPageTitle(pathname) {
  if (pathname.startsWith(PATIENT_ROUTES.ANALYSIS)) return "Phân tích xét nghiệm";
  if (pathname.startsWith("/patient/reports/") || pathname.startsWith("/patient/history/")) {
    return "Kết quả xét nghiệm";
  }
  if (pathname.startsWith(PATIENT_ROUTES.HISTORY)) return "Lịch sử kết quả";
  if (pathname.startsWith(PATIENT_ROUTES.TRENDS)) return "Xu hướng chỉ số";
  if (pathname.startsWith(PATIENT_ROUTES.PROFILE)) return "Thông tin cá nhân";
  return "Tổng quan";
}
