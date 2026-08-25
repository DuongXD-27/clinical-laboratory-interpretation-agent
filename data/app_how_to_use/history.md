```
feature: history
role: patient
route: /patient/history
section: report-list
```

## Feature này dùng để làm gì?

Cho phép bệnh nhân theo dõi và tìm lại các phiếu xét nghiệm đã lưu trước đây, theo đúng mô tả trên trang: "Theo dõi và tìm lại các phiếu xét nghiệm đã lưu."

## Người dùng tìm ở đâu?

- Menu điều hướng bên trái khu vực bệnh nhân: mục **"Lịch sử kết quả"** → route `/patient/history`.
- Từ trang Tổng quan (`/patient`), khối "Hành động nhanh" có thẻ **"Xem lịch sử"** (mô tả phụ: "Tra cứu kết quả cũ") trỏ tới cùng route.
- Chi tiết từng phiếu mở tại `/patient/history/{reportId}` (dùng chung component `PatientReportDetail` với `/patient/reports/{reportId}`).

## Các bước sử dụng?

1. Vào mục "Lịch sử kết quả" trên menu.
2. Danh sách các phiếu đã lưu hiển thị theo trang (component `HistoryPanel`, phân trang 10 phiếu/trang trên web).
3. Bấm vào một phiếu để mở trang chi tiết, xem lại đầy đủ chỉ số, câu hỏi đã chọn cho bác sĩ, và trạng thái kiểm chứng của bác sĩ (nếu có).

## Điều kiện/giới hạn?

- Chỉ hiển thị được cho tài khoản bệnh nhân đã đăng nhập (`getRole() === "patient"`) — mục này **bị ẩn khỏi menu đối với người dùng khách (guest)**.
- Phiếu trùng lặp (cùng ngày, cùng bộ kết quả) có thể được hệ thống nhận diện và không tạo bản ghi mới.
- Nếu Dashboard báo "Bác sĩ đã kiểm chứng N phiếu xét nghiệm của bạn", link "Xem lại" cũng dẫn về `/patient/history`.

## Không làm được gì?

- Người dùng khách (guest) **không có** mục Lịch sử — dữ liệu phân tích của guest không được lưu nên không có gì để tra cứu.
- Trong danh sách lịch sử (`HistoryPanel.tsx`) **không có** nút xóa phiếu — chữ "Xóa" duy nhất ở đây là "Xóa lọc" (xóa bộ lọc tìm kiếm theo ngày/tên bệnh nhân).
- Xóa phiếu **thực hiện ở trang chi tiết**, không phải ở danh sách: mở một phiếu (`/patient/history/{id}` hoặc `/patient/reports/{id}`, dùng chung component `PatientReportDetail.tsx`) → nút **"Xóa phiếu"** ở góc trên bên phải → xác nhận hộp thoại "Bạn có chắc muốn xóa kết quả xét nghiệm này?" → gọi `DELETE /api/v1/patient/me/lab-reports/{reportId}` → xóa xong tự quay về `/patient/history`. Thao tác này không thể hoàn tác (không có nút khôi phục/thùng rác trong code đã đọc).
- Ghi chú của bác sĩ gắn trên phiếu thì khác: chỉ "thêm mới, không sửa và không xoá" (nguyên văn trong UI) — không lẫn với việc xóa cả phiếu.
- Không chỉnh sửa được giá trị chỉ số của một phiếu đã lưu từ trang lịch sử (chỉ xem lại, không có form sửa).
