# PRD V3 — OCR Review Gate và Guardrail nâng cấp

**Phiên bản:** 3.0  
**Ngày:** 2026-08-07  
**Trạng thái:** Approved for `release/v3.0`

## 1. Bài toán

OCR có thể đọc sai tên, giá trị hoặc đơn vị trên phiếu xét nghiệm. Nếu dữ liệu
sai được đưa thẳng vào pipeline, Reference Checker và Critical Detector vẫn xử
lý đúng theo dữ liệu nhận được nhưng kết quả cuối cùng có thể gây hiểu nhầm cho
người dùng. Đồng thời, guardrail V1 chỉ có regex và fallback tĩnh nên dễ chặn oan
và không bao phủ các cách diễn đạt né từ khóa.

## 2. Người dùng và user story

- Là bệnh nhân hoặc bác sĩ, tôi muốn đối chiếu và sửa từng chỉ số OCR trước khi
  phân tích để dữ liệu đọc sai không tự động đi vào hệ thống.
- Là PO giữ an toàn, tôi muốn dòng OCR confidence thấp có một xác nhận tăng
  cường, độc lập với nút submit chung.
- Là PO giữ guardrail, tôi muốn nội dung vi phạm được thử viết lại đúng một lần
  rồi mới dùng mẫu dự phòng đã duyệt, nhằm giảm chặn oan mà không hạ mức an toàn.

## 3. Quyết định phạm vi sản phẩm

OCR vẫn thuộc nhóm **Nâng cao**, nhưng được **làm sớm** và đưa vào V3. OCR không
được đổi nhãn thành “Cơ bản”, vì luồng cơ bản vẫn phải hoạt động hoàn chỉnh với
dữ liệu nhập tay/mô phỏng mà không phụ thuộc Vision LLM, ảnh hoặc OpenRouter.

Lý do làm sớm:

1. Ảnh phiếu là cách nhập sát nhu cầu người dùng nhất và giảm công nhập tay.
2. OCR tạo ra nguồn dữ liệu không chắc chắn, phù hợp để chứng minh cơ chế HITL
   và defense-in-depth của sản phẩm.
3. Kiến trúc adapter tách biệt cho phép phát hành sớm mà không biến Vision LLM
   thành điều kiện bắt buộc của luồng cơ bản.

Đánh đổi chấp nhận: thêm một bước xác nhận, tăng thời gian thao tác; phụ thuộc
VLM bên ngoài ở bước trích xuất; OCR không đạt độ chính xác tuyệt đối; người dùng
vẫn có thể xác nhận nhầm dù hệ thống đã cảnh báo rõ.

## 4. Yêu cầu chức năng

### FR-OCR — OCR Review Gate

1. `/api/v1/ocr/upload` chỉ trả bản nháp; không chạy graph phân tích.
2. Mỗi bản nháp có `draft_id`, `confidence`, `raw_text` và `needs_review`.
3. Server ký confidence gốc trong review token hết hạn sau 15 phút. Client không
   được tự nâng confidence để bỏ qua gate.
4. Bệnh nhân/bác sĩ phải xác nhận đã đối chiếu **mọi dòng** với ảnh gốc.
5. Dòng được giữ lại có `confidence < 0.7` phải có xác nhận tăng cường riêng.
6. Người dùng được sửa tên, giá trị, đơn vị hoặc loại dòng khỏi phân tích; phải
   giữ lại ít nhất một dòng.
7. Chỉ `/api/v1/ocr/confirm` với token và bằng chứng review hợp lệ mới chuyển dữ
   liệu OCR vào graph với `is_ocr_reviewed=true`.
8. Upload và confirm đều yêu cầu JWT của vai trò patient hoặc doctor.

### FR-GR — Guardrail

1. Kiểm tra toàn bộ nội dung hiển thị: summary, explanation, indicator name và
   questions for doctor.
2. Validator chạy tại chỗ, kết hợp regex và luật ý định không phụ thuộc regex,
   không gọi mạng/model để quyết định pass/fail.
3. Khi phát hiện vi phạm, được gọi LLM rewrite **đúng một lần**.
4. Output rewrite phải qua lại cùng validator. Nếu vẫn vi phạm hoặc retry lỗi,
   dùng Template Library.
5. Một Template Library đã duyệt dùng chung cho fallback giải thích/tóm tắt và
   fallback câu hỏi bác sĩ.
6. `guardrail_passed=false` nếu nội dung ban đầu từng vi phạm, kể cả output cuối
   đã được làm an toàn; flags được giữ để audit.

## 5. Yêu cầu phi chức năng và an toàn

- Không chẩn đoán, kết luận nguyên nhân, kê đơn hoặc đề nghị điều trị.
- Ảnh upload chỉ xử lý trong request, không ghi xuống filesystem/database.
- Token review không chứa giá trị xét nghiệm; chỉ chứa ID dòng và confidence.
- Ngưỡng confidence và TTL cấu hình bằng environment variables.
- Không dùng dữ liệu bệnh nhân thật trong V3; PHI de-identification đầy đủ vẫn
  là điều kiện bắt buộc trước production clinical use.

## 6. Ngoài phạm vi

- Tự động bỏ qua review cho confidence cao.
- Tự động sửa giá trị OCR dựa trên khoảng tham chiếu.
- Unit conversion tự động.
- LLM-as-judge và chẩn đoán/điều trị dưới mọi hình thức.

## 7. Definition of Done

- UI Review dùng chung xuất hiện cho cả Patient Portal và Doctor Portal.
- Backend từ chối token sai/hết hạn, thiếu dòng, dòng chưa review và dòng
  confidence thấp chưa xác nhận tăng cường.
- OCR UI không gọi `/analyze` trực tiếp.
- Guardrail có test cho retry một lần, fallback và cách diễn đạt không dấu né
  regex.
- PRD, ADR và kickoff V3 nhất quán về quyết định “Nâng cao nhưng làm sớm”.

