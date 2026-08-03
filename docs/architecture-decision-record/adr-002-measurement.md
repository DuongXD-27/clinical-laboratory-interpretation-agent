# ADR-002: Chuẩn hóa hệ đơn vị đo về mmol/L

**Ngày:** 2026-07-28

**Trạng thái:** Accepted

## Bối cảnh

Phiếu xét nghiệm ở Việt Nam thường dùng mmol/L cho Glucose và bộ mỡ máu
(LDL, HDL, Triglyceride), trong khi nhiều tài liệu y khoa tiếng Anh
(nguồn RAG tham khảo) trình bày theo mg/dL. Rủi ro lẫn đơn vị đã xảy ra
thật: bảng ngưỡng LDL ban đầu bị so sánh nhầm giá trị mmol/L với ngưỡng
viết theo mg/dL, khiến hệ thống phân loại sai (báo "Tối ưu" cho 1 ca
thực chất đang ở mức cao).

## Các lựa chọn (Alternatives)

### Lựa chọn 1: Chuẩn hóa toàn hệ thống về mmol/L
- Ưu điểm: Khớp thói quen đọc phiếu xét nghiệm thực tế của bệnh nhân
  Việt Nam, đúng mục tiêu "dễ hiểu cho bệnh nhân" của đề bài.
- Nhược điểm: Tài liệu nguồn tiếng Anh chủ yếu dùng mg/dL, cần tự quy đổi
  thủ công khi biên soạn nội dung nguồn.

### Lựa chọn 2: Chuẩn hóa về mg/dL
- Ưu điểm: Phổ biến hơn trong tài liệu tiếng Anh, dễ tìm nguồn tham khảo.
- Nhược điểm: Không khớp thói quen đọc phiếu xét nghiệm của bệnh nhân
  Việt Nam — đi ngược mục tiêu chính của đề bài.

### Lựa chọn 3: Hỗ trợ song song 2 đơn vị, tự động quy đổi theo đầu vào
- Ưu điểm: Linh hoạt nhất, đúng hướng lâu dài, xử lý được cả phiếu nước
  ngoài.
- Nhược điểm: Tốn thời gian phát triển hơn mức cho phép trong mốc 3 ngày
  của V0.1.

## Quyết định (Decision)

Chọn **Lựa chọn 1: chuẩn hóa mmol/L toàn hệ thống** cho V1.0. Lựa chọn 3
(quy đổi động) được dời sang version sau.

## Lý do (Rationale)

1. Khớp đúng thực tế phiếu xét nghiệm Việt Nam — mục tiêu cốt lõi của
   sản phẩm.
2. Loại bỏ ngay lớp lỗi đã thực sự gặp phải khi test V0.1 (LDL bị phân
   loại sai do lẫn đơn vị).
3. Đơn giản hóa phạm vi phù hợp mốc 3 ngày; quy đổi động để dành version
   sau khi có thêm thời gian.

## Hệ quả (Consequences)

- Nếu nhận đầu vào từ phiếu dùng mg/dL (vd OCR từ nguồn nước ngoài), hệ
  thống sẽ đọc sai giá trị cho đến khi có cơ chế quy đổi động.
- Đã ghi nhận là việc ưu tiên cho version tiếp theo trong Version Handoff
  V1, không phải thiếu sót bị bỏ quên.