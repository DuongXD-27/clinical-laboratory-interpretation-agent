```
feature: chat-assistant
role: patient
route: /patient/*
section: assistant-widget
```

## Feature này dùng để làm gì?

Trợ lý AI dạng chat nổi (floating widget), giúp bệnh nhân đặt câu hỏi và nhận trả lời ngay trong lúc dùng app — bao gồm cả câu hỏi y khoa lẫn câu hỏi về cách dùng app. Đây chính là nơi các câu hỏi "Tải phiếu xét nghiệm ở đâu?", "Xem lịch sử ở đâu?" nên được trả lời.

## Người dùng tìm ở đâu?

- Nút nổi **"Hỏi trợ lý"** (icon tin nhắn) xuất hiện ở góc màn hình trên **mọi trang trong khu vực bệnh nhân** (`/patient`, `/patient/analysis`, `/patient/history`, `/patient/trends`, `/patient/profile`, `/patient/reports/{id}`) — vì widget được mount trong `PatientShell`, lớp bao ngoài dùng chung cho toàn bộ layout `/patient/*`.
- Bấm nút để mở bảng chat (`ChatPanel`).

## Các bước sử dụng?

1. Bấm nút "Hỏi trợ lý" ở góc màn hình để mở bảng chat.
2. Lần đầu có thể cần xác nhận màn hình giới thiệu (onboarding) trước khi gõ tin nhắn.
3. Gõ câu hỏi vào ô soạn tin, gửi đi.
4. Đọc câu trả lời; nếu có, mở khối "Nguồn tham khảo (N)" để xem nguồn (xem `provenance-sources.md`).
5. Một số câu trả lời có nút hành động gợi ý (suggested action) — bấm để điều hướng thẳng tới trang liên quan (ví dụ tới trang Phân tích, Lịch sử, hoặc Xu hướng).
6. Có thể đóng bảng chat bằng phím Esc hoặc nút đóng.

## Điều kiện/giới hạn?

- Widget nhận biết ngữ cảnh trang hiện tại (`uiContextForPath`): biết người dùng đang ở "dashboard", "analysis", "history" hay "trend", và với trang xu hướng còn nhận diện chỉ số đang xem (`candidate_analyte`) để trả lời sát ngữ cảnh hơn.
- Cần đăng nhập hợp lệ; nếu phiên hết hạn, trợ lý sẽ đưa người dùng về trang đăng nhập.
- Đã xác nhận widget này **chỉ được xác nhận là có mặt trong `PatientShell`** (khu vực bệnh nhân) — chưa tìm thấy bằng chứng nó cũng xuất hiện trong `DoctorShell` (khu vực bác sĩ).

## Không làm được gì?

- Không xác nhận được rằng bác sĩ có cùng trợ lý chat này — nếu người dùng là bác sĩ hỏi về "trợ lý AI", không nên khẳng định tính năng này tồn tại y hệt ở khu vực bác sĩ (chưa kiểm chứng được `AssistantWidget` trong `DoctorShell.tsx`).
- Trợ lý không thay thế được các trang chuyên biệt (Analysis, History, Trends...) — nó có thể trả lời và gợi ý điều hướng, nhưng thao tác thực (tải ảnh, xem biểu đồ...) vẫn cần thực hiện trên trang tương ứng.
- Không đưa ra chẩn đoán y khoa thay bác sĩ; các câu hỏi điều trị vẫn tuân theo cảnh báo an toàn của hệ thống (ngoài phạm vi Phase 1 — thuộc retrieval/routing của Phase 2).
