```
feature: trends
role: patient
route: /patient/trends
section: single-analyte,group-trends
```

## Feature này dùng để làm gì?

Cho phép bệnh nhân xem biến động của một chỉ số xét nghiệm (ví dụ WBC) qua nhiều lần đo, hoặc xem cả một nhóm chỉ số cùng chức năng (ví dụ nhóm mỡ máu) cùng lúc, dưới dạng biểu đồ đường hoặc ma trận nhiệt (heatmap). Trang mô tả: "Chọn một chỉ số để xem biến động qua các lần xét nghiệm đã lưu."

## Người dùng tìm ở đâu?

- Menu điều hướng bên trái khu vực bệnh nhân: mục **"Xu hướng chỉ số"** → route `/patient/trends`.
- Từ trang Tổng quan, khối "Hành động nhanh" có thẻ **"Xu hướng"** (mô tả phụ: "Theo dõi thay đổi").
- Có 2 tab: **"Từng chỉ số"** (`?analyte=...`, mặc định) và **"Cả nhóm chức năng"** (`?mode=group`).

## Các bước sử dụng?

Chế độ "Từng chỉ số":
1. Chọn chỉ số cần xem trong ô thả xuống "Chỉ số".
2. Chọn "Phạm vi dữ liệu": **"5 kết quả gần nhất"** hoặc **"3 tháng gần nhất"**.
3. Xem biểu đồ đường theo thời gian kèm đường tham chiếu bình thường/nguy kịch.
4. Bấm nút **"Giải thích xu hướng"** để AI sinh giải thích bằng văn bản cho biểu đồ đang xem.
5. Có thể gửi yêu cầu bác sĩ review biểu đồ (xem panel "TrendDoctorReviewPanel" ngay dưới phần giải thích).

Chế độ "Cả nhóm chức năng":
1. Chọn "Nhóm chức năng" cần xem (ví dụ nhóm chỉ số có ≥3 điểm dữ liệu đủ điều kiện).
2. Chọn kiểu hiển thị: **"Biểu đồ đường"** hoặc **"Ma trận nhiệt"**.
3. Bấm **"Giải thích cả nhóm"** để AI giải thích chung cho cả nhóm chỉ số.

## Điều kiện/giới hạn?

- Xu hướng **chỉ hiển thị khi một chỉ số có từ 3 kết quả (lần đo) trở lên** — thông báo rõ: "Xu hướng chỉ được hiển thị đối với các chỉ số có từ 3 kết quả trở lên." Các phiếu trùng ngày/trùng bộ kết quả có thể bị nhận diện là trùng lặp và không tính thêm điểm.
- Chế độ nhóm chỉ khả dụng khi có ≥1 nhóm chức năng đủ điều kiện (ví dụ có đủ dữ liệu cho ít nhất vài chỉ số cùng nhóm như HbA1c và LDL-C).
- Chỉ dành cho tài khoản bệnh nhân đã đăng nhập (`getRole() === "patient"`); **không có trong menu của guest**.
- Nếu chỉ số/nhóm đã đạt hoặc tiến gần ngưỡng nguy kịch, biểu đồ hiện banner đỏ "Cần chú ý ngay".
- Biểu đồ chỉ nối các điểm đã đo, không suy diễn dữ liệu giữa hai lần xét nghiệm — có ghi chú rõ trên giao diện.

## Không làm được gì?

- Đây **không phải chẩn đoán** — cuối trang có ghi rõ: "Biểu đồ và phần giải thích xu hướng chỉ hỗ trợ theo dõi dữ liệu xét nghiệm theo thời gian, không phải chẩn đoán và không thay thế đánh giá của bác sĩ."
- Không hiển thị được xu hướng cho chỉ số mới chỉ có 1–2 lần đo.
- Không tự động thông báo cho bác sĩ — muốn bác sĩ xem phải chủ động gửi yêu cầu qua panel review xu hướng (xem `doctor-questions.md` cho phần bác sĩ xử lý yêu cầu này).
