```
feature: ocr-review
role: patient
route: /patient/analysis?mode=ocr
section: ocr-upload
```

## Feature này dùng để làm gì?

Cho phép bệnh nhân tải ảnh phiếu xét nghiệm; AI (Vision adapter) đọc và trích xuất các chỉ số từ ảnh thành bản nháp (draft). Trước khi đưa vào phân tích, bệnh nhân **bắt buộc phải xem lại và xác nhận** từng chỉ số đã đọc được, để tránh AI đọc sai gây hiểu nhầm về kết quả sức khỏe.

## Người dùng tìm ở đâu?

- Trang `/patient/analysis`, bấm nút chế độ **"Tải ảnh phiếu"**.
- Có thể vào thẳng chế độ này qua query `?mode=ocr` (được `frontend/src/app/patient/analysis/page.tsx` xử lý khi tham số `mode=ocr` có trong URL).

## Các bước sử dụng?

Quy trình hiển thị 4 bước trên giao diện: **"Tải phiếu → Kiểm tra dữ liệu → Phân tích → Xem kết quả"**.

1. Chọn ảnh phiếu xét nghiệm (khu vực kéo-thả).
2. Bấm **"Đọc phiếu xét nghiệm"** để AI xử lý ảnh.
3. Ở bước "Kiểm tra dữ liệu": với mỗi chỉ số AI đọc được, tick chọn ô **"Tôi đã kiểm tra tên, giá trị và đơn vị với ảnh gốc."**
4. Nếu chỉ số được đánh dấu độ tin cậy thấp ("Cần bạn kiểm tra lại"), phải tick thêm ô **"Tôi xác nhận giá trị trên đã đúng với phiếu xét nghiệm."**
5. Điền Tuổi, Giới tính, Ngày xét nghiệm.
6. Bấm **"Phân tích kết quả"** — nút chỉ bật khi mọi chỉ số đưa vào phân tích đã được kiểm tra/xác nhận và có giá trị hợp lệ.

## Điều kiện/giới hạn?

- Tải ảnh cá nhân phụ thuộc chính sách hệ thống lấy từ `/api/v1/ocr/policy` (`upload_enabled`, `custom_image_allowed`). Nếu tắt, giao diện hiện thông báo "Tải ảnh cá nhân hiện chưa được bật trong môi trường này."
- Một số chỉ số AI đọc được có thể **không được hệ thống hỗ trợ diễn giải** — hiển thị trong khối "Một số chỉ số hiện chưa được hỗ trợ" kèm lý do.
- Chỉ số có giá trị OCR không hợp lệ (không phải số) sẽ hiện cảnh báo và phải sửa trước khi tiếp tục.
- Tuổi hợp lệ cho chế độ OCR: số nguyên 0–120 (khác với giới hạn 18–60 của nhập tay).
- Nếu không tìm thấy chỉ số nào trong ảnh, hệ thống báo "Không tìm thấy chỉ số xét nghiệm trong ảnh. Hãy chụp rõ toàn bộ phiếu và thử lại."
- Có thể loại bỏ một chỉ số khỏi phân tích bằng nút "Không đưa vào phân tích", và đưa lại bằng "Đưa lại vào phân tích".
- Ảnh gốc không được lưu sau khi yêu cầu kết thúc (theo văn bản đồng ý hiển thị khi `consent_required=true`).

## Không làm được gì?

- **Không thể bỏ qua bước xác nhận** — hệ thống chặn nút "Phân tích kết quả" nếu còn chỉ số chưa được tick kiểm tra hoặc chưa xác nhận độ tin cậy thấp. Đây chính là lý do phải xác nhận OCR: đảm bảo dữ liệu AI đọc khớp với phiếu giấy trước khi dùng để phân tích sức khỏe.
- Không tự động sửa lỗi đọc sai — người dùng phải tự đối chiếu và sửa tay từng chỉ số.
- Không đảm bảo đọc được mọi loại phiếu/mọi chỉ số; các chỉ số ngoài thư viện tham chiếu bị đánh dấu "chưa được hỗ trợ" và không tự động đưa vào phân tích.
