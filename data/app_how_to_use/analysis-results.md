```
feature: analysis-results
role: patient
route: /patient/analysis,/patient/reports/{reportId}
section: result-view
```

## Feature này dùng để làm gì?

Sau khi nhập tay hoặc xác nhận OCR xong, hệ thống hiển thị kết quả phân tích: từng chỉ số kèm đánh giá, cảnh báo nếu có giá trị nguy kịch, tóm tắt tổng quan, và danh sách câu hỏi gợi ý để mang đi hỏi bác sĩ.

## Người dùng tìm ở đâu?

- Xuất hiện ngay trên trang `/patient/analysis` sau khi bấm "Phân tích kết quả" (component `AnalysisResultView`).
- Có thể mở lại chi tiết đầy đủ tại `/patient/reports/{reportId}` bằng nút **"Mở trang chi tiết"**.
- Nếu phiếu bị trùng với phiếu đã lưu trước đó, hệ thống báo "Kết quả xét nghiệm này có vẻ đã được lưu trước đó" kèm link "Xem kết quả đã lưu".

## Các bước sử dụng?

1. Sau khi phân tích xong, xem tiêu đề "Kết quả xét nghiệm" và số chỉ số đã phân tích.
2. Nếu có cảnh báo nguy kịch, biểu ngữ đỏ "Cảnh báo sức khỏe nghiêm trọng" hiện ra — xem chi tiết ở `critical-alerts.md`.
3. Đọc phần tóm tắt (nếu có) và từng thẻ chỉ số (giá trị, đơn vị, đánh giá, nguồn tham khảo — xem `provenance-sources.md`).
4. Với các chỉ số hệ thống chưa hỗ trợ diễn giải, mục "Chưa được hệ thống hỗ trợ diễn giải" liệt kê tên các chỉ số đó.
5. Đọc "Lưu ý quan trọng" ở cuối trang: "Kết quả do AI tạo ra chỉ nhằm mục đích tham khảo, không thay thế chẩn đoán y khoa."
6. Có thể bấm "Mở trang chi tiết" (nếu đã lưu) hoặc "Phân tích phiếu khác" để làm lại.
7. Bên dưới là danh sách "Câu hỏi mang đi hỏi bác sĩ" gợi ý (xem `doctor-questions.md`).
8. Tại trang chi tiết (`/patient/reports/{reportId}`), có thể bấm nút **"Xóa phiếu"** để xóa hẳn phiếu này — hệ thống hỏi xác nhận trước, xóa xong quay về trang Lịch sử. Thao tác không thể hoàn tác (xem thêm `history.md`).

## Điều kiện/giới hạn?

- Kết quả chỉ được lưu vào lịch sử nếu người dùng đăng nhập với vai trò patient (không phải guest) — thông báo "Kết quả đã được lưu vào lịch sử xét nghiệm." kèm link "Xem chi tiết".
- Một số chỉ số nằm ngoài phạm vi hỗ trợ diễn giải của hệ thống ("out_of_scope_indicators") — được liệt kê riêng, không có đánh giá đi kèm.
- Nếu có cảnh báo nguy kịch chưa được xác nhận (chưa bấm "Tôi sẽ liên hệ bác sĩ"), phần câu hỏi gợi ý cho bác sĩ tạm thời bị ẩn cho tới khi xác nhận.

## Không làm được gì?

- Không đưa ra chẩn đoán y khoa — chỉ mang tính tham khảo, theo đúng nội dung "Lưu ý quan trọng" hiển thị trên trang.
- Không tự động đặt lịch khám hay liên hệ bác sĩ thay người dùng — nút "Tôi sẽ liên hệ bác sĩ" chỉ là xác nhận đã đọc cảnh báo, không gửi yêu cầu đi đâu cả.
- Không chỉnh sửa được kết quả đã phân tích tại đây — muốn thay đổi phải bấm "Phân tích phiếu khác" và nhập lại từ đầu (xóa rồi phân tích lại cũng được, nhưng không có "sửa tại chỗ").
