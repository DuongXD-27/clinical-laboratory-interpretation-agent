# LumiLab Motion UI Inventory

Status: implementation inventory created before the global motion refactor.

## Safety boundary

- Motion may explain hierarchy, continuity, focus, and state change. It must not communicate medical severity.
- `NORMAL`, `LOW`, `HIGH`, `CRITICAL`, `UNKNOWN`, `NEED_REVIEW`, OCR confidence, verification state, numerical values, ranges, and thresholds remain visually static.
- Reference-range bands, threshold lines, critical markers, emergency warnings, and provenance content never pulse, blink, shimmer, glow, bounce, or morph.
- Existing API contracts, auth/RBAC, patient access rules, and medical semantics are out of scope.
- Shell chrome remains mounted and stable. Route motion is limited to the changing workspace.

## Motion levels and tokens

| Level | Duration | Intended use |
|---|---:|---|
| 0 — static clinical | 0 ms | Clinical values, status, warnings, thresholds, ranges, verification and OCR semantics |
| 1 — micro | 100–160 ms | Hover, press, focus, icon and active-indicator settle |
| 2 — component | 160–240 ms | Tabs, filters, validation, disclosure, new chat messages |
| 3 — surface | 200–300 ms | Dialogs, drawers, empty/loading/result surface resolution |
| 4 — LumiLens signature | 280–420 ms | Patient route resolution, report/detail continuity, chat portal |

Canonical durations: `instant 100`, `fast 140`, `base 220`, `surface 280`, `signature 360`; canonical curves: `standard`, `enter`, `exit`.

## Route inventory

