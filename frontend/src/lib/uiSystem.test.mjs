import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(path, "utf8");

test("patient and doctor shells share the same AppShell and content rail contract", () => {
  const primitives = read("src/components/common/LayoutPrimitives.tsx");
  const patient = read("src/components/patient/PatientShell.tsx");
  const doctor = read("src/components/doctor/DoctorShell.tsx");
  const css = read("src/app/globals.css");

  assert.match(primitives, /export function AppShell/);
  assert.match(primitives, /export function ContentRail/);
  assert.match(patient, /<AppShell[\s\S]*role="patient"/);
  assert.match(doctor, /<AppShell[\s\S]*role="doctor"/);
  assert.match(css, /--shell-sidebar-width:/);
  assert.match(css, /--shell-topbar-height:/);
  assert.match(css, /--shell-gutter:/);
  assert.match(css, /\.content-rail--standard/);
  assert.match(css, /\.content-rail--wide/);
});

test("patient and doctor indicators use one clinical card grammar", () => {
  const card = read("src/components/common/ClinicalIndicatorCard.tsx");
  const patient = read("src/components/patient/IndicatorResultCard.tsx");
  const doctor = read("src/components/doctor/DoctorFindingCard.tsx");
  const analysis = read("src/components/patient/AnalysisResultView.tsx");
  const history = read("src/components/HistoryPanel.tsx");
  const report = read("src/components/patient/PatientReportDetail.tsx");

  assert.match(card, /clinical-indicator-card/);
  assert.match(patient, /ClinicalIndicatorCard/);
  assert.match(doctor, /ClinicalIndicatorCard/);
  assert.match(analysis, /indicator-card-grid/);
  assert.match(history, /indicator-card-grid/);
  assert.match(report, /indicator-card-grid/);
});

test("trend controls remain present inside one control surface", () => {
  const trends = read("src/app/patient/trends/page.tsx");
  for (const label of [
    "Từng chỉ số",
    "Cả nhóm chức năng",
    "5 kết quả gần nhất",
    "3 tháng gần nhất",
    "Biểu đồ đường",
    "Ma trận nhiệt",
    "Giải thích cả nhóm",
  ]) {
    assert.ok(trends.includes(label), `missing trend control: ${label}`);
  }
  assert.match(trends, /trend-control-surface/);
  assert.match(trends, /<h4>\{item\.display_name\}<\/h4>[\s\S]*<p>\{item\.canonical_unit\}<\/p>/);
});

test("review toolbar is in main flow and has no legacy viewport-fixed rule", () => {
  const route = read("src/app/doctor/reports/[reportId]/page.tsx");
  const css = read("src/app/globals.css");
  const toolbarIndex = route.indexOf("<DoctorReviewProgressBar");
  const gridIndex = route.indexOf('<div className="doctor-report-grid">');
  const contractIndex = css.indexOf("/* VMEC shared clinical UI contract");
  const legacyStart = css.indexOf(".review-progress-bar {");
  const legacyEnd = css.indexOf("}", legacyStart);
  const overrideIndex = css.indexOf(".review-progress-bar.review-progress-toolbar", contractIndex);

  assert.ok(toolbarIndex > 0 && toolbarIndex < gridIndex);
  assert.doesNotMatch(css.slice(legacyStart, legacyEnd), /position: fixed/);
  assert.match(css.slice(overrideIndex, overrideIndex + 500), /position: sticky/);
});

