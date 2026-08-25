# App Help — manual demo (yeu-cau-vu.txt mục F)

5 câu hỏi bắt buộc, chạy qua dispatcher thật (`_dispatch_app_help`) +
retriever thật (Chroma collection `app_help_kb_v1`, embedding Gemini,
`APP_HELP_RETRIEVAL_MIN_SCORE=0.70`). `RETRIEVED_CHUNK_IDS` lấy trực tiếp từ
retriever (top-3); `SOURCE_DOC`/`FINAL_RESPONSE` là output thật của
dispatcher — không chỉnh sửa tay.

Run: `python -m eval.app_help.manual_demo` (2026-08-25).

---

```
QUESTION=Làm sao tải phiếu xét nghiệm?
RETRIEVED_CHUNK_IDS=['upload-analysis::feature-nay-dung-de-lam-gi', 'upload-analysis::cac-buoc-su-dung', 'upload-analysis::nguoi-dung-tim-o-dau']
SOURCE_DOC=['upload-lab-report.md']
FINAL_RESPONSE=Feature này dùng để làm gì?

Cho phép bệnh nhân nhập kết quả xét nghiệm để hệ thống phân tích và giải thích. Trang nêu rõ mục đích: "Tải phiếu xét nghiệm hoặc nhập các chỉ số để hệ thống giải thích kết quả." Có 2 cách nhập:
- **Nhập tay**: gõ trực tiếp từng chỉ số.
- **Tải ảnh phiếu**: tải ảnh phiếu xét nghiệm, hệ thống dùng OCR (AI đọc ảnh) để trích xuất chỉ số (xem file `ocr-review.md`).
PASS/FAIL=PASS
```

```
QUESTION=Tôi xem lịch sử ở đâu?
RETRIEVED_CHUNK_IDS=['history::cac-buoc-su-dung', 'history::nguoi-dung-tim-o-dau', 'history::khong-lam-duoc-gi']
SOURCE_DOC=['history.md']
FINAL_RESPONSE=Các bước sử dụng?

1. Vào mục "Lịch sử kết quả" trên menu.
2. Danh sách các phiếu đã lưu hiển thị theo trang (component `HistoryPanel`, phân trang 10 phiếu/trang trên web).
3. Bấm vào một phiếu để mở trang chi tiết, xem lại đầy đủ chỉ số, câu hỏi đã chọn cho bác sĩ, và trạng thái kiểm chứng của bác sĩ (nếu có).
PASS/FAIL=PASS
```

```
QUESTION=Làm sao xem xu hướng WBC?
RETRIEVED_CHUNK_IDS=['trends::cac-buoc-su-dung', 'trends::nguoi-dung-tim-o-dau', 'trends::dieu-kien-gioi-han']
SOURCE_DOC=['trends.md']
FINAL_RESPONSE=Các bước sử dụng?

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
PASS/FAIL=PASS
```

```
QUESTION=Tại sao phải xác nhận OCR?
RETRIEVED_CHUNK_IDS=['ocr-review::khong-lam-duoc-gi']
SOURCE_DOC=['ocr-review.md']
FINAL_RESPONSE=Không làm được gì?

- **Không thể bỏ qua bước xác nhận** — hệ thống chặn nút "Phân tích kết quả" nếu còn chỉ số chưa được tick kiểm tra hoặc chưa xác nhận độ tin cậy thấp. Đây chính là lý do phải xác nhận OCR: đảm bảo dữ liệu AI đọc khớp với phiếu giấy trước khi dùng để phân tích sức khỏe.
- Không tự động sửa lỗi đọc sai — người dùng phải tự đối chiếu và sửa tay từng chỉ số.
- Không đảm bảo đọc được mọi loại phiếu/mọi chỉ số; các chỉ số ngoài thư viện tham chiếu bị đánh dấu "chưa được hỗ trợ" và không tự động đưa vào phân tích.
PASS/FAIL=PASS
```

```
QUESTION=Tôi sửa thông tin cá nhân ở đâu?
RETRIEVED_CHUNK_IDS=['profile::cac-buoc-su-dung', 'profile::feature-nay-dung-de-lam-gi', 'profile::khong-lam-duoc-gi']
SOURCE_DOC=['profile.md']
FINAL_RESPONSE=Các bước sử dụng?

1. Vào mục "Thông tin cá nhân" trên menu.
2. Xem thông tin hiện tại: Họ tên, Ngày sinh, Giới tính, Email (mặc định các trường bị khóa/disabled).
3. Bấm nút **"Chỉnh sửa"** để mở khóa các trường nhập.
4. Sửa các trường cần thiết: Họ tên, Ngày sinh, Giới tính (Nam/Nữ/Khác), Email.
5. Bấm **"Lưu thay đổi"** để lưu, hoặc **"Hủy"** để hủy bỏ thay đổi và quay lại giá trị cũ.
6. Cuối trang hiển thị "Tạo lúc" và "Cập nhật lúc" của hồ sơ.
PASS/FAIL=PASS
```

## Note on RETRIEVED_CHUNK_IDS vs the public response

`SOURCE_DOC`/`FINAL_RESPONSE` above are exactly what `_dispatch_app_help`
returns to the orchestrator (`ExplanationDataPayload.sources`/`.explanation`)
— this is real, unedited output. `RETRIEVED_CHUNK_IDS` is captured by calling
`AppHelpRetriever.retrieve()` directly alongside the dispatch call, because
the public response payload deliberately does not expose raw chunk IDs to
end users (same convention as the existing provenance follow-up path — see
the CHAT-V1.5-R1-G1 comment block in `dispatcher.py`). Surfacing chunk IDs to
the end user was treated as new, separate scope, not bundled into this
change — noted here as an open item, not silently decided.
