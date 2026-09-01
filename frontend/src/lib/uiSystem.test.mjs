import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const read = (path) => readFileSync(path, "utf8");

test("patient, doctor and admin shells share the same AppShell and content rail contract", () => {
  const primitives = read("src/components/common/LayoutPrimitives.tsx");
  const patient = read("src/components/patient/PatientShell.tsx");
  const doctor = read("src/components/doctor/DoctorShell.tsx");
  const admin = read("src/components/admin/AdminShell.tsx");
  const css = read("src/app/globals.css");

  assert.match(primitives, /export function AppShell/);
  assert.match(primitives, /export function ContentRail/);
  assert.match(patient, /<AppShell[\s\S]*role="patient"/);
  assert.match(doctor, /<AppShell[\s\S]*role="doctor"/);
  assert.match(admin, /<AppShell[\s\S]*role="admin"/);
  assert.match(css, /--shell-sidebar-width:/);
  assert.match(css, /--shell-topbar-height:/);
  assert.match(css, /--shell-gutter:/);
  assert.match(css, /\.content-rail--standard/);
  assert.match(css, /\.content-rail--wide/);
});

test("brand and system states are shared across public and authenticated surfaces", () => {
  const brand = read("src/components/common/BrandSignature.tsx");
  const state = read("src/components/common/SystemState.tsx");
  const landing = read("src/app/page.tsx");
  const login = read("src/app/login/page.tsx");
  const patientSidebar = read("src/components/patient/PatientSidebar.tsx");
  const doctorSidebar = read("src/components/doctor/DoctorSidebar.tsx");
  const adminSidebar = read("src/components/admin/AdminSidebar.tsx");

  assert.match(brand, /export function BrandMark/);
  assert.match(brand, /export function BrandLockup/);
  assert.match(state, /"loading" \| "empty" \| "error" \| "not-found"/);
  for (const source of [landing, login, patientSidebar, doctorSidebar, adminSidebar]) {
    assert.match(source, /BrandLockup/);
  }
});

test("App Router exposes route-level loading, error and not-found fallbacks", () => {
  const loading = read("src/app/loading.tsx");
  const error = read("src/app/error.tsx");
  const globalError = read("src/app/global-error.tsx");
  const notFound = read("src/app/not-found.tsx");

  assert.match(loading, /kind="loading"/);
  assert.match(error, /kind="error"/);
  assert.match(error, /reset/);
  assert.match(globalError, /kind="error"/);
  assert.match(notFound, /kind="not-found"/);
});

test("core form screens use shared controls and explicit tab semantics", () => {
  const login = read("src/app/login/page.tsx");
  const analysis = read("src/app/patient/analysis/page.tsx");
  const profile = read("src/app/patient/profile/page.tsx");

  assert.match(login, /<Input/);
  assert.match(login, /<Button/);
  assert.match(login, /<SegmentedControl/);
  assert.match(login, /semantics="tabs"/);
  assert.match(login, /role="tabpanel"/);
  assert.match(analysis, /<SegmentedControl/);
  assert.match(analysis, /semantics="tabs"/);
  assert.match(analysis, /<NativeSelect/);
  assert.match(profile, /<Input/);
  assert.match(profile, /<NativeSelect/);
});

