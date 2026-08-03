# ADR-001: Chọn LangGraph để điều phối Agent

**Ngày:** 2026-07-28

**Trạng thái:** Accepted

## Bối cảnh

Bài toán cần nhiều bước xử lý nối tiếp với ràng buộc an toàn nghiêm ngặt:
đối chiếu khoảng tham chiếu → phát hiện giá trị nguy kịch → tra cứu giải
thích qua RAG → kiểm duyệt nội dung (guardrail) trước khi trả về người
dùng. Đây là sản phẩm y tế — guardrail bắt buộc phải chạy ở mọi luồng,
không được phép bị bỏ qua trong bất kỳ trường hợp nào. Ngoài ra, đề bài
yêu cầu kiến trúc phải trace/debug được từng bước (PLO2).

## Các lựa chọn (Alternatives)

### Lựa chọn 1: LangGraph
- Ưu điểm: Quản lý state tường minh qua từng node dạng đồ thị; đảm bảo
  guardrail luôn được thực thi ở cuối luồng bất kể LLM "muốn" gì; dễ
  trace/debug từng bước; tích hợp sẵn với hệ sinh thái LangChain đang
  dùng cho RAG.
- Nhược điểm: Thêm 1 dependency mới, cần thời gian làm quen; kém linh
  hoạt hơn agent tự do khi gặp ca ngoài kịch bản đã thiết kế.

### Lựa chọn 2: Gọi hàm tuần tự thông thường (không dùng framework)
- Ưu điểm: Đơn giản, không cần học thư viện mới, dễ hiểu cho người mới.
- Nhược điểm: Không có cơ chế quản lý state chuẩn, khó mở rộng khi thêm
  node mới, không có công cụ trace/visualize luồng.

### Lựa chọn 3: LangChain Agent kiểu ReAct
- Ưu điểm: Linh hoạt, LLM tự quyết định gọi tool nào và khi nào dừng,
  phù hợp bài toán mở.
- Nhược điểm: Rủi ro cao nhất — LLM có thể tự ý bỏ qua bước guardrail vì
  không bị ép buộc trong luồng cứng, không chấp nhận được với sản phẩm y tế.

## Quyết định (Decision)

Chọn **Lựa chọn 1: LangGraph**.

## Lý do (Rationale)

1. Guardrail bắt buộc phải chạy ở mọi luồng — LangGraph cho phép ép cứng
   thứ tự node, loại bỏ khả năng LLM tự bỏ qua bước an toàn.
2. Đề bài yêu cầu kiến trúc trace/debug được (PLO2) — StateGraph
   visualize luồng rõ ràng hơn agent loop tự do.
3. Từng node test độc lập được trước khi ghép — đã áp dụng thực tế khi
   build V1, giúp cô lập lỗi nhanh (vd lỗi 422/500 khi tích hợp API).
4. Giảm chi phí học thêm framework thứ 2 vì đã tích hợp sẵn hệ sinh thái
   LangChain nhóm dùng cho RAG.

## Hệ quả (Consequences)

- Khi mở rộng thêm node (OCR, memory/trend ở version sau), cần thiết kế
  lại một phần luồng state — chấp nhận được, đã lường trước khi chọn.
- Cần thời gian làm quen cho thành viên chưa dùng LangGraph.