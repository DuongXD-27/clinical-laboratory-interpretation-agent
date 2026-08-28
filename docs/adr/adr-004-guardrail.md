# ADR-004: Guardrail dùng kiến trúc nhiều lớp (Defense-in-Depth)

**Ngày:** 2026-08-01

**Trạng thái:** Accepted

## Bối cảnh

Sản phẩm y tế với ràng buộc cứng: tuyệt đối không chẩn đoán, không suy
đoán nguyên nhân. Trong lần kiểm thử đầu tiên của V1.0, dù đã có prompt
yêu cầu không suy đoán, giải thích sinh ra cho ca Kali nguy kịch vẫn chứa
câu suy đoán nguyên nhân ("có thể do thận hoạt động không bình thường",
"do ảnh hưởng của thuốc"). Chỉ prompt-level là không đủ tin cậy — đây là
bằng chứng thực nghiệm, không phải giả định.

## Các lựa chọn (Alternatives)

### Lựa chọn 1: 3 lớp độc lập (Prompt-level + Validator regex + UI-level Gate)
- Ưu điểm: Lỗi ở 1 lớp không lộ tới bệnh nhân; đã minh chứng hiệu quả
  thực tế khi lớp Validator bắt được lỗi mà lớp Prompt bỏ sót; log lại
  được các lần bị chặn phục vụ đánh giá sau này.
- Nhược điểm: Danh sách từ khóa cấm (regex) cần bảo trì liên tục, không
  bắt được mọi cách diễn đạt mới; mỗi lớp thêm 1 chút độ trễ xử lý.

### Lựa chọn 2: Chỉ dùng prompt-level
- Ưu điểm: Đơn giản, nhanh, không cần code thêm node.
- Nhược điểm: Đã tự chứng minh không đủ tin cậy qua chính lần test thật.

### Lựa chọn 3: Dùng 1 LLM thứ 2 làm "giám khảo" (LLM-as-judge)
- Ưu điểm: Có thể bắt được câu vi phạm diễn đạt tinh vi mà regex bỏ sót.
- Nhược điểm: Tốn thêm 1 lượt gọi API (chi phí + độ trễ); bản thân lớp
  giám khảo cũng mang tính xác suất, không chắc đáng tin hơn regex với
  các mẫu câu đã biết trước.

## Quyết định (Decision)

Chọn **Lựa chọn 1**: guardrail 3 lớp. Lựa chọn 3 để dành đánh giá lại ở
version sau nếu cần bắt các case tinh vi hơn.

## Lý do (Rationale)

1. Bằng chứng thực nghiệm trực tiếp: prompt-level một mình không chặn
   được câu suy đoán nguyên nhân trong lần test thật của V0.1.
2. Validator độc lập không dựa vào chính LLM tự đánh giá lại — tránh rủi
   ro LLM "tự tin sai" về câu trả lời của chính nó.
3. Log lại được các lần bị chặn (Guardrail Logs DB), phục vụ đánh giá và
   cải tiến sau này (PLO7).

## Hệ quả (Consequences)

- Cần rà soát định kỳ danh sách từ khóa cấm khi phát hiện case lọt lưới.
- Cân nhắc bổ sung Lựa chọn 3 (LLM-as-judge) nếu quy mô nội dung tăng và
  regex không còn đủ bao phủ.