# LumiLab Chat UI Refactor Plan

## 1. Information architecture

Panel có hai view loại trừ nhau:

- `conversation`: onboarding hoặc welcome/current thread, transcript và
  composer.
- `history`: danh sách thread đã lưu; không render transcript hoặc composer.

Luồng mặc định:

1. Widget mount chỉ tải conversation metadata.
2. Mở panel vào clean conversation view; không chọn và không tải transcript.
3. Gửi câu đầu tiên tạo một conversation mới qua contract `POST
   /conversations`, sau đó stream message với id tường minh.
4. History chỉ tải transcript sau khi người dùng chọn một thread.
5. New Chat dừng request đang chạy, tạo conversation mới có context rỗng và
   trả về conversation view.

## 2. Component architecture

```text
AssistantWidget
└── ChatPanel
    ├── ChatHeader
    ├── conversation view
    │   ├── onboarding safety gate
    │   ├── ChatEmptyState | message scroller
    │   │   └── AssistantTurn
    │   │       └── ChatSources
    │   └── ChatComposer
    └── ChatThreadList
```

- `AssistantWidget`: page context, open/close, focus/inert behavior, navigation.
- `useOrchestratorChat`: current thread state, saved metadata, transcript fetch,
  request lifecycle và explicit New Chat creation.
- `ChatPanel`: view state và composition, không sở hữu composer draft.
- `ChatHeader`: brand/status/context cùng New Chat, History, Close.
- `ChatThreadList`: loading/error/empty/grouped thread states.
- `ChatEmptyState`: welcome copy và bốn contextual starter prompts.
- `ChatComposer`: draft, IME-safe keyboard behavior, send/stop.
- `AssistantTurn`: structured medical payload, critical/warning hierarchy,
  suggested actions.
- `ChatSources`: progressive source disclosure.

## 3. Visual direction

- Nền mineral/white translucent, muted teal cho identity và interaction.
- Border mảnh, shadow mềm, radius nhất quán với LumiLab UI system.
- Brand mark code-native thay icon support chat generic.
- Header action có label trên desktop, icon compact trên mobile.
- User bubble teal đậm align phải; assistant surface sáng, outline nhẹ, avatar
  align trái.
- Prompt grid 2 cột desktop, 1 cột mobile; mỗi prompt là action nhỏ, không phải
  marketing card.
- Composer là một input surface thống nhất, tối đa sáu dòng.
- Loading dùng shimmer restrained; reduced-motion tắt animation.

## 4. Interaction changes

- Không đọc localStorage conversation id và không auto-select newest thread.
- History là view riêng và có trạng thái pressed rõ trên action.
- Chọn thread mới gọi transcript endpoint và quay về conversation view.
- New Chat luôn khả dụng, kể cả guest; guest vẫn không persistence.
- Context của page/report chỉ xuất hiện như subtitle/chip nhẹ.
- Focus trở lại launcher khi đóng; mobile giữ dialog semantics, inert siblings,
  focus trap và safe-area padding.

## 5. Explicit non-goals

- Không đổi medical rules, reference ranges, thresholds, units hoặc status
  semantics.
- Không đổi RBAC/patient ownership.
- Không thêm delete action vì backend chưa có endpoint.
- Không hiển thị fake message preview. Với API summary hiện tại, secondary copy
  dùng nhãn trung thực “Tiếp tục hội thoại đã lưu”; preview thật cần một thay
  đổi API được duyệt riêng.
