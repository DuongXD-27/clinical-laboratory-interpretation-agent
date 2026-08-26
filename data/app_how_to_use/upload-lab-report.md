```
feature: upload-analysis
role: patient
route: /patient/analysis
section: manual-entry,ocr-upload
```

## Feature này dùng để làm gì?

Cho phép bệnh nhân nhập kết quả xét nghiệm để hệ thống phân tích và giải thích. Trang nêu rõ mục đích: "Tải phiếu xét nghiệm hoặc nhập các chỉ số để hệ thống giải thích kết quả." Có 2 cách nhập:
- **Nhập tay**: gõ trực tiếp từng chỉ số.
- **Tải ảnh phiếu**: tải ảnh phiếu xét nghiệm, hệ thống dùng OCR (AI đọc ảnh) để trích xuất chỉ số (xem file `ocr-review.md`).

## Người dùng tìm ở đâu?

- Menu điều hướng bên trái khu vực bệnh nhân: mục **"Phân tích xét nghiệm"** → route `/patient/analysis`.
- Từ trang Tổng quan (`/patient`), khối "Hành động nhanh" có thẻ **"Phân tích phiếu mới"** trỏ tới cùng route.
- Trên trang Analysis có 2 nút chuyển chế độ: **"Nhập tay"** và **"Tải ảnh phiếu"**.

## Các bước sử dụng?

Nhập tay:
1. Bấm "Nhập tay" (mặc định đã chọn).
2. Bấm "+ Thêm chỉ số" để chọn các chỉ số có trên phiếu giấy của bạn.
3. Nhập giá trị cho từng chỉ số đã chọn.
4. Điền "Thông tin chung": Tuổi (18–60), Giới tính, Ngày xét nghiệm.
5. Bấm "Phân tích kết quả".

Tải ảnh phiếu: xem chi tiết ở `ocr-review.md`.

## Điều kiện/giới hạn?

- Nhập tay: tuổi phải là số nguyên trong khoảng **18–60** (ngoài khoảng này hệ thống báo lỗi "Dữ liệu tham chiếu hiện hỗ trợ người từ 18 đến 60 tuổi."); phải chọn ngày xét nghiệm.
- Người dùng khách (guest): vẫn dùng được cả 2 chế độ nhập, nhưng có thông báo "Bạn đang dùng thử với tư cách khách — Kết quả phân tích không được lưu lại và sẽ mất khi bạn thoát phiên."
- Nút "Xóa dữ liệu đang nhập" xóa toàn bộ dữ liệu đang nhập ở chế độ hiện tại.
- Tính năng tải ảnh (custom image) có thể bị tắt tùy chính sách hệ thống (`/api/v1/ocr/policy`) — xem `ocr-review.md`.

## Không làm được gì?

- Không giới hạn cố định số lượng chỉ số có thể thêm ở chế độ nhập tay, nhưng chỉ các chỉ số có trong danh mục hệ thống hỗ trợ mới chọn được.
- Không hỗ trợ nhập kết quả cho người ngoài khoảng tuổi 18–60 ở chế độ nhập tay (chưa xác nhận giới hạn tuổi tương tự có áp dụng cho chế độ OCR hay không — chế độ OCR cho phép tuổi 0–120, xem `ocr-review.md`).
- Không có nút "lưu nháp" — nếu rời trang khi chưa bấm "Phân tích kết quả", dữ liệu đang nhập sẽ mất.
