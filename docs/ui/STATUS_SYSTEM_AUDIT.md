# VMEC-05 Status System Audit

Audit date: 2026-08-29  
Scope: `frontend/src` (Patient, Doctor, shared UI; Admin noted where it reuses the shared badge)  
Boundary: presentation only. No classification, threshold, verification, OCR, API, auth, or workflow behavior may change.

## Scan summary

- 42 distinct visual status rendering sites across 24 frontend files.
- 11 duplicated presentation patterns: generic `Badge`, `ClinicalStatusChip`, legacy `status-badge`, queue state text, queue reason chip, hand-built dashboard label, trend critical badge, trend-review panels, OCR amber/green summaries, assistant delivery alerts, and admin HTTP badges.
- Five semantic families: clinical severity, data trust/verification, workflow, user interaction, and system/data quality.
- Primary inconsistency: clinical severity and secondary metadata are both rendered as bordered capsules with similar size and weight.
- Accessibility gaps: one emoji-only trend warning, several color-dot summaries, and hand-built labels whose icon semantics and optical sizing differ.

## Canonical taxonomy and presentation hierarchy

| Family | States | Default importance | Default presentation |
|---|---|---:|---|
| Clinical severity | normal, abnormal, critical, unknown | passive / attention / urgent | inline / soft / strong |
| Data trust | unverified, pending verification, verified | passive / attention / passive | inline / soft / inline |
| Workflow | pending, reviewing, processed, completed, cancelled, rejected | passive | inline (soft only when isolated) |
| User interaction | question, comment, needs response | attention | soft |
| System/data quality | OCR review, input review, unsupported, unknown data | attention | soft |

## Status inventory

| Status | Internal value | Location | Role | Family | Importance | Existing presentation | Duplicate | UX issue | Proposed presentation |
|---|---|---|---|---|---|---|---:|---|---|
| Bình thường / Trong khoảng | `normal`, `NORMAL` | analyte cards, report rows/details, dashboard summary, heatmap | Shared | Clinical | passive | capsule, dot, colored text, swatch | yes | too many visual forms; green capsule competes with values | quiet inline icon + label |
| Bất thường / Cần lưu ý | `abnormal`, `HIGH`, `LOW` | analyte cards, report rows/details, dashboard cards/summary, heatmap | Shared | Clinical | attention | bordered amber pill, hand-built label, dot, swatch | yes | saturated traffic-light styling and duplicated mappings | soft frosted indicator |
| Giá trị khẩn cấp / Nguy kịch | `critical`, `CRITICAL_HIGH`, `CRITICAL_LOW`, `is_critical` | analyte cards, analysis alert, report detail, dashboard, queue, trends, heatmap | Shared | Clinical | urgent | red pill, banner, left-border card, raw text, emoji | yes | inconsistent urgency and duplicated treatment | strong clinical indicator; alert surfaces remain alerts |
| Chưa phân loại / Chưa rõ | `unknown`, `UNKNOWN`, `HOLD` | analyte cards, analysis summary, heatmap | Patient | Clinical/data quality | passive | gray pill, dot, swatch | yes | family ambiguity and color-led legend | inline help icon + label |
| Chưa kiểm chứng | `unverified` | recent reports, history, report details | Shared | Data trust | passive | gray bordered capsule | yes | visually equal to severity | quiet inline trust label |
| Đang chờ bác sĩ xem | `pending_review` | recent reports, history, report details | Shared | Data trust/workflow | attention | blue-gray capsule | yes | wording is secondary but styling is primary | compact soft trust indicator |
| Đã xác minh | `verified` | recent reports, history, report details, doctor queue | Shared | Data trust | passive | green capsule / queue label | yes | can visually neutralize a critical label | quiet inline check + label |
| Chờ đánh giá | queue pending/default | doctor queue overview, tabs, rows | Doctor | Workflow | passive | metric tint, counter tab, independent row label | yes | counters and row state resemble semantic badges | neutral inline workflow label; quiet tab counter |
| Đã xử lý / progress | `findings_reviewed`, review progress | queue rows and review footer | Doctor | Workflow | passive | progress bar plus text | yes | copy and progress are split across local implementations | inline workflow copy plus existing progress track |
| Đã đồng ý | `agreed` | finding cards, trend reviews | Doctor/Patient | Workflow | passive | green capsule / green panel | yes | oversized success treatment | quiet inline completion label |
| Đã đính chính | `corrected` | finding cards, trend reviews | Doctor/Patient | Workflow | attention | green capsule / green panel | yes | correction is not generic success | inline review label with neutral-review tone |
| Đã bỏ qua | `skipped` | finding cards | Doctor | Workflow | passive | gray capsule | no | container is heavier than the state | inline neutral label |
| Đang chờ duyệt | `PENDING` | doctor/patient trend review | Shared | Workflow | passive | generic pending capsule / amber panel | yes | inconsistent between roles | inline/soft workflow indicator |
| Đã duyệt | `REVIEWED` | doctor/patient trend review | Shared | Workflow | passive | green capsule / green panel | yes | overstates secondary metadata | quiet inline completion label |
| Đã hủy | `CANCELLED` | trend review and assistant delivery | Shared | Workflow | passive | gray capsule / alert | yes | cancellation confused with error in some contexts | neutral inline state; alert only when action failed |
| Từ chối | `REJECTED` | trend review | Shared | Workflow | attention | critical capsule | no | looks like clinical danger | soft workflow rejection indicator |
| Cần theo dõi/trao đổi thêm | `needs_follow_up` | trend review panels | Shared | Workflow/interaction | attention | amber panel | yes | visually resembles clinical abnormality | soft review indicator |
| OCR cần kiểm tra | `LOW_OCR_CONFIDENCE`, `needs_review` | queue tabs/rows/sidebar, OCR panel | Shared | System/data quality | attention | cyan capsule plus multiple amber summaries | yes | fragmented and sometimes amber-warning clinical look | soft cool-teal data-quality indicator |
| Cần kiểm tra dữ liệu đầu vào | `NEED_REVIEW` | analyte cards | Patient | System/data quality | attention | amber bordered message | no | resembles medical abnormality | soft cool-teal status callout |
| Chưa được hỗ trợ diễn giải | out-of-scope/unsupported | analysis result, assistant | Patient | System/data quality | passive | generic info message | yes | lacks a consistent system-state cue | inline neutral information indicator |
| Có câu hỏi | `PATIENT_HAS_QUESTIONS` | queue overview/tabs/rows/sidebar | Doctor | User interaction | attention | bronze capsule and metric tint | yes | looks like medical warning | soft bronze interaction indicator |
| Cần phản hồi / đã trả lời | question answer state | doctor sidebar/history | Shared | User interaction | attention/passive | card/editor/green answer panel | yes | state is implicit and locally colored | inline question/answered metadata |
| Đã lưu / trùng phiếu | `saved`, `duplicate` | analysis result | Patient | System/workflow | passive | generic info message | yes | unrelated system states look identical | quiet inline system label within info surface |
| Tải lên thành công | local upload success | upload dropzone | Patient | Workflow | passive | green text | no | not aligned to shared icon geometry | inline completion indicator |
| Đang tải / xử lý / lỗi / hủy | assistant delivery states | assistant turn | Patient | Workflow/system | attention | skeleton/progress/Alert variants | yes | delivery state is not separated from clinical alerts | workflow indicator; preserve true error alert |
| HTTP success/warning/error | status code groups | Admin traces | Admin | System | attention | generic colored Badge | yes | shared badge variants remain traffic-light pills | system-family inline/soft indicator |

