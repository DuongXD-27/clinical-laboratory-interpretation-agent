# ADR-005: Xếp Critical-Value Detection vào nhóm "Cơ bản"

**Ngày:** 2026-07-28

**Trạng thái:** Accepted

## Bối cảnh

Đề bài VMEC-05, mục "Yêu cầu đầu ra", liệt kê "Phát hiện giá trị nguy
kịch — cảnh báo khẩn" ở nhóm Nâng cao. Tuy nhiên, mục "Ràng buộc" của
cùng đề bài quy định đây là yêu cầu an toàn bắt buộc ("chỉ số nguy hiểm —
cảnh báo cần liên hệ y tế khẩn"). Đề bài tự mâu thuẫn giữa 2 cách phân
loại cho cùng 1 tính năng.

## Các lựa chọn (Alternatives)

### Lựa chọn 1: Xếp vào Cơ bản, làm ngay từ V1.0
- Ưu điểm: Chứng minh năng lực an toàn cốt lõi ngay từ bản đầu; giảm rủi
  ro nếu dự án phải dừng giữa chừng; làm nền tảng sớm cho guardrail
  (ADR-003, ADR-004).
- Nhược điểm: Tốn thời gian phát triển sớm hơn dự kiến, đẩy lùi lịch các
  tính năng Nâng cao khác (OCR, đa ngôn ngữ...).

### Lựa chọn 2: Giữ đúng theo đề bài, xếp cùng nhóm Nâng cao, làm sau
- Ưu điểm: Bám sát đúng thứ tự liệt kê gốc của đề bài, dễ đối chiếu checklist.
- Nhược điểm: Rủi ro an toàn cao hơn nhiều so với các tính năng Nâng cao
  khác — không thể đánh đồng "thiếu OCR" (kém tiện) với "thiếu cảnh báo
  nguy kịch" (có thể gây hại thật).

## Quyết định (Decision)

Chọn **Lựa chọn 1**: xếp Critical-Value Detection vào nhóm Cơ bản của
riêng dự án, triển khai từ V1.0.

## Lý do (Rationale)

1. Mục Ràng buộc của đề bài quy định đây là luật an toàn bắt buộc, không
   có ngoại lệ — ưu tiên theo ràng buộc, không theo cách phân loại tính năng.
2. Bản chất rủi ro của việc thiếu tính năng này khác hẳn các tính năng
   Nâng cao còn lại.
3. Cần thiết kế và kiểm chứng sớm để làm nền tảng cho các version sau.

## Hệ quả (Consequences)

- Đã ghi chú rõ trong PRD lý do lệch khỏi thứ tự liệt kê gốc của đề bài,
  tránh giám khảo hiểu nhầm là đọc sai yêu cầu.
- Các tính năng Nâng cao khác bị đẩy lùi lịch hơn so với làm tuần tự
  đúng thứ tự đề bài.