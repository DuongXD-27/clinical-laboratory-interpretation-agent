# LumiLab Chat UI Audit

## Phạm vi

Audit bao phủ launcher, panel, header, onboarding, welcome state, transcript,
message presentation, progress/loading, composer, history và sources của trợ lý
bệnh nhân. Logic y khoa, guardrail, RBAC và API payload không nằm trong phạm vi
thay đổi.

## 1. Current issues

### Information architecture

- History từng được chèn ngay dưới header trong cùng màn conversation. Hai tác
  vụ “đọc cuộc trò chuyện hiện tại” và “chọn một thread đã lưu” cạnh tranh cùng
  một không gian.
- Hook từng chọn conversation đã lưu gần nhất và gọi API transcript ngay khi
  mount. Vì vậy một thread cũ bị trình bày như current session dù người dùng
  chưa chủ động chọn.
- New Chat, History và Close đều là icon-only action cùng cấp; hierarchy và ý
  nghĩa không đủ rõ.

### Visual hierarchy

- Launcher có treatment giống nút hành động nổi thông thường, chưa truyền đạt
  được identity của một clinical AI assistant.
- Header thiếu cấu trúc brand → status/context → task actions.
- Welcome copy, prompts và composer có mật độ/shape chưa tạo được nhịp điệu
  “quiet clinical”.
- Assistant response gần như hòa vào nền, thiếu avatar/surface để mắt nhận biết
  điểm bắt đầu của một lượt trả lời.

### Conversation readability

- Response dài được trình bày chủ yếu như một khối prose, khó quét mắt.
- User/assistant alignment có khác nhau nhưng assistant response chưa có visual
  anchor rõ.
- Loading/progress là text và dot đơn giản, chưa tạo cảm giác hệ thống đang xử
  lý có chủ đích.
- Source disclosure đúng về an toàn URL nhưng hierarchy giữa source label,
  hostname và phần nội dung chính còn yếu.

### Interaction and accessibility

- History mở như một vùng chen ngang, không phải secondary route rõ ràng.
- Header icon-only buộc người dùng đoán action; trạng thái active của History
  chưa đủ rõ.
- Focus trap/Escape/focus restoration đã có, nhưng cần giữ nguyên sau refactor.
- Composer đã hỗ trợ Enter/Shift+Enter và IME, nhưng treatment vẫn giống form
  hơn input surface của AI assistant.

### Structural maintainability

- `ChatPanel.tsx` trước đây sở hữu header, history, empty state, transcript và
  composer trong một component lớn.
- Sources nằm trong `AssistantTurn`, starter prompts nằm trong `ChatPanel`; khó
  thay đổi từng vùng mà không ảnh hưởng vùng khác.
- Pure test cũ còn mã hóa hành vi tự mở conversation gần nhất, trái với UX mới.

## 2. Safety observations

- Critical alert chỉ được render từ alert có thẩm quyền; không suy diễn
  `HIGH/LOW` thành `CRITICAL`.
- Suggested action vẫn đi qua allowlist và route sanitizer.
- Source vẫn chỉ nhận HTTP(S) URL đã được lọc.
- Guest mode không gọi conversation persistence API.
- Không có endpoint xóa conversation và summary API không trả message preview.
  Audit không xem việc tự dựng preview hoặc nút xóa giả là giải pháp hợp lệ.

## 3. Priority

1. Loại bỏ auto-open transcript và tách History khỏi current conversation.
2. Thiết lập lại hierarchy của launcher/header/welcome/composer.
3. Cải thiện scanability của response, source và loading state.
4. Tách component theo trách nhiệm, bổ sung regression test.
5. Xác minh responsive, keyboard, light/dark và reduced motion.
