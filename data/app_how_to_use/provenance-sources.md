```
feature: provenance-sources
role: patient
route: /patient/analysis,/patient/reports/{reportId},/patient/history/{reportId}
section: sources-disclosure,chat-sources
```

## Feature này dùng để làm gì?

Cho phép bệnh nhân xem **nguồn tham khảo** (link tới tài liệu y khoa) đứng sau mỗi lời giải thích của AI — cho từng chỉ số trong kết quả phân tích, và cho từng câu trả lời của trợ lý chat. Mục đích là minh bạch: người dùng biết thông tin AI đưa ra dựa trên nguồn nào.

## Người dùng tìm ở đâu?

- **Trong kết quả phân tích / lịch sử / chi tiết phiếu** (`/patient/analysis`, `/patient/reports/{reportId}`, `/patient/history/{reportId}`): mỗi thẻ chỉ số (`IndicatorResultCard`) có khối gấp lại (`<details>`) nhãn **"Nguồn tham khảo · N nguồn"**, bấm để **"Xem nguồn"** — mở danh sách link, mỗi link hiện tên miền nguồn (component `SourcesDisclosure.tsx`).
- **Trong khung chat trợ lý AI**: mỗi câu trả lời có khối gấp lại nhãn **"Nguồn tham khảo (N)"** (component `AssistantTurn.tsx`).

## Các bước sử dụng?

1. Tìm khối "Nguồn tham khảo" ngay dưới nội dung giải thích/chỉ số/câu trả lời.
2. Bấm vào để mở rộng danh sách nguồn.
3. Bấm vào từng link để mở nguồn tham khảo trong tab mới (`target="_blank"`).

## Điều kiện/giới hạn?

- Khối "Nguồn tham khảo" **chỉ hiện khi có ít nhất 1 nguồn** — nếu chỉ số/câu trả lời không có nguồn, khối này không hiển thị (`SourcesDisclosure` trả về `null` khi `sources.length === 0`).
- Chỉ hiển thị tên miền của nguồn (`sourceHostname`), không hiển thị toàn bộ URL trên giao diện.

## Không làm được gì?

- Đây không phải trang "quản lý nguồn" riêng — không có route độc lập, chỉ là chi tiết hiển thị lồng trong kết quả/chat.
- Không cho phép người dùng thêm, chỉnh sửa, hay đánh giá độ tin cậy của nguồn.
- Không đảm bảo mọi câu trả lời của trợ lý hoặc mọi chỉ số đều có nguồn — một số phản hồi có thể không kèm nguồn tham khảo nào.