test("assistant safe area and responsive small-multiple tiers are explicit", () => {
  const css = read("src/app/globals.css");
  assert.match(css, /--assistant-safe-inline:/);
  assert.match(css, /--assistant-safe-block:/);
  assert.match(css, /\.app-shell--patient \.app-shell__main/);
  assert.match(css, /\.trend-small-multiples \{ display: grid; grid-template-columns: repeat\(3/);
  assert.match(css, /@media \(max-width: 1279px\)[\s\S]*\.trend-small-multiples \{ grid-template-columns: repeat\(2/);
  assert.match(css, /@media \(max-width: 767px\)[\s\S]*\.trend-small-multiples \{ grid-template-columns: minmax\(0, 1fr\)/);
});

test("Vietnamese date controls keep native ISO values while presenting dd/mm/yyyy", () => {
  const localizedDate = read("src/components/common/LocalizedDateInput.tsx");
  const history = read("src/components/HistoryPanel.tsx");
  const analysis = read("src/app/patient/analysis/page.tsx");

  assert.match(localizedDate, /type="date"/);
  assert.match(localizedDate, /lang="vi-VN"/);
  assert.match(localizedDate, /dd\/mm\/yyyy/);
  assert.match(history, /LocalizedDateInput/);
  assert.match(analysis, /LocalizedDateInput/);
});

test("patient indicator explanations use independent accessible progressive disclosure", () => {
  const card = read("src/components/common/ClinicalIndicatorCard.tsx");
  const css = read("src/app/globals.css");

  assert.match(card, /useState\(false\)/);
  assert.match(card, /<button[\s\S]*aria-controls=\{explanationId\}[\s\S]*aria-expanded=\{expanded\}/);
  assert.match(card, /setExpanded\(\(current\) => !current\)/);
  assert.match(card, /expanded \? "Thu gọn" : "Xem thêm"/);
  assert.match(css, /\.clinical-card__explanation[\s\S]*-webkit-line-clamp: 5/);
  assert.match(css, /\.indicator-card-grid[\s\S]*align-items: start/);
});

test("history rows expose three deliberate information zones", () => {
  const history = read("src/components/HistoryPanel.tsx");
  const css = read("src/app/globals.css");

  assert.match(history, /history-row__identity/);
  assert.match(history, /history-row__summary/);
  assert.match(history, /history-row__workflow/);
  assert.match(css, /grid-template-columns: minmax\(0, 48fr\) minmax\(12rem, 27fr\) minmax\(13rem, 25fr\)/);
});

test("shared desktop workspace has symmetric gutters and doctor report spacing has no additive margins", () => {
  const css = read("src/app/globals.css");
  const contractStart = css.indexOf("/* VMEC shared clinical UI contract");
  const patientMainStart = css.indexOf(".app-shell--patient .app-shell__main", contractStart);
  const patientMainEnd = css.indexOf("}", patientMainStart);
  const toolbarStart = css.indexOf(".review-progress-bar.review-progress-toolbar");
  const toolbarEnd = css.indexOf("}", toolbarStart);
  const reportGridStart = css.indexOf(".doctor-report-grid", toolbarEnd);
  const reportGridEnd = css.indexOf("}", reportGridStart);

  assert.doesNotMatch(css.slice(patientMainStart, patientMainEnd), /padding-right/);
  assert.match(css.slice(toolbarStart, toolbarEnd), /margin: 0/);
  assert.match(css.slice(reportGridStart, reportGridEnd), /margin-top: 0/);
});

test("formatClinicalAssessment localizes clinical states into Vietnamese without raw English enums", async () => {
  const { formatClinicalAssessment } = await import("./patientUi.mjs");

  assert.equal(formatClinicalAssessment("NORMAL"), "Bình thường");
  assert.equal(formatClinicalAssessment("normal"), "Bình thường");
  assert.equal(formatClinicalAssessment("HIGH"), "Cao");
  assert.equal(formatClinicalAssessment("high"), "Cao");
  assert.equal(formatClinicalAssessment("LOW"), "Thấp");
  assert.equal(formatClinicalAssessment("low"), "Thấp");
  assert.equal(formatClinicalAssessment("CRITICAL"), "Giá trị khẩn cấp");
  assert.equal(formatClinicalAssessment("UNKNOWN"), "Chưa thể đánh giá");
  assert.equal(formatClinicalAssessment("PENDING"), "Đang chờ");
  assert.equal(formatClinicalAssessment("REVIEWED"), "Đã đánh giá");
  assert.equal(formatClinicalAssessment("APPROVED"), "Đã duyệt");
  assert.equal(formatClinicalAssessment("REJECTED"), "Đã từ chối");
  assert.equal(formatClinicalAssessment("CANCELLED"), "Đã huỷ");
});

test("formatPatientDemographics formats age safely and omits missing age cleanly", async () => {
  const { formatPatientDemographics } = await import("./patientUi.mjs");

  assert.equal(formatPatientDemographics("male", 45), "Nam · 45 tuổi");
  assert.equal(formatPatientDemographics("female", 30), "Nữ · 30 tuổi");
  assert.equal(formatPatientDemographics("male", null), "Nam");
  assert.equal(formatPatientDemographics("female", undefined), "Nữ");
  assert.equal(formatPatientDemographics("other", ""), "Khác");
  assert.equal(formatPatientDemographics("male", "-"), "Nam");
  assert.doesNotMatch(formatPatientDemographics("male", null), /- tuổi/);
  assert.doesNotMatch(formatPatientDemographics("female", undefined), /- tuổi/);
});

test("native browser dialogs are replaced with ClinicalConfirmDialog in doctor and patient workflows", () => {
  const doctorReport = read("src/app/doctor/reports/[reportId]/page.tsx");
  const patientReport = read("src/components/patient/PatientReportDetail.tsx");
  const confirmDialog = read("src/components/common/ClinicalConfirmDialog.tsx");

  assert.doesNotMatch(doctorReport, /window\.confirm/);
  assert.doesNotMatch(doctorReport, /window\.alert/);
  assert.doesNotMatch(patientReport, /window\.confirm/);
  assert.match(doctorReport, /<ClinicalConfirmDialog/);
  assert.match(patientReport, /<ClinicalConfirmDialog/);
  assert.match(confirmDialog, /export default function ClinicalConfirmDialog/);
});

test("doctor trend review page establishes task-based H1 and unified two-column geometry", () => {
  const page = read("src/app/doctor/trend-reviews/[requestId]/page.tsx");
  const listPage = read("src/app/doctor/trend-reviews/page.tsx");
  const sidebar = read("src/components/doctor/DoctorSidebar.tsx");
  const topbar = read("src/components/doctor/DoctorTopbar.tsx");

  assert.match(page, /title=\{`Đánh giá xu hướng \$\{review\.display_name\}`\}/);
  assert.doesNotMatch(page, /title=\{detail\.patient\.name\}/);
  assert.match(page, /formatPatientDemographics/);
  assert.match(page, /doctor-trend-review-grid/);
  assert.match(page, /trend-chart-card/);
  assert.match(page, /trend-data-card/);
  assert.match(page, /formatClinicalAssessment/);
  assert.match(listPage, /title="Đánh giá xu hướng"/);
  assert.match(sidebar, /label: "Đánh giá xu hướng"/);
  assert.match(topbar, /return "Đánh giá xu hướng"/);
});

