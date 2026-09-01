# DOCTOR UI AUDIT

Date: 2026-09-01  
Scope: frontend-only visual refactor. API contracts, RBAC, patient-data access, medical thresholds, classification logic, and NORMAL / LOW / HIGH / CRITICAL semantics are protected and unchanged.

## Routes discovered

| Route | Primary job | Clinical states present |
|---|---|---|
| `/doctor` | Operational verification queue | pending, critical, OCR review, patient question, verified, loading, empty, error, pagination |
| `/doctor/reports/[reportId]` | Finding-by-finding report verification | critical / abnormal / normal findings, OCR source context, patient questions, pending / corrected / skipped / agreed, verified, loading, error |
| `/doctor/trend-reviews` | Trend-review queue | pending, reviewed, all, empty, loading, error |
| `/doctor/trend-reviews/[requestId]` | Trend review and clinician response | pending, reviewed, cancelled, rejected, loading, error |

No Doctor sandbox route or standalone Doctor OCR/question route exists in the current App Router tree. OCR validation and patient-question review are report-detail states reached through `/doctor?tab=ocr`, `/doctor?tab=questions`, and `/doctor/reports/[reportId]`.

## Component map

### Shared Doctor components

- `DoctorShell`, `DoctorSidebar`, `DoctorTopbar`: authenticated Doctor shell and navigation.
- `DoctorPageHeader`: wrapper over the shared `PageHero` primitive.
- `DoctorQueueOverview`: five operational counters.
- `QueueTabs`: queue filters and counts.
- `QueueRow`: patient identity, review reasons, medical status, progress, and report CTA.
- `ReasonChip`: maps backend review flags to the shared semantic status system.
- `DoctorReviewProgressBar`: sticky report progress and completion action.
- `DoctorFindingCard`: clinical finding review actions.
- `DoctorReportSidebar`: patient context, review flags, original OCR image, and patient questions.

### Reused Patient/shared primitives

- `AppShell`, `ContentRail`, `PageHero`, `ActionGroup` for the common LumiLab shell grammar.
- `BrandLockup` and `ClinicalSignal` for brand continuity.
- `StatusIndicator`, `SeverityBadge`, and `VerificationBadge` for stable medical/workflow semantics.
- `ClinicalIndicatorCard` and `DoctorNoteBlock` for readable opaque clinical content.
- shadcn Base primitives: `Button`, `Card`, `Tabs`, `Textarea`, `Skeleton`, `Sheet`, and shared `SystemState`/`Empty`.
- Patient formatting helpers for locale-safe dates, times, demographics, and assessment labels.

## Problems identified

### Cross-route hierarchy

- The queue landing uses a one-off heading while detail routes use `DoctorPageHeader`, so Doctor screens do not share one dependable page hierarchy.
- The existing wide content rail and large vertical gaps consume too much first viewport height for a daily operations surface.
- Multiple generations of Doctor CSS remain in the global cascade. Late rules repair some surfaces but do not provide a single scoped Doctor authority.

### Queue operations

- The overview is a glass card containing five tile-like metrics; the title and card framing add height without improving scan speed.
- Queue tabs read as a large segmented control rather than a compact operational filter bar.
- The toolbar exposes no useful secondary control and visually separates filters from the list more than necessary.
- Queue rows contain the right data but the current equal visual weight makes identity, reason, severity, progress, and action compete.
- Critical rows have a narrow accent, but their reason and row surface do not form a restrained, unmistakable priority treatment.
- Long queue performance has no explicit `content-visibility` optimization.
- Empty and error states are custom markup instead of the shared state primitive; the empty state also uses a text checkmark as a structural icon.

### Report verification

- Patient/report context, review reason, OCR context, questions, finding review, and completion progress are present but do not read as a clear workflow sequence.
- The right rail is a stack of visually similar cards; sections need stronger headings and differentiated clinical/operational roles without adding more card chrome.
- Finding actions and outcome blocks are visually heavier than the clinical value and AI explanation they govern.
- Loading placeholders use bespoke empty `div` elements instead of the installed `Skeleton` primitive.
- Error screens repeat nested custom state cards rather than the shared `SystemState` component.
- The original-image preview lacks explicit intrinsic dimensions; this can cause layout movement when the backend image loads.

### Trend review

- The list route combines a loose filter heading, oversized tab surface, and floating cards rather than one compact queue container.
- Trend rows do not align patient, analyte/context, status, and action as consistently as the report queue.
- Detail content has the necessary chart, snapshot table, AI explanation, metadata, and clinician action, but section framing is inconsistent with report verification.
- The snapshot table uses a bespoke status span rather than the shared semantic status system.
- The native select needs an explicit named form control and stable light/dark surface treatment.

### Shell, responsive behavior, and interaction

- Sidebar/topbar carry the PatientShell DNA, but active-nav glow and generous navigation spacing are too decorative for the Doctor workspace.
- Several icon/control implementations predate the current Base Nova composition rules.
- Desktop density is acceptable only above wide laptop sizes; 1024px pushes queue workflow content into a second row with weak alignment.
- Focus states exist in parts of the queue, but state pages, rows, tabs, pagination, image preview, and report actions need one consistent visible-focus treatment.
- Some loading copy uses three periods instead of the ellipsis character required by the current UI guideline.

## Refactor direction

1. Make `DoctorPageHeader` the compact shared Doctor hero authority.
2. Turn `DoctorQueueOverview` into a low-height operational strip with semantic counter accents, not tiles.
3. Consolidate queue filters and context into one `DoctorQueueToolbar`, with URL-reflected tabs and clear count hierarchy.
4. Rebuild `QueueRow` as a stable three-zone operations row: patient/report, review reason, clinical workflow/action.
5. Add shared `DoctorSection` and `DoctorStatePanel` primitives for report/trend grouping and loading/empty/error consistency.
6. Apply one final `.app-shell--doctor` CSS authority after the existing cascade, with desktop-first density and deliberate 1366 / 1024 / mobile collapse.
7. Keep every medical and workflow state derived from the existing backend response and shared status mapping; no new business rule or medical inference will be introduced.

