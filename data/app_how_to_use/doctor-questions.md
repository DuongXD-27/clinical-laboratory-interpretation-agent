```
feature: doctor-questions
role: patient,doctor
route: /patient/analysis,/patient/reports/{reportId},/doctor/reports/{reportId},/doctor/trend-reviews
section: questions-for-doctor,trend-review-queue
```

## Feature này dùng để làm gì?

Có hai luồng liên quan tới "hỏi bác sĩ" trong app, cả hai đã xác nhận trong code:

1. **Câu hỏi gợi ý cho bác sĩ** ("Questions for doctor"): sau khi phân tích, hệ thống gợi ý các câu hỏi bệnh nhân có thể mang đi hỏi bác sĩ. Bệnh nhân chọn những câu muốn hỏi, có thể sao chép/in ra; nếu đã lưu vào phiếu, bác sĩ mở phiếu trong hàng đợi sẽ thấy đúng các câu đã chọn và có thể trả lời trực tiếp trong hệ thống.
2. **Yêu cầu bác sĩ review biểu đồ xu hướng** (Trend Doctor Review): bệnh nhân có thể gửi yêu cầu để bác sĩ xem và nhận xét một biểu đồ xu hướng cụ thể; bác sĩ xử lý các yêu cầu này trong hàng đợi riêng.

## Người dùng tìm ở đâu?

Phía bệnh nhân:
- Panel "Câu hỏi mang đi hỏi bác sĩ" hiện dưới kết quả phân tích tại `/patient/analysis` và trên `/patient/reports/{reportId}` (component `QuestionsForDoctorPanel.tsx`).
- Panel gửi yêu cầu review xu hướng nằm trên `/patient/trends` (component `TrendDoctorReviewPanel.tsx`, dưới phần "Giải thích xu hướng").

Phía bác sĩ:
- Câu hỏi của bệnh nhân hiện trong sidebar khi bác sĩ mở một phiếu tại `/doctor/reports/{reportId}` (component `DoctorReportSidebar.tsx`, mục "Câu hỏi của bệnh nhân (N)").
- Yêu cầu review xu hướng nằm trong danh sách riêng tại `/doctor/trend-reviews`, chi tiết từng yêu cầu tại `/doctor/trend-reviews/{requestId}`.

## Các bước sử dụng?

Bệnh nhân — câu hỏi gợi ý:
1. Sau khi có kết quả phân tích, xem danh sách câu hỏi gợi ý.
2. Tick chọn những câu muốn hỏi thật sự.
3. Bấm **"Sao chép"** để copy các câu đã chọn, hoặc **"In"** để in ra.
4. Nếu đã đăng nhập (không phải guest) và phiếu đã lưu, lựa chọn được tự động lưu vào phiếu.

Bác sĩ — trả lời câu hỏi:
1. Mở phiếu cần xử lý trong Hàng đợi đánh giá (`/doctor`).
2. Trong sidebar, với mỗi câu hỏi chưa trả lời, gõ nội dung vào ô "Trả lời câu hỏi này cho bệnh nhân".
3. Bấm **"Lưu câu trả lời"**. Có thể bấm **"Sửa"** để chỉnh lại câu trả lời đã lưu.

Bác sĩ — review xu hướng:
1. Vào `/doctor/trend-reviews`, lọc theo trạng thái **"Đang chờ"** / **"Đã review"** / **"Tất cả"**.
2. Bấm vào một yêu cầu để mở trang chi tiết `/doctor/trend-reviews/{requestId}`: xem lại biểu đồ xu hướng + bảng dữ liệu từng mốc xét nghiệm (giá trị, ngày, đánh giá) + nhận xét xu hướng do AI sinh ra.
3. Chọn 1 trong 3 mức đánh giá: **"Xác nhận nhận xét AI phù hợp"**, **"Đính chính hoặc bổ sung nhận xét AI"**, hoặc **"Cần theo dõi hoặc trao đổi thêm"**, kèm ô nhận xét bắt buộc (không được để trống).
4. Bấm **"Gửi review"**. Sau khi đã gửi (trạng thái "Đã review"), form chuyển sang **chỉ đọc** — không sửa lại nhận xét đã gửi được nữa.

## Điều kiện/giới hạn?

- Nếu tất cả chỉ số trong phiếu đều bình thường, hệ thống **không tạo câu hỏi gợi ý** — hiển thị thông báo "Không có câu hỏi bổ sung được đề xuất cho phiếu này." (chủ đích: tránh gây lo lắng không cần thiết).
- Người dùng khách (guest, `reportId === null`): vẫn chọn được câu hỏi trong phiên nhưng **không được lưu lại** — có ghi chú: "Bạn đang dùng thử với tư cách khách nên lựa chọn này không được lưu lại."
- Trả lời câu hỏi chỉ dành cho tài khoản bác sĩ (`readOnly` kiểm soát quyền chỉnh sửa trong `DoctorReportSidebar`).

## Không làm được gì?

- Đây **không phải chat trực tiếp real-time với bác sĩ** — là cơ chế hỏi-đáp bất đồng bộ qua từng phiếu/yêu cầu cụ thể, không phải khung chat giữa bệnh nhân và bác sĩ.
- Guest không thể lưu câu hỏi đã chọn để bác sĩ xem sau — chỉ tài khoản bệnh nhân đã đăng ký mới có tính năng này.
- Không có tính năng đặt lịch hẹn khám bác sĩ trong luồng này (chưa tìm thấy trong repo).
