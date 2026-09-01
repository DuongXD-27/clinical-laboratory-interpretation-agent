# LumiLab Chat UI Verification

## 1. What changed

- Launcher mới dùng LumiLab brand mark, compact status và clinical glass
  treatment.
- Header mới có hierarchy brand → status/context → New Chat/History/Close.
- Welcome state có copy ngắn, clinical disclaimer và bốn starter prompts.
- User/assistant messages có alignment, avatar, surface, typography và spacing
  riêng; response dài tách paragraph để dễ scan.
- Progress/transcript loading dùng shimmer; error và empty state dùng shared
  system-state grammar.
- Composer mới hỗ trợ 1–6 dòng, focus state, IME-safe Enter, Shift+Enter,
  send/stop và keyboard hint.
- History là view độc lập, group `Hôm nay` / `Trước đó`, có title, secondary
  description và timestamp.
- Sources chuyển thành component riêng với disclosure, public label và
  hostname.
- Light/dark, mobile safe areas và reduced motion có rule tường minh.

## 2. Previous-history auto-open

Đã loại bỏ.

- Mount chỉ gọi `listConversations()` để lấy metadata/onboarding status.
- Không còn localStorage conversation id hoặc `pickInitialConversation`.
- `getConversation()` chỉ chạy từ thao tác chọn một item trong History.
- Clean session gửi message bằng một id từ `POST /conversations`; không dùng
  nhánh thiếu id của backend vì nhánh tương thích đó sẽ nối vào thread gần nhất.

## 3. Safety and API verification

- Không thay API schema, backend route, auth hoặc patient access rule.
- Không thay cách phân loại NORMAL / LOW / HIGH / CRITICAL.
- Critical presentation vẫn chỉ dùng `authoritativeCriticalAlerts()`.
- Suggested actions vẫn qua `sanitizeSuggestedAction()`.
- Source vẫn qua `safeHttpSources()`.
- Guest vẫn không gọi conversation persistence endpoints.

## 4. Automated verification

Chạy tại `frontend/`:

| Command | Result |
| --- | --- |
| `npm test` | PASS — 125/125 |
| `npm run lint` | PASS — 0 errors, 0 warnings |
| `npm run build` | PASS — Next.js production build, TypeScript và 14 static pages hoàn tất |

Regression coverage mới xác nhận:

- widget mount có thể tải metadata nhưng không auto-open transcript;
- controller không dùng `localStorage` hoặc initial-conversation picker;
- History và conversation là hai view riêng;
- New Chat dùng explicit conversation creation contract;
- stop/retry, role log, IME, critical alert, safe sources, responsive và reduced
  motion tiếp tục được bảo vệ.

## 5. Visual and responsive QA

Static/component QA đã kiểm tra các breakpoint 375, 430, 768, 1024 và desktop
qua CSS contract:

- dưới 768px panel full-height `100dvh`, header actions compact, composer dùng
  bottom safe area;
- dưới 430px prompts chuyển một cột và thread timestamp xuống hàng;
- desktop giữ panel tối đa 472px, line length của assistant response được giới
  hạn;
- touch targets chính đạt tối thiểu 40–44px;
- focus-visible, Escape, focus restoration và mobile focus trap được giữ;
- reduced motion vô hiệu shimmer và transform.

In-app browser không có browser instance khả dụng trong phiên chạy này, nên
không thể chụp screenshot/interaction QA thực tế. Đây là giới hạn môi trường,
không được ghi nhận như một visual pass. Cần smoke-test đăng nhập thật ở 375px,
768px và desktop khi browser instance được kết nối.

## 6. Known constraints

- Conversation summary không có message preview; UI dùng secondary copy trung
  thực thay vì dựng dữ liệu giả.
- Không có delete endpoint nên không hiển thị delete action.
- Browser visual smoke test còn pending như ghi ở trên; automated build và
  source-level responsive/accessibility contract đã pass.