## Affected components/pages

Patient: dashboard, recent activity, analysis result, analyte cards, history, report detail, trends/heatmap, trend review, OCR review, assistant delivery states.  
Doctor: queue overview, filters, rows, report header/sidebar, finding cards, progress, trend-review list/detail.  
Shared: `ClinicalStatusChip`, severity/verification wrappers, base Badge, status tokens, alerts and legends.

## Migration contract

The implementation will introduce one type-safe `StatusIndicator` whose centralized config derives family, tone, icon, level, and label. Legacy wrappers may remain as compatibility facades but must render the new primitive. Alert banners, progress bars, heatmap cells, and tab counters remain distinct components because they are not status badges.

## V2 visual refinement

The shared status primitive now uses three visibly distinct grammars instead of one capsule treatment:

- Metadata states are unenclosed icon-and-text labels with the semantic hue concentrated in the icon.
- Attention states use a compact, small-radius, nearly neutral glass field with a luminous neutral hairline; no semantic-colored outline or surface remains.
- Critical clinical states have no label enclosure. A ruby focal glyph, darker restrained label, and an optional two-pixel accent on the owning row/card provide hierarchy.

Supporting reason labels are rendered inline when a primary severity signal is already present. Critical and flagged doctor cards no longer combine a semantic card border, status capsule, and reason capsule.

### Deliberate non-status exceptions

- `components/ui/alert.tsx`: full-width alert surfaces, including destructive system failures, are messages rather than status labels.
- `components/patient/AnalysisResultView.tsx`: the critical emergency-warning banner must remain an unmistakable alert surface.
- `app/patient/trends/page.tsx`: the critical escalation banner is an emergency-warning surface.
- `app/admin/page.tsx` and `app/admin/traces/[requestId]/page.tsx`: error/SLO cards are operational alerts, not metadata badges.
- Queue/tab counts are navigation counters and remain quiet counters rather than adopting clinical status treatment.
- Progress tracks, reference-range bars, and heatmap cells encode quantitative data and remain data visualizations.
