# ADR-003: Critical-Value Detection dùng luật cứng (rule-based), không dùng LLM

**Ngày:** 2026-07-29

**Trạng thái:** Accepted

## Bối cảnh

Phát hiện giá trị nguy kịch (vd Kali ≥ 6.5 mmol/L) là điểm quyết định
quan trọng nhất trong toàn hệ thống — sai ở bước này có thể gây hại thật.
LLM có tính xác suất, có thể trả lời khác nhau cho cùng 1 input ở các
lần gọi khác nhau — không chấp nhận được cho quyết định "có nguy kịch
hay không".

## Các lựa chọn (Alternatives)

### Lựa chọn 1: Luật cứng (rule-based), lưu ngưỡng ở file riêng
- Ưu điểm: Deterministic, test được bằng unit test cố định (input → output
  không đổi); ngưỡng nguy kịch audit độc lập với bảng tham chiếu thường;
  không phụ thuộc hành vi LLM.
- Nhược điểm: Bảo trì song song 2 file cấu hình; chỉ số ngoài thư viện sẽ
  không được phát hiện nguy kịch.

### Lựa chọn 2: Để LLM tự đọc giá trị và phân loại trạng thái
- Ưu điểm: Không cần thêm node riêng, gộp chung 1 lần gọi LLM, ít code hơn.
- Nhược điểm: Non-deterministic — rủi ro không chấp nhận được cho quyết
  định an toàn tính mạng.

### Lựa chọn 3: Gộp ngưỡng nguy kịch chung 1 bảng với khoảng tham chiếu bình thường
- Ưu điểm: Chỉ cần bảo trì 1 file duy nhất.
- Nhược điểm: Làm mờ ranh giới giữa "thông tin tham khảo" và "ngưỡng cảnh
  báo khẩn", khó audit riêng, rủi ro 1 dòng sai lẫn vào hàng chục dòng
  bình thường mà không ai để ý.

## Quyết định (Decision)

Chọn **Lựa chọn 1**: luật cứng, ngưỡng nguy kịch lưu ở
`critical_thresholds.json`, tách biệt khỏi bảng tham chiếu thường.

## Lý do (Rationale)

1. Đây là quyết định ảnh hưởng an toàn tính mạng — cần tính nhất quán
   tuyệt đối, loại bỏ khỏi phạm vi xác suất của LLM.
2. Tách file riêng cho phép audit/verify từng ngưỡng độc lập — đã áp
   dụng: đánh dấu rõ ngưỡng Kali nào còn là số tạm chưa verify nguồn.
3. Cho phép viết test tự động xác định trước khi tích hợp lên giao diện.

## Hệ quả (Consequences)

- Cần đồng bộ thủ công giữa 2 file cấu hình khi cập nhật dữ liệu.
- Cần cơ chế log & giới hạn phạm vi riêng cho chỉ số chưa có trong
  `critical_thresholds.json`.