| Route | Shell / surfaces | Motion variant | Selective continuity | Reduced-motion result | QA status |
|---|---|---|---|---|---|
| `/` | Landing nav, hero, demo result card, trust band, feature/process/doctor/safety/CTA sections | Public `LumiLens`: one calm hero resolve; sections resolve by hierarchy, not card-by-card spectacle | Landing CTA → `/login` uses a restrained route transition only | Immediate content with opacity-only state changes | Pending |
| `/privacy` | Public document header, policy sections, back action | Public-document: short in-place resolve; long-form text stays stable | Back to landing/login uses route transition only | Immediate document | Pending |
| `/login` | Stable auth shell, intro/trust rail, login/register tabs, Google sign-in, fields, validation | Auth: shell/card static; only current form content crossfades/glides 4 px in 180–220 ms | Login/register is local tab continuity; successful auth uses destination route resolve | Form swaps instantly or opacity-only; no spatial validation motion | Pending |
| `/patient` | Patient shell, dashboard header, latest report, needs-attention, quick actions, recent reports, empty/loading/error states | Patient signature 340–360 ms with hierarchical header → primary → supporting surface resolution | Recent/latest report card → report detail; quick action → analysis/history/trends | No sweep, scale or stagger; content appears immediately/opacity-only | Pending |
| `/patient/analysis` | Manual/OCR tabs, upload dropzone, OCR stepper/review, metric selector/input rows, result view, critical warning, disclaimer | Patient signature shell; component transitions for tabs/upload/review/results | Analysis result → saved report detail where a link exists | OCR/verification and warning semantics remain static; shimmer disabled | Pending |
| `/patient/history` | Header, account lookup controls, filters, skeleton/empty/error, paginated report rows/cards, clinical notes/questions | Patient signature entry; capped list resolve on initial load/filter only | History row/card → `/patient/history/[reportId]` or canonical report detail | No list stagger or spatial row entrance; skeleton becomes static | Pending |
| `/patient/history/[reportId]` | Historical report detail wrapper and report content | Patient detail signature 340–380 ms; primary report first, supporting sections second | History source item → detail; back → history | In-place/opacity-only detail reveal | Pending |
| `/patient/reports/[reportId]` | Report header, summary, indicator cards, questions, sources, disclaimer, delete confirmation | Richest patient `LumiLens` detail resolution 360 ms; no animation on clinical indicator status | Report card → detail; analyte affordance → trends when available | No spatial/scale/stagger; all clinical content immediately legible | Pending |
| `/patient/trends` | Header, analyte/group controls, chips, chart/heatmap, explanation, doctor-review panels, loading/error/empty | Patient signature entry; control crossfade; initial chart plot reveal only, capped at 350–500 ms | Analyte/report affordance → trend context | Chart line/draw disabled; threshold/reference/critical layers always static | Pending |
| `/patient/profile` | Header, profile identity, fields, explanation-style options, loading/empty/error | Patient standard 280–320 ms; stable form geometry and short selection settle | Sidebar → profile route resolve | Fields/options change instantly or opacity-only | Pending |
| `/doctor` | Doctor shell, operational header, queue overview, toolbar, tabs, initial queue rows, loading/empty/error | Doctor-lite 280–300 ms; capped initial rows, filter crossfade; row hover ≤1 px | Queue row → `/doctor/reports/[reportId]` | No stagger/spatial rows; stable queue with opacity-only replacement | Pending |
| `/doctor/reports/[reportId]` | Report header/progress, findings, report sections, sticky supporting sidebar, dialogs/states | Doctor detail 300–320 ms; primary column before supporting sidebar | Queue row → report detail; back → queue | Immediate/opacity-only columns; semantic and warning elements static | Pending |
| `/doctor/trend-reviews` | Header, status tabs, skeleton/empty/error, review queue cards | Doctor-lite 280 ms; local filter crossfade and capped initial queue resolve | Review row/card → request detail | No stagger/slide; opacity-only filter replacement | Pending |
| `/doctor/trend-reviews/[requestId]` | Header, trend chart, point table, patient/request card, professional note form | Doctor detail 300 ms; primary evidence before supporting action rail | Review item → request detail; back → review queue | Chart draw and spatial sequencing disabled | Pending |
| `/admin` | Admin shell, KPI strip, SLO/cost panels, charts, trace filters/table, loading/error | Admin restrained 240–280 ms; stable metrics and charts; capped trace-row resolve | Trace row/request-id → trace detail; metric continuity only if a stable source exists | Immediate metrics/table; no chart drawing/stagger | Pending |
| `/admin/traces/[requestId]` | Request header, stats, timing waterfall/list, metadata and diagnostic sections | Admin detail 260–280 ms; stable diagnostic geometry | Trace row → detail; back → trace table | In-place/opacity-only detail | Pending |

### System routes and boundaries

| Surface | Motion | Reduced-motion result | QA status |
|---|---|---|---|
| Root `loading.tsx` and shell loading states | Static skeleton geometry; optional restrained shimmer only | Shimmer disabled | Pending |
| `error.tsx` / `global-error.tsx` | One surface resolve; retry press feedback | Immediate surface | Pending |
| `not-found.tsx` | One public/system surface resolve | Immediate surface | Pending |
| Navigation sidebars/topbars/mobile sheets | Shell stays static; active rail settles in 140 ms; mobile sheet uses small edge motion | Instant active state and sheet placement | Pending |

## Shared component inventory

