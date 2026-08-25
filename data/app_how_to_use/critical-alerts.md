```
feature: critical-alerts
role: patient
route: /patient/analysis,/patient,/patient/trends
section: critical-banner,needs-attention
```

## Feature này dùng để làm gì?

Cảnh báo bệnh nhân khi một chỉ số xét nghiệm đạt mức **nguy kịch** (critical) hoặc chỉ đơn thuần **bất thường** (cao/thấp so với khoảng tham chiếu), để họ biết cần liên hệ bác sĩ sớm. Đây **không phải một trang/route riêng** — đây là một thành phần (component) xuất hiện lồng trong nhiều màn hình khác.

## Người dùng tìm ở đâu?

Cảnh báo khẩn cấp xuất hiện ở 3 nơi đã xác nhận trong code:
1. **Ngay sau khi phân tích** tại `/patient/analysis`: biểu ngữ đỏ toàn chiều rộng "Cảnh báo sức khỏe nghiêm trọng" (component `AnalysisResultView`).
2. **Trên trang Tổng quan** `/patient`: mục "Chỉ số cần lưu ý" (component `NeedsAttention`), hiển thị 2 loại thẻ:
   - Thẻ viền đỏ, nhãn **"Cần chú ý khẩn cấp"** (chỉ số `is_critical = true`).
   - Thẻ thường, nhãn **"Cần lưu ý"** (chỉ số ở trạng thái `high`/`low` nhưng không nguy kịch).
3. **Trên trang Xu hướng** `/patient/trends`: banner đỏ "Cần chú ý ngay" khi một chỉ số "đã đạt" hoặc "đang tiến gần" ngưỡng nguy kịch qua thời gian.

## Các bước sử dụng?

1. Khi biểu ngữ đỏ xuất hiện tại trang Analysis, đọc nội dung cảnh báo cho từng chỉ số nguy kịch.
2. Bấm nút **"Tôi sẽ liên hệ bác sĩ"** để xác nhận đã đọc — sau khi xác nhận, phần câu hỏi gợi ý cho bác sĩ mới hiện ra.
3. Trên trang Tổng quan, bấm link **"Xem phân tích chi tiết cho các chỉ số này"** dưới mục "Chỉ số cần lưu ý" để mở phiếu chi tiết (`/patient/reports/{id}`).
4. Trên trang Xu hướng, khi banner "Cần chú ý ngay" hiện, cân nhắc gửi yêu cầu bác sĩ review (xem `trends.md`).

## Điều kiện/giới hạn?

- Cảnh báo nguy kịch dựa trên trường `is_critical` / `critical_alerts` do backend tính (ngưỡng nguy kịch từ dữ liệu tham chiếu), không phải do người dùng tự đặt.
- Mục "Chỉ số cần lưu ý" trên Dashboard **chỉ hiển thị nếu có ít nhất một chỉ số nguy kịch hoặc bất thường** trong phiếu mới nhất — nếu tất cả chỉ số bình thường, mục này không hiện (trả về `null` trong code).
- Nút "Tôi sẽ liên hệ bác sĩ" chỉ là xác nhận đã đọc, không gửi thông báo/tin nhắn thật tới bác sĩ nào.

## Không làm được gì?

- **Không có trang "Cảnh báo khẩn cấp" độc lập** — nếu người dùng hỏi "cảnh báo khẩn cấp ở đâu", câu trả lời đúng là: nó xuất hiện lồng trong kết quả phân tích, trong Tổng quan, và trong Xu hướng — không có URL/menu riêng cho tính năng này.
- Không tự động gọi cấp cứu, đặt lịch khám, hay nhắn tin cho bác sĩ.
- Không phân biệt được mức độ khẩn cấp y tế thực tế (ví dụ độ ưu tiên cấp cứu) — chỉ dựa trên ngưỡng số liệu tham chiếu trong hệ thống.
