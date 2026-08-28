# ADR-007: Đưa OCR sớm với Review Gate có bằng chứng phía server

**Ngày:** 2026-08-07  
**Trạng thái:** Accepted  
**Phạm vi:** `release/v3.0`

## Bối cảnh

ADR-006 đã chọn OCR hai bước và UI Review, đồng thời ghi nhận quyết định đưa OCR
sớm hơn lộ trình gốc. Tuy nhiên triển khai V2 gọi `/analyze` trực tiếp sau nút
“Xác nhận”; backend không nhận được bằng chứng từng dòng đã được đối chiếu và
không bảo toàn confidence gốc. Vì vậy client lỗi hoặc bị sửa có thể bỏ qua cảnh
báo confidence thấp.

Kickoff V3 ban đầu dời confidence-based gate sang V4. PO đã điều chỉnh phạm vi
`release/v3.0`: đóng lỗ hổng này ngay cùng PRD/guardrail, thay vì công bố OCR khi
server chưa cưỡng chế bước review.

## Các lựa chọn

### 1. Giữ gate chỉ ở frontend

- Ít code, trải nghiệm hiện tại không đổi.
- Không tạo được invariant phía server; nút submit chung không chứng minh từng
  dòng confidence thấp đã được xem.

### 2. Lưu bản nháp OCR trong database/session server

- Server giữ được toàn bộ bản gốc để đối chiếu.
- Tăng rủi ro lưu dữ liệu xét nghiệm/PHI, cần lifecycle và cleanup; không phù hợp
  chính sách V3 không nhận/lưu dữ liệu bệnh nhân thật.

### 3. Token ký ngắn hạn + xác nhận từng dòng (đã chọn)

- Server ký `draft_id` và confidence, không ký giá trị để vẫn cho phép sửa tay.
- Không lưu ảnh hoặc bản nháp ở server sau request; token hết hạn nhanh.
- Có thể cưỡng chế review mọi dòng và xác nhận tăng cường cho confidence thấp.
- Tăng độ phức tạp API/UI và thêm một endpoint.

## Quyết định

Chọn lựa chọn 3.

Luồng chuẩn:

1. `POST /ocr/upload` xử lý ảnh trong bộ nhớ, tạo draft và token ký có TTL.
2. Patient/Doctor UI hiển thị `raw_text`, confidence và trường sửa tay.
3. Mỗi dòng phải có `reviewed=true`; dòng được dùng có confidence gốc `< 0.7`
   phải có `low_confidence_acknowledged=true`.
4. `POST /ocr/confirm` xác minh chữ ký, TTL, tập `draft_id` đầy đủ và bằng chứng
   review; chỉ sau đó mới tạo `raw_indicators` và chạy graph với
   `is_ocr_reviewed=true`.

Ngưỡng và TTL lần lượt cấu hình bằng `OCR_LOW_CONFIDENCE_THRESHOLD` và
`OCR_REVIEW_TOKEN_EXPIRE_MINUTES`.

ADR này **thay thế riêng bước 2** của ADR-006: OCR UI không còn gọi `/analyze`
trực tiếp. Các quyết định về Vision LLM/OpenRouter và tiền xử lý ảnh của ADR-006
vẫn giữ nguyên.

## Vì sao OCR vẫn là “Nâng cao nhưng làm sớm”

Luồng cơ bản không cần ảnh/VLM và vẫn là đường lui vận hành. OCR được làm sớm vì
giảm nhập tay, thể hiện đúng nhu cầu người dùng và tạo bằng chứng rõ cho thiết kế
HITL an toàn. Đổi lại, team chấp nhận thêm thao tác review, độ trễ/độ sẵn sàng
của provider và rủi ro người dùng xác nhận nhầm còn tồn dư.

## Hệ quả

- Cả upload và confirm yêu cầu JWT patient/doctor.
- Frontend dùng chung một `OcrReviewPanel` cho hai portal.
- Không có auto-pass cho confidence cao: tất cả dòng đều phải review; confidence
  thấp chỉ tăng thêm một xác nhận rõ ràng.
- Token không thay thế xác thực người dùng và không chứa tên/giá trị xét nghiệm.
- Khi triển khai dữ liệu thật, vẫn phải bổ sung de-identification, consent và
  chính sách lưu trữ; ADR này không tuyên bố hệ thống sẵn sàng lâm sàng.