test("assistant keeps one flex viewport and one anchored composer across chat states", () => {
  const panel = read("src/components/patient/assistant/ChatPanel.tsx");
  const composer = read("src/components/patient/assistant/ChatComposer.tsx");
  const turn = read("src/components/patient/assistant/AssistantTurn.tsx");
  const css = read("src/app/globals.css");
  const authority = css.slice(css.lastIndexOf("LumiLab Premium Clinical AI Assistant"));

  assert.match(panel, /className="assistant-conversation-view"/);
  assert.match(authority, /\.assistant-panel \{[\s\S]*?display: flex;[\s\S]*?flex-direction: column;/);
  assert.match(authority, /\.assistant-conversation-view \{[\s\S]*?display: flex;[\s\S]*?flex: 1 1 auto;[\s\S]*?min-height: 0;[\s\S]*?flex-direction: column;/);
  assert.match(authority, /\.assistant-transcript-shell \{[\s\S]*?flex: 1 1 auto;[\s\S]*?min-height: 0;/);
  assert.match(authority, /\.assistant-composer \{[\s\S]*?flex: 0 0 auto;/);
  assert.doesNotMatch(authority.match(/\.assistant-conversation-view \{[\s\S]*?\}/)?.[0] ?? "", /grid-template-rows/);

  assert.match(composer, /<InputGroup className="assistant-composer-field">/);
  assert.match(composer, /<InputGroupTextarea/);
  assert.match(composer, /<InputGroupButton/);
  assert.match(turn, /LumiLab đang trả lời/);
  assert.match(turn, /<Bubble variant="ghost"/);
  assert.doesNotMatch(turn, /progressLabel|Đang hiểu câu hỏi|Đang tìm dữ liệu xét nghiệm/);
});

test("assistant composer keeps balanced single-line geometry and pill controls", () => {
  const composer = read("src/components/patient/assistant/ChatComposer.tsx");
  const css = read("src/app/globals.css");
  const authority = css.slice(css.lastIndexOf("LumiLab Premium Clinical AI Assistant"));

  assert.match(composer, /className="assistant-composer-input"/);
  assert.match(composer, /data-state=\{requestActive \? "generating" : "idle"\}/);
  assert.match(authority, /\.assistant-composer-field \{[\s\S]*?min-height: 3\.5rem;[\s\S]*?border-radius: 1\.75rem;/);
  assert.match(authority, /\.assistant-composer \.assistant-composer-input \{[\s\S]*?min-height: 2\.875rem;[\s\S]*?padding: \.75rem \.5rem \.75rem \.8rem;[\s\S]*?line-height: 1\.375rem;/);
  assert.match(authority, /\.assistant-send-stop \{[\s\S]*?width: 2\.75rem !important;[\s\S]*?height: 2\.75rem !important;[\s\S]*?border-radius: 999px !important;/);
});

test("auth card has a stable top anchor while registration can extend the page", () => {
  const login = read("src/app/login/page.tsx");
  const css = read("src/app/globals.css");

  assert.match(login, /className="auth-panel"/);
  assert.match(login, /<FieldGroup className="auth-fields">/);
  assert.match(css, /\.auth-intro \{ position: sticky; top: 0;[\s\S]*?height: 100dvh;/);
  assert.match(css, /\.auth-panel \{[\s\S]*?align-items: flex-start;/);
  assert.match(css, /\.auth-card \{ width: min\(100%, 31rem\); margin: 0;/);
  assert.doesNotMatch(css, /\.auth-card \{[^}]*align-self: center/);
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

test("OCR analysis uses one geometry-stable progress stepper from upload through result", () => {
  const stepper = read("src/components/patient/AnalysisProgressStepper.tsx");
  const ocrReview = read("src/components/OcrReviewPanel.tsx");
  const result = read("src/components/patient/AnalysisResultView.tsx");
  const css = read("src/app/globals.css");
  const outerStepper = stepper.match(/<ol[\s\S]*?>/)?.[0] ?? "";

  assert.match(stepper, /type AnalysisProgressStep = 1 \| 2 \| 3 \| 4/);
  assert.match(stepper, /className="m-0 flex list-none items-center overflow-x-auto/);
  assert.match(stepper, /"flex size-6 items-center justify-center rounded-full border text-xs font-semibold"/);
  assert.match(stepper, /"mx-3 h-px w-8 bg-\[var\(--border\)\]\/60 sm:mx-4 sm:w-12"/);
  assert.match(stepper, /aria-current=\{isCurrent \? "step" : undefined\}/);
  assert.match(stepper, /isComplete \? <Check/);
  assert.doesNotMatch(outerStepper, /bg-|border-|rounded-|shadow-|p-[1-9]/);
  assert.match(ocrReview, /<AnalysisProgressStepper currentStep=\{currentStep\} \/>/);
  assert.match(result, /<AnalysisProgressStepper currentStep=\{4\} \/>/);
  assert.doesNotMatch(result, /ocr-stepper|ocr-stepper-result/);
  assert.doesNotMatch(css, /\.ocr-stepper(?:-result)?/);
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
  assert.match(trends, /<h4>\{item\.display_name\}<\/h4>[\s\S]*<p>\{formatClinicalUnit\(item\.canonical_unit\)\}<\/p>/);
});

test("scientific clinical units use one presentation boundary while canonical values stay unchanged", () => {
  const formatter = read("src/lib/clinicalUnit.mjs");
  const catalog = read("src/generated/analyteCatalog.mjs");
  const clinicalCard = read("src/components/common/ClinicalIndicatorCard.tsx");
  const metricInput = read("src/components/MetricInput.tsx");
  const trendChart = read("src/components/TrendChart.tsx");
  const trendHeatmap = read("src/components/TrendHeatmap.tsx");
  const assistant = read("src/components/patient/assistant/AssistantTurn.tsx");
  const patientUi = read("src/lib/patientUi.mjs");

  assert.match(formatter, /export function formatClinicalText/);
  assert.match(formatter, /export function formatClinicalUnitSuffix/);
  assert.match(formatter, /export function canonicalizeClinicalUnitInput/);
  assert.match(catalog, /unit: "10\^9\/L"/);
  assert.match(catalog, /unit: "10\^12\/L"/);
  for (const source of [clinicalCard, metricInput, trendChart, trendHeatmap, assistant, patientUi]) {
    assert.match(source, /formatClinical(?:Text|Unit|UnitSuffix|Value)/);
  }
  assert.match(metricInput, /canonicalizeClinicalUnitInput/);
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

test("doctor workspace refactor is audit-backed and composes shared operational primitives", () => {
  const audit = read("../DOCTOR_UI_AUDIT.md");
  const queue = read("src/app/doctor/page.tsx");
  const report = read("src/app/doctor/reports/[reportId]/page.tsx");
  const trendList = read("src/app/doctor/trend-reviews/page.tsx");
  const trendDetail = read("src/app/doctor/trend-reviews/[requestId]/page.tsx");
  const css = read("src/app/globals.css");

  assert.match(audit, /Routes discovered/);
  assert.match(audit, /Patient/);
  assert.match(queue, /DoctorPageHeader/);
  assert.match(queue, /DoctorQueueToolbar/);
  assert.doesNotMatch(queue, /DoctorQueueOverview/);
  assert.match(queue, /DoctorStatePanel/);
  assert.match(report, /DoctorSection/);
  assert.match(trendList, /DoctorQueueToolbar/);
  assert.match(trendDetail, /DoctorSection/);
  assert.match(css, /\.app-shell--doctor \.doctor-worklist-card[\s\S]*content-visibility: auto/);
  assert.match(css, /@media \(max-width: 1199px\)[\s\S]*\.app-shell--doctor \.doctor-trend-review-grid[\s\S]*grid-template-columns: minmax\(0, 1fr\)/);
});

test("doctor queue renders independent reusable cards with shared clinical status semantics", () => {
  const page = read("src/app/doctor/page.tsx");
  const card = read("src/components/doctor/DoctorQueueCard.tsx");
  const reasons = read("src/components/doctor/ReasonChip.tsx");
  const history = read("src/components/HistoryPanel.tsx");
  const css = read("src/app/globals.css");

  assert.match(page, /import DoctorQueueCard/);
  assert.match(page, /className="doctor-worklist-cards"/);
  assert.match(page, /doctor-worklist-card doctor-worklist-card--skeleton/);
  assert.match(card, /export default function DoctorQueueCard/);
  assert.match(card, /doctor-worklist-card__identity/);
  assert.match(card, /doctor-worklist-card__reasons/);
  assert.match(card, /doctor-worklist-card__workflow/);
  assert.match(card, /data-queue-state=\{statusState\}/);
  assert.match(card, /StatusIndicator state=\{statusState\}/);
  assert.match(card, /ReasonChip/);
  assert.match(reasons, /LOW_OCR_CONFIDENCE: "ocr-review"/);
  assert.match(reasons, /PATIENT_HAS_QUESTIONS: "question"/);
  assert.match(card, /\? "verified"/);
  assert.match(card, /\? "critical"/);
  assert.match(card, /: "pending"/);
  assert.match(css, /\.doctor-worklist-cards \{[\s\S]*?gap: 0\.75rem/);
  assert.match(css, /\.app-shell--doctor \.doctor-worklist-card \{[\s\S]*?border: 1px solid var\(--border\)[\s\S]*?border-radius: var\(--radius-glass\)[\s\S]*?box-shadow: var\(--shadow-hairline\)/);
  assert.match(css, /\.doctor-worklist-body \.doctor-state-panel > \.system-state \{[\s\S]*?border-radius: var\(--radius-glass\)/);
  assert.match(history, /className="history-row"/);
  assert.match(history, /StatusIndicator/);
  assert.doesNotMatch(page, /doctor-worklist-row|QueueRow/);
  assert.doesNotMatch(card, /doctor-worklist-row/);
  assert.doesNotMatch(css, /doctor-worklist-row/);
  assert.doesNotMatch(css, /\.doctor-worklist-card\[data-severity="critical"\][\s\S]*?background:/);
  assert.doesNotMatch(css, /\.doctor-worklist-cards > li \+ li[\s\S]*?border-top:/);
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
