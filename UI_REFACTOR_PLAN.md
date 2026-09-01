# LumiLab — UI Refactor Plan

Kế hoạch này ghi cả quyết định và trạng thái triển khai thực tế. Mục tiêu là refactor presentation theo chiều dọc mà không chạm medical/business/auth contracts.

## 1. Guardrails

- Không đổi API endpoints, request/response payloads hoặc data fetching behavior.
- Không đổi reference range, critical threshold, comparison, alias, unit conversion hoặc provenance.
- Không đổi auth/RBAC, role home, patient ownership hoặc session behavior.
- Không đổi NORMAL / LOW / HIGH / CRITICAL và emergency warning.
- Ưu tiên shared component/token; tránh fork component theo route.

## 2. Phases

| Phase | Phạm vi | Deliverable | Trạng thái |
|---|---|---|---|
| 0 | Inventory, screenshots hiện có, contract và baseline | Route/component/state matrix | Hoàn tất |
| 1 | Foundation | Tokens, content tiers, shadows, radius, typography, focus | Hoàn tất |
| 2 | Brand và shell | BrandMark, BrandLockup, ClinicalSignal, shared admin shell | Hoàn tất |
| 3 | Primitives và states | Button/Input/Textarea/Card/Alert/Badge, Empty/Spinner/Select, route fallbacks | Hoàn tất |
| 4 | Public/auth | Landing, login/register/guest, privacy | Hoàn tất |
| 5 | Patient | Dashboard, analysis, profile; shared styling cho history/report/trends | Hoàn tất |
| 6 | Doctor/admin | Unified shell, worklist/report/trend/admin surface hierarchy | Hoàn tất |
| 7 | QA và documentation | Contract tests, lint, build, audit/system/coverage docs | Hoàn tất bằng automated QA |
| 8 | Browser visual regression | 320/768/1024/1440 screenshots + keyboard walkthrough | Chờ browser session khả dụng |

## 3. Implementation work packages

### WP-1 — Shared foundation

Acceptance:

- patient/doctor/admin dùng một `AppShell`;
- standard/wide có max-width thực và cùng left rail;
- PageHero có hierarchy và signature nhất quán;
- clinical surfaces không dùng transparent glass cho nội dung critical.

### WP-2 — Brand continuity

Acceptance:

- một code-native mark dùng ở landing, login, desktop rail và mobile sheet;
- không còn text `+` giả logo ở landing/footer;
- public/auth/product chia sẻ palette, material và typography.

### WP-3 — State coverage

Acceptance:

- route loading, error, global error và not found tồn tại;
- data empty/error/loading có shared visual grammar;
- error có recovery action khi khả thi;
- loading/error dùng ARIA role phù hợp.

### WP-4 — Forms và interactions

Acceptance:

- login, analysis, profile dùng shared controls;
- default control height ≥44px;
- login và analysis mode switch có tab semantics;
- reduced-motion không chạy page/hover translation.

### WP-5 — Clinical workspaces

Acceptance:

- dashboard có focal summary tiết chế, quick actions và recent rows cùng system;
- history giữ ba information zones;
- report giữ canonical clinical card/status/source/disclosure;
- trends giữ chart controls trong một surface;
- doctor review toolbar nằm trong flow và sticky;
- admin table/chart dùng cùng shell và card hierarchy.

## 4. Rollout / rollback

Thay đổi được tổ chức theo shared component và final CSS authority, nên rollback có thể thực hiện theo nhóm:

1. Route fallbacks.
2. Auth/public presentation.
3. Shared shell/brand.
4. Final UI-system CSS block.

Không cần migration dữ liệu hay backend rollback. Nếu phát hiện regression clinical presentation, ưu tiên rollback component presentation nhưng giữ nguyên `StatusIndicator` mapping và API flow.

## 5. QA gate

- `git diff --check`
- `npm test`
- `npm run lint`
- `npm run build`
- kiểm tra không có `window.alert` / `window.confirm` trong clinical workflows;
- kiểm tra tất cả canonical patient routes trỏ tới App Router page thật;
- browser keyboard/screenshot pass khi có session.

## 6. Follow-up không chặn release

- Tách dần các đoạn CSS legacy khỏi file `globals.css` 9k+ dòng sang component layers mà không đổi selector priority.
- Bổ sung Storybook/visual regression snapshots cho primitives và clinical states.
- Chuyển các raw buttons còn lại trong legacy worklist/history sang shared Button theo từng workflow có test.
- Kiểm chứng chart/table density bằng browser ở dữ liệu dài và màn 320px.
