# LumiLab — LumiLens Signature Motion System

## 1. Philosophy & Visual Direction

**Quiet Clinical Motion / Premium Clinical Intelligence**

LumiLab motion is engineered, not decorated. It provides spatial continuity, calm feedback, and subtle depth across the medical workspace without ever distracting healthcare professionals or patients from clinical data.

### Core Principles
- **Quiet & Restrained**: No playful bouncing, no elastic overshoot, no neon glows.
- **Spatial & Continuous**: Transitions originate from logical anchors (e.g. AI chatbot emerging from its launcher).
- **Zero Layout Shift**: Shells, sidebars, topbars, and composer fields remain rock-solid.
- **Medical Semantics Protection**: Clinical severity (NORMAL, LOW, HIGH, CRITICAL, UNKNOWN) is conveyed strictly through typography, icons, wording, and semantic color — **never** through continuous animation or blinking.

---

## 2. Motion Hierarchy & Design Tokens

### 2.1 Canonical Durations

| Token | Duration | Usage |
|---|---|---|
| `--motion-instant` | `100ms` | Press acknowledgement and instant state settle. |
| `--motion-fast` | `140ms` | Micro-interactions, button active states, focus rings, hover elevation. |
| `--motion-base` | `220ms` | Tab switching, list item entrance, chat messages. |
| `--motion-surface` | `280ms` | Dialog, drawer, doctor route, and surface resolution. |
| `--motion-signature` | `360ms` | Patient route, shared-detail continuity, and LumiLens portal motion. |
| `--motion-page` | `280ms` | Compatibility alias for existing route surfaces. |
| `--motion-slow` | `320ms` | Major surface transitions, large drawer entrances. |
| `--motion-chat-open` | `360ms` | AI Assistant LumiLens spatial panel opening. |
| `--motion-chat-close` | `200ms` | AI Assistant panel closing (faster than enter). |

### 2.2 Easing Curves

| Token | Curve | Purpose |
|---|---|---|
| `--ease-standard` | `cubic-bezier(0.2, 0.8, 0.2, 1)` | Balanced default for two-way state transitions. |
| `--ease-enter` | `cubic-bezier(0.16, 1, 0.3, 1)` | Decelerating curve for arriving elements (pages, dialogs, panels). |
| `--ease-exit` | `cubic-bezier(0.4, 0, 1, 1)` | Accelerating curve for departing elements. |

### 2.3 Shorthand Transition Variables

```css
:root {
  --transition-fast: var(--motion-fast) var(--ease-standard);
  --transition-base: var(--motion-base) var(--ease-standard);
  --transition-slow: var(--motion-slow) var(--ease-standard);
  --transition-enter: var(--motion-base) var(--ease-enter);
  --transition-exit: var(--motion-fast) var(--ease-exit);
}
```

---

## 3. Clinical Safety Boundary (VMEC-05)

1. **No Continuous Severity Animation**:
   - Status indicators (CRITICAL, ABNORMAL, NORMAL, UNKNOWN) must **never** pulse, shimmer, or blink.
   - Warning blocks must remain completely stable to avoid cognitive fatigue and misinterpretation.
2. **No Animation-Only Meaning**:
   - Every system state must be fully legible and understandable with motion completely disabled.
3. **No Large-Area Blurs or Heavy GPU Filters**:
   - Large blur areas on desktop pages degrade rendering performance on clinical workstations. Transitions animate strictly `opacity` and `transform`.

---

## 4. Component Transition Specifications

### 4.1 Route & Workspace Transitions
- **AppShell Persistence**: `PatientShell`, `DoctorShell`, and `AdminShell` persist sidebars, topbars, and brand atmospheres between navigations.
- **RouteTransition Primitive**: Only the main content workspace is wrapped with `RouteTransition` keyed by `pathname`. React View Transitions are progressive enhancement; unsupported browsers use the CSS fallback.
- **Entrance Animation**:
  - `opacity`: `0 -> 1`
  - `transform`: `translateY(10px) -> translateY(0)`
  - Patient: `360ms`; doctor: `280ms`; admin: `220ms`.
- **No Horizontal Desktop Slides**: Desktop views remain strictly vertical/in-place.

### 4.2 Tab & Filter Transitions
- **Triggers**: Smooth `140ms` color, background, and border transition.
- **Panels**: Crossfade + subtle `4px` vertical glide (`180–220ms`).
- **Tab Counts**: Numerical badges remain dimensionally stable without layout reflow.

### 4.3 Lists & Queues
- **Stagger Interval**: `15ms` per item, capped at maximum 8 items (`calc(min(var(--stagger-index, 0), 8) * 15ms)`) so the final delay never exceeds `120ms`.
- **Row Entrance**: `opacity: 0 -> 1`, `translateY: 5px -> 0`.
- **No Scroll Replay**: Stagger is only applied upon initial load/filter change, not replayed during normal user scrolling.

### 4.4 Card Hover
- **Restrained Elevation**: `transform: translateY(-1px)` with slight elevation shadow and border tint.
- **Duration**: `140ms` (`--motion-fast`).
- **No 3D Tilts or Continuous Glows**.

### 4.5 AI Chatbot — Signature Motion
- **Deterministic State Machine**:
  ```ts
  type AssistantVisibility = "closed" | "opening" | "open" | "closing";
  ```
- **Spatial Opening**:
  - `transform-origin`: `calc(100% - 24px) calc(100% - 24px)` (bottom-right launcher anchor).
  - Starts: `opacity: 0`, `transform: translateY(8px) scale(0.96)`.
  - Ends: `opacity: 1`, `transform: translateY(0) scale(1)`.
  - Duration: `360ms` (`--ease-enter`).
- **Closing**:
  - Accelerating exit: `opacity: 1 -> 0`, `transform: translateY(6px) scale(0.96)`.
  - Duration: `200ms` (`--ease-exit`).
  - Driven by `onAnimationEnd` lifecycle with safety timer fallback.
- **Internal View Transitions**:
  - `Conversation -> History`: `translateX(6px) -> 0` with crossfade.
  - `History -> Conversation`: `translateX(-6px) -> 0` with crossfade.
  - Chat panel frame and composer remain firmly stationary.
- **Messages & Thinking**:
  - New message entrance: `opacity: 0 -> 1`, `translateY(4px) -> 0` in `200ms`.
  - Thinking state: Compact 3-dot pulse (`1.4s` smooth loop).

### 4.6 Dialogs & Modals
- **Backdrop**: Fade in `140–180ms`.
- **Surface**: Scale `0.98 -> 1` and `translateY(4px) -> 0` in `180–220ms`.

---

## 5. Accessibility & Reduced Motion

Global support via `@media (prefers-reduced-motion: reduce)`:
- All spatial transforms (`translateY`, `translateX`, `scale`) are disabled (`transform: none !important`).
- Stagger delays are zeroed (`animation-delay: 0ms !important`).
- Thinking dots pulse is disabled.
- Transitions and animations resolve immediately (`0.01ms`), ensuring full functionality, accessibility, and zero vestibular discomfort.

---

## 6. Architecture & Maintenance Rules

1. When adding a new animated component, import tokens from `src/lib/motion.ts` and apply CSS variables from `globals.css`.
2. Do not introduce standalone animation timing without semantic justification.
3. Keep layout math and animations decoupled.
