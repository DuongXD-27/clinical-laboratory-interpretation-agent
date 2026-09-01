# LumiLab — UI Coverage Report

Ngày cập nhật: 01/09/2026

## 1. Coverage summary

| Miền | Screens/routes | Audited | Refactored hoặc nhận shared system | State coverage |
|---|---:|---:|---:|---:|
| Public/auth | 3 | 3 | 3 | default, validation, loading, error |
| Patient | 6 canonical + 1 alias | 7 | 7 | loading, empty, error, populated, guest, critical, confirmation |
| Doctor | 4 | 4 | 4 | loading, empty, error, populated, review, completion |
| Admin | 2 | 2 | 2 | loading, error, populated, filters, pagination |
| System | 4 fallback types | 4 | 4 | loading, error, global error, not found |

Route coverage: **16/16 product pages**, cộng **4 system fallback types**.

## 2. Route-by-route coverage

| Route | Desktop layout | Mobile layout | Loading | Empty | Error | Primary interaction | Status |
|---|---|---|---|---|---|---|---|
| `/` | ✓ | ✓ | n/a | n/a | n/a | CTA/nav | Covered |
| `/login` | ✓ | ✓ | ✓ | n/a | ✓ | login/register/guest/Google | Covered |
| `/privacy` | ✓ | ✓ | n/a | n/a | n/a | long-form navigation | Covered |
| `/patient` | ✓ | ✓ | ✓ | ✓ | ✓ | dashboard actions | Covered |
| `/patient/analysis` | ✓ | ✓ | ✓ | ✓ | ✓ | manual/OCR/analyze | Covered |
| `/patient/history` | ✓ | ✓ | ✓ | ✓ | ✓ | filter/open/paginate | Covered |
| `/patient/history/[reportId]` | alias | alias | inherited | inherited | inherited | report detail | Covered |
| `/patient/reports/[reportId]` | ✓ | ✓ | ✓ | n/a | ✓ | disclose/delete/ack | Covered |
| `/patient/trends` | ✓ | ✓ | ✓ | ✓ | ✓ | filters/chart/heatmap/review | Covered |
| `/patient/profile` | ✓ | ✓ | ✓ | ✓ | ✓ | view/edit/save | Covered |
| `/doctor` | ✓ | ✓ | ✓ | ✓ | ✓ | filter/open/paginate | Covered |
| `/doctor/reports/[reportId]` | ✓ | ✓ | ✓ | n/a | ✓ | review/correct/complete | Covered |
| `/doctor/trend-reviews` | ✓ | ✓ | ✓ | ✓ | ✓ | filter/open | Covered |
| `/doctor/trend-reviews/[requestId]` | ✓ | ✓ | ✓ | n/a | ✓ | assess/comment/save | Covered |
| `/admin` | ✓ | ✓ | ✓ | table empty | ✓ | filter/refresh/paginate | Covered |
| `/admin/traces/[requestId]` | ✓ | ✓ | ✓ | ✓ | ✓ | inspect/refresh | Covered |

## 3. Component coverage

### Added

- `BrandSignature.tsx`: BrandMark, BrandLockup, ClinicalSignal.
- `SystemState.tsx`: loading, empty, error, not-found, shell gate.
- shadcn/Base UI additions: Empty, Spinner, Separator, NativeSelect.
- App Router: loading, error, global-error, not-found.

### Refactored

- AppShell supports patient, doctor và admin.
- Patient/Doctor/Admin sidebars and topbars share brand/navigation grammar.
- Button, Input, Textarea, Card, Alert, Badge and NativeSelect use canonical token sizing/material.
- Landing, login and privacy share product identity.
- Patient dashboard, analysis and profile use shared states/controls.
- Existing history/report/trend/doctor/admin screens inherit unified content rail, surfaces and responsive rules.

### Intentionally unchanged

- Status mappings and medical copy behavior.
- API calls, payloads and data models.
- Auth guards, redirects, role checks and backend authorization.
- Threshold/range/unit/source logic.
- Chart data transformation and clinical bands.
- Assistant action allowlist and clinical safety behavior.

## 4. Accessibility coverage

| Check | Result |
|---|---|
| Skip link for authenticated roles | patient ✓ doctor ✓ admin ✓ |
| Active nav semantics | `aria-current` ✓ |
| Login tabs | tablist/tab/aria-selected ✓ |
| Analysis tabs | tablist/tab/aria-selected/controls ✓ |
| Loading announcements | role=status ✓ |
| Error announcements | role=alert ✓ |
| Icon-only naming | preserved ✓ |
| Reduced motion | page and hover motion disabled ✓ |
| Default control target | 44px ✓ |
| Color-only medical status | avoided via icon + text ✓ |
| Dialog focus management | Base UI primitives retained ✓ |

## 5. Automated verification

Commands executed from `frontend`:

```text
npm test
npm run lint
npm run build
```

Latest verified results:

- Unit/contract tests: 127/127 passing.
- ESLint: passing, zero reported errors.
- Next.js production build: passing; all static/dynamic routes compiled.
- `git diff --check`: passing; only line-ending notices from existing CRLF files.

## 6. Visual verification status

Reviewed repository screenshots from prior UI evidence for dashboard, history, analysis, trends, doctor queue/review and dialogs. Attempted the required in-app browser flow, but the environment returned no available browser session. Therefore:

- static/code/contract/responsive audit: complete;
- lint/test/build: complete;
- fresh screenshot comparison and live keyboard walkthrough: pending environment availability.

## 7. Known residual risks

1. `globals.css` vẫn chứa legacy layers trước final authority; build order currently guarantees the new system wins, but future extraction should be incremental and test-protected.
2. Google Sign-In content is rendered by third-party iframe/widget, so final pixel/focus QA requires the OAuth-enabled browser environment.
3. Dense chart/table layouts should receive a final live pass with long Vietnamese labels and real production-sized datasets.

Không có residual risk đã biết nào liên quan đến thay đổi medical thresholds, status meaning, API contract, auth/RBAC hoặc patient access.