| Component / pattern | Current role | Target motion | Static / protected content | QA status |
|---|---|---|---|---|
| `RouteTransition` | Keys changing route content inside each authenticated shell | Progressive native View Transition where supported plus CSS fallback; role-specific variant | Sidebars, topbars, floating launcher, ambient shell | Pending |
| Public/auth route wrappers | Root, privacy, login and system screens have no authenticated shell wrapper | Shared public/auth/system route entrance classes | Document text and auth card geometry | Pending |
| `AppShell` / sidebars / topbars | Persistent application frame | No remount animation; active item/background settles only | Identity, page labels, session affordances | Pending |
| Page headers / hero blocks | Establish current page and actions | First hierarchy layer, 0 ms child delay | Titles and descriptions do not morph | Pending |
| Cards / queue rows / report rows | Primary navigation and information surfaces | Hover ≤1 px, fast border/shadow; capped initial resolve | Medical values and severity decorations | Pending |
| Tabs / segmented controls / filters | Local content state | Trigger 140 ms; pane opacity + 4 px, 180–220 ms | Counts and selected values remain dimensionally stable | Pending |
| Buttons / icon buttons / links | Actions and navigation | Press `scale(.985)` for 80–120 ms; no bounce | Destructive/emergency wording remains stable | Pending |
| Inputs / textareas / selects | Data entry | Focus border/ring 140 ms; validation offset 2–3 px maximum | Value text and units | Pending |
| Dialogs / confirm dialog / lightbox | Modal confirmation and media | Backdrop 140–180 ms; surface 180–220 ms, opacity + `.98` scale + 4 px | Warning/confirmation semantics | Pending |
| Mobile sheets / drawers | Responsive navigation / supporting content | Small edge translation, 200–280 ms | Content hierarchy | Pending |
| Skeleton / spinner / async states | Waiting feedback | Restrained shimmer/spinner while waiting only | Never applied to clinical status | Pending |
| Trend chart / heatmap / admin charts | Analytical plots | Initial plot fade/line reveal ≤500 ms; no replay on hover/filter noise | Reference bands, thresholds, critical markers, values | Pending |
| `SystemState` / `DoctorStatePanel` | Loading, empty, error states | Single surface resolution | Error wording and status meaning | Pending |

## Chat inventory — signature portal

| Surface | Target motion | Constraints | Reduced-motion result | QA status |
|---|---|---|---|---|
| Launcher | Stable floating anchor; fast hover/press | No continuous glow/pulse | Static anchor | Pending |
| Launcher → panel | `LumiLens` portal, bottom-right transform origin, opacity + 8 px + `.96` scale, 320–360 ms | No bounce; recurring near-white/teal resolving edge occurs only during open | Panel appears without scale/translation/sweep | Pending |
| Panel → launcher | Opacity + 6 px + `.97` scale, 180–220 ms exit | Lifecycle completes on animation end; timer is safety fallback only | Immediate close | Pending |
| Conversation ↔ history | Internal content only: opacity + 6 px horizontal, 180–220 ms | Frame, header and composer stay fixed | Instant/opacity-only content swap | Pending |
| New message | Only the newly appended turn resolves with opacity + 4 px, ~200 ms | Existing transcript never replays | Immediate message | Pending |
| Thinking indicator | Quiet temporary three-dot state | No association with severity; stops when response resolves | Static dots | Pending |
| Composer | Stable input geometry; 140 ms focus/send/stop feedback | No layout shift during request state | Instant controls | Pending |
| Onboarding/consent and history loading/error/empty | Component/surface resolve | Explicit accessible state; no decorative looping | Immediate state | Pending |

## LumiLens edge and ambient background

- The resolving edge is a thin, nearly white teal refraction line. It may appear once during route/detail/chat portal entry and must not loop.
- Ambient gradients remain effectively static. A route transition may shift opacity/position subtly without animating blur or a continuous gradient.
- No large blur animation, canvas, WebGL, particle field, neon glow, elastic easing, or spring overshoot.
- Implementation should stay on `transform` and `opacity` for moving surfaces; color/border/shadow transitions are allowed for micro feedback.

## Required verification matrix

- Routes: every row above, including loading, error, empty, success, dialog/drawer and chat states that can be reached with available data.
- Viewports: `375x667`, `390x844`, `430x932`, `768x1024`, `1024x768`, `1366x768`, `1440x900`, `1920x1080`.
- Interaction: rapid route changes, rapid tab/filter changes, repeated chat open/close, history/conversation switching, dialog open/close, Escape, focus restoration, mobile sheet navigation.
- Accessibility: keyboard focus, semantic status with motion disabled, `prefers-reduced-motion: reduce`, no content loss, no motion-only meaning.
- Performance: no layout shift, no repeated chart/list replay, no large animated backdrop blur, and no permanent `will-change` on large surfaces.

