# App Help — manual demo (yeu-cau-vu.txt mục F)

5 câu hỏi bắt buộc, chạy qua **toàn bộ pipeline thật**: retriever thật
(Chroma collection `app_help_kb_v1`, embedding Gemini,
`APP_HELP_RETRIEVAL_MIN_SCORE=0.70`) → `_dispatch_app_help` →
`response_composer.build_final_response` (bao gồm cả bước LLM viết lại có
kiểm soát, nếu xảy ra — xem `_APP_HELP_EXTRA_RULES` trong
`response_composer.py`). `RETRIEVED_CHUNK_IDS` lấy trực tiếp từ retriever
(top-3); `SOURCE_DOC`/`FINAL_RESPONSE` là `response.sources`/`response.message`
thật — không chỉnh sửa tay.

Đây là bản chạy lại (2026-08-25, sau audit routing/retrieval) — bản đầu
tiên (trước khi có bước LLM rewrite + section-hint fix) đã lỗi thời, xem
git history của file này nếu cần so sánh.

Run: `python -m eval.app_help.manual_demo`.

---

```
QUESTION=Làm sao tải phiếu xét nghiệm?
RETRIEVED_CHUNK_IDS=['upload-analysis::cac-buoc-su-dung']
SOURCE_DOC=['upload-lab-report.md']
FINAL_RESPONSE=Bạn có thể nhập kết quả xét nghiệm theo các bước sau: 1. Chọn "Nhập tay". 2. Bấm "+ Thêm chỉ số" để chọn các chỉ số trên phiếu xét nghiệm của bạn. 3. Nhập giá trị cho từng chỉ số. 4. Điền thông tin chung bao gồm tuổi (18–60), giới tính và ngày xét nghiệm. 5. Bấm "Phân tích kết quả" để xem thông tin.
PASS/FAIL=PASS
```

```
QUESTION=Tôi xem lịch sử ở đâu?
RETRIEVED_CHUNK_IDS=['history::nguoi-dung-tim-o-dau', 'history::cac-buoc-su-dung', 'history::khong-lam-duoc-gi']
SOURCE_DOC=['history.md']
FINAL_RESPONSE=- Menu điều hướng bên trái khu vực bệnh nhân: mục **"Lịch sử kết quả"** → route `/patient/history`.
- Từ trang Tổng quan (`/patient`), khối "Hành động nhanh" có thẻ **"Xem lịch sử"** (mô tả phụ: "Tra cứu kết quả cũ") trỏ tới cùng route.
- Chi tiết từng phiếu mở tại `/patient/history/{reportId}` (dùng chung component `PatientReportDetail` với `/patient/reports/{reportId}`).
PASS/FAIL=PASS
```

```
QUESTION=Làm sao xem xu hướng WBC?
RETRIEVED_CHUNK_IDS=['trends::cac-buoc-su-dung', 'trends::nguoi-dung-tim-o-dau', 'trends::dieu-kien-gioi-han']
SOURCE_DOC=['trends.md']
FINAL_RESPONSE=Chế độ "Từng chỉ số":
1. Chọn chỉ số cần xem trong ô thả xuống "Chỉ số".
2. Chọn "Phạm vi dữ liệu": **"5 kết quả gần nhất"** hoặc **"3 tháng gần nhất"**.
3. Xem biểu đồ đường theo thời gian kèm đường tham chiếu bình thường/nguy kịch.
4. Bấm nút **"Giải thích xu hướng"** để AI sinh giải thích bằng văn bản cho biểu đồ đang xem.
5. Có thể gửi yêu cầu bác sĩ review biểu đồ (xem panel "TrendDoctorReviewPanel" ngay dưới phần giải thích).

Chế độ "Cả nhóm chức năng":
1. Chọn "Nhóm chức năng" cần xem (ví dụ nhóm chỉ số có ≥3 điểm dữ liệu đủ điều kiện).
2. Chọn kiểu hiển thị: **"Biểu đồ đường"** hoặc **"Ma trận nhiệt"**.
3. Bấm **"Giải thích cả nhóm"** để AI giải thích chung cho cả nhóm chỉ số.
PASS/FAIL=PASS
```

```
QUESTION=Tại sao phải xác nhận OCR?
RETRIEVED_CHUNK_IDS=['ocr-review::khong-lam-duoc-gi']
SOURCE_DOC=['ocr-review.md']
FINAL_RESPONSE=Để sử dụng tính năng phân tích, bạn lưu ý một số điểm sau: Bạn không thể bỏ qua bước xác nhận dữ liệu vì hệ thống sẽ chặn nút "Phân tích kết quả" nếu vẫn còn chỉ số chưa được kiểm tra hoặc chưa xác nhận độ tin cậy thấp. Việc xác nhận OCR giúp đảm bảo dữ liệu AI đọc khớp với phiếu giấy của bạn. Bên cạnh đó, hệ thống không tự động sửa lỗi đọc sai, vì vậy bạn cần tự đối chiếu và sửa tay từng chỉ số. Ngoài ra, hệ thống không đảm bảo đọc được mọi loại phiếu hoặc chỉ số; các chỉ số ngoài thư viện tham chiếu sẽ được đánh dấu "chưa được hỗ trợ" và không tự động đưa vào phân tích.
PASS/FAIL=PASS
```

```
QUESTION=Tôi sửa thông tin cá nhân ở đâu?
RETRIEVED_CHUNK_IDS=['profile::nguoi-dung-tim-o-dau']
SOURCE_DOC=['profile.md']
FINAL_RESPONSE=Menu điều hướng bên trái khu vực bệnh nhân: mục **"Thông tin cá nhân"** → route `/patient/profile`.
PASS/FAIL=PASS
```

## Quan sát

- Câu 1, 3, 4 được LLM viết lại tự nhiên hơn (không còn heading/`.md`
  reference) — đúng thiết kế `_APP_HELP_EXTRA_RULES`.
- Câu 2 KHÔNG được viết lại (network timeout tạm thời khi chạy — xem log),
  rơi về bản đã dọn heading/file-ref nhưng vẫn còn markdown bold/backtick
  thô. Đây là hành vi AN TOÀN theo thiết kế (fail closed về verbatim khi
  composer lỗi), không phải bug — chỉ là câu trả lời kém mượt hơn ở lần
  chạy cụ thể này.
- Câu 5 chỉ trả về vị trí menu (không phải các bước) vì câu hỏi chỉ có
  cue "ở đâu", không có cue "làm sao"/"các bước" — đúng thiết kế
  `_section_hint`.

## Note on RETRIEVED_CHUNK_IDS vs the public response

`SOURCE_DOC`/`FINAL_RESPONSE` above are exactly what
`response_composer.build_final_response` returns
(`OrchestratorResponse.sources`/`.message`) — real, unedited output.
`RETRIEVED_CHUNK_IDS` is captured by calling `AppHelpRetriever.retrieve()`
directly alongside the dispatch call, because the public response payload
deliberately does not expose raw chunk IDs to end users (same convention as
the existing provenance follow-up path — see the CHAT-V1.5-R1-G1 comment
block in `dispatcher.py`). Surfacing chunk IDs to the end user was treated
as new, separate scope, not bundled into this change — noted here as an
open item, not silently decided.
