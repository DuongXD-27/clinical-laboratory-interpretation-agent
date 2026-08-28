# ADR-006: OCR Phiếu Xét Nghiệm bằng Vision LLM qua OpenRouter (2 bước + UI_Review)

**Ngày:** 2026-08-04

**Trạng thái:** Accepted

## Bối cảnh

Đề bài yêu cầu đọc kết quả xét nghiệm từ **ảnh phiếu xét nghiệm** (tính
năng Nâng cao). Hiện hệ thống chỉ nhận dữ liệu JSON qua `/api/v1/analyze`
(Adapters_JSON). Cần một Adapter_Vision để chuyển ảnh → danh sách chỉ số
thô, nhưng luồng này phải tuân theo ràng buộc an toàn của kickoff V2
mục 4.1: **dữ liệu từ ảnh KHÔNG được đưa thẳng vào AgentState** — người
dùng phải xác nhận trước khi phân tích.

## Các lựa chọn (Alternatives)

### Lựa chọn 1: OCR một bước — ảnh → thẳng vào graph phân tích
- Ưu điểm: Ít bước UI, trải nghiệm nhanh.
- Nhược điểm: Vi phạm trực tiếp kickoff V2 mục 4.1 (UI_Review). VLM đọc
  sai chỉ số sẽ lập tức lan vào kết quả giải thích và cảnh báo nguy kịch —
  rủi ro an toàn không chấp nhận được với dữ liệu y khoa.

### Lựa chọn 2: OCR hai bước — ảnh → bản nháp → người dùng xác nhận → `/analyze`
- Ưu điểm: Tuân thủ UI_Review (kickoff V2 mục 4.1); bản nháp có `confidence`
  và `raw_text` để người dùng đối chiếu; giữ graph LangGraph hiện tại
  nguyên vẹn (không thêm node, không sửa AgentState).
- Nhược điểm: Thêm một bước UI, tốn thời gian người dùng kiểm tra.

### Lựa chọn 3: OCR cục bộ (Tesseract/PaddleOCR) không dùng VLM
- Ưu điểm: Không tốn API, không phụ thuộc network.
- Nhược điểm: Dễ vỡ với bảng lồng nhau, chữ in chồng, tiếng Việt có dấu,
  chữ nghiêng/mờ — chính là các trường hợp phiếu xét nghiệm thực tế. VLM
  đọc ngữ cảnh bảng tốt hơn hẳn. Chi phí của `:free` model OpenRouter ≈ 0.

## Quyết định (Decision)

Chọn **Lựa chọn 2**: luồng OCR hai bước với Vision LLM qua OpenRouter.

- Bước 1: `POST /api/v1/ocr/upload` nhận file ảnh → preprocess (deskew +
  auto-contrast, xem `image_processor.py`) → gọi Vision LLM → trả
  `OCRReviewResponse` (bản nháp: `name`, `value`, `unit`, `confidence`,
  `raw_text`).
- Bước 2: frontend hiển thị bản nháp để người dùng kiểm tra/sửa, điền
  metadata (tuổi/giới tính/ngày) rồi gọi `/api/v1/analyze` (luồng cũ,
  graph không đổi). Bản nháp OCR **không bao giờ ghi vào `AgentState`/
  `raw_indicators`**.

Thông số kỹ thuật:

- Provider: **OpenRouter** (OpenAI-compatible) — key riêng
  `OPENROUTER_API_KEY`, không tái dùng `OPENAI_API_KEY`.
- Model mặc định: `google/gemma-4-26b-a4b-it:free` — cấu hình qua
  `VISION_MODEL` trong `.env`. Không hardcode vì OpenRouter hay thay đổi
  danh mục model free-tier (xem ghi chú trong `.env.example`).
- **Lịch sử model:** ban đầu chọn `nvidia/nemotron-nano-12b-v2-vl:free`;
  ngày 2026-08-04 chuyển sang `google/gemma-4-26b-a4b-it:free` sau khi đo
  baseline cho thấy gemma ổn định hơn (ít rate-limit, ít trả rỗng) dù tốc
  độ tương đương. Xem `docs/audit/ocr-baseline.md` để so sánh số liệu.
- Vision LLM **không trả lời y khoa**: system prompt giới hạn việc trích
  xuất JSON, không giải thích/chẩn đoán (guardrail, ADR-004).

## Đưa OCR sớm hơn lộ trình gốc (V2 thay vì nhóm "Nâng cao" sau)

### Bối cảnh

Lộ trình gốc của đề bài VMEC-05 xếp OCR vào nhóm **Nâng cao**, dự kiến làm
sau khi các nhóm khác hoàn tất. Tuy nhiên kickoff V2 chọn ưu tiên
**"OCR/9 chỉ số/deploy trước"** và giao OCR cho Dương + Vũ làm trong V2
(xem `version-2-kickoff.md` mục 4.1). ADR này ghi rõ lý do + đánh đổi đã
chấp nhận — tương tự cách ADR-005 đã làm cho Critical-Value Detection.

### Các lựa chọn (Alternatives)

#### Lựa chọn 1: Làm OCR sớm trong V2 (đã chọn)
- Ưu điểm: Đáp ứng nhu cầu thực của người dùng (chụp ảnh phiếu thay vì nhập
  tay); minh hoạ sớm Adapter_Vision + Gate an toàn UI_Review — điểm khác
  biệt đáng giá của hệ thống; tận dụng được thời điểm Dương + Vũ cùng sẵn.
- Nhược điểm: Đẩy lùi lịch các việc Nâng cao khác; rủi ro OCR đọc sai lan
  vào kết quả nếu không chặn đúng cách.

#### Lựa chọn 2: Giữ đúng lộ trình gốc (làm sau khi xong 9 chỉ số + deploy)
- Ưu điểm: Đúng thứ tự liệt kê của đề bài, dễ đối chiếu checklist.
- Nhược điểm: Không kịp minh hoạ tính năng Nâng cao trong bản demo; bỏ lỡ
  cơ hội chứng minh Gate an toàn cho nguồn dữ liệu kém tin cậy (ảnh chụp).

### Quyết định (Decision)

Chọn **Lựa chọn 1**: làm OCR trong V2, **với điều kiện bắt buộc** — dữ
liệu từ ảnh không được ghi thẳng vào `AgentState`, luôn đi qua UI_Review
(xem "Quyết định" ở trên). Điều kiện này đã được implement và kiểm thử.

### Đánh đổi đã chấp nhận

1. **Độ chính xác OCR không đạt 100%** — chấp nhận bằng cổng xác nhận thủ
   công (UI_Review) thay vì trì hoãn; chỉ số confidence thấp luôn phải qua
   bước duyệt của bệnh nhân/bác sĩ trước khi vào pipeline.
2. **Tốc độ model free-tier chậm** (11–42s/ảnh đo thực tế ngày 2026-08-04)
   — chấp nhận tạm thời cho demo; đổi model trả phí khi có ngân sách
   (cấu hình qua `VISION_MODEL`, xem `ocr-baseline.md`).
3. **Lịch các tính năng Nâng cao khác bị lùi** (đa ngôn ngữ, ...) so với
   làm tuần tự đúng thứ tự đề bài.
4. **Rủi ro phụ thuộc VLM bên ngoài** (chi phí, danh mục model free-tier
   thay đổi) — giảm thiểu bằng cách không hardcode model, cấu hình qua
   `.env` và có retry trong `VisionAdapter`.

## Lý do (Rationale)

1. Bắt buộc tuân theo kickoff V2 mục 4.1 — đây là ràng buộc được sponsor
   chốt, không thể đổi.
2. Cách 2 bước không đụng vào graph/state hiện có → rủi ro regression thấp,
   test suite cũ vẫn chạy (không phá 22 test hiện hữu).
3. OpenRouter `:free` VLM = chi phí 0 cho demo, dễ đổi model sau khi đã
   đo baseline (ADR này đi kèm bộ ảnh mẫu + `eval_ocr.py`).
4. Preprocess ảnh (deskew/contrast) xử lý 2 ca phổ biến (phiếu chụp nghiêng,
   thiếu sáng) trước khi gửi VLM, cải thiện độ chính xác mà không tốn prompt.

## Hệ quả (Consequences)

- Thêm endpoint mới `/api/v1/ocr/upload`, module `src/adapters/vision_adapter.py`,
  `src/services/image_processor.py`, schema `src/models/ocr_schemas.py`.
- Cần `OPENROUTER_API_KEY` hợp lệ để chạy baseline (`src/scripts/eval_ocr.py`).
- Frontend thêm chế độ "Tải ảnh phiếu" với màn hình UI_Review.
- Sai số OCR được đo trên bộ ảnh mẫu (normal/blur/skew/lowlight), báo cáo
  ở `docs/audit/ocr-baseline.md`.
- Đơn vị đo vẫn giữ chuẩn mmol/L theo ADR-002 — chỉ số đọc từ ảnh phải
  được người dùng xác nhận đúng đơn vị ở UI_Review; không làm unit-conversion
  tự động ở V2.
