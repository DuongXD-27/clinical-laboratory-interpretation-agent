## VERSION 1 — 28/07/2026 đến 02/08/2026

### Mục tiêu ban đầu
- Phiên bản đầu tiên - V1 xử lý được 3 chỉ số sinh tồn cốt lõi: Glucose, LDL-Cholesterol, và Kali.
- Xây dựng thành công luồng xử lý Agent Graph kết nối giữa Backend AI (LangGraph/FastAPI) và Frontend (Next.js).
- Thiết lập tiêu chuẩn an toàn y tế cơ bản, đặc biệt là cơ chế cảnh báo bệnh nhân đối với các chỉ số nguy kịch (Gate 3).

### Đã hoàn thành
- Viết tài liệu PRD V1 xác định rõ ràng scope (3 chỉ số) và Definition of Done.
- Dựng xong khung Backend với kiến trúc LangGraph gồm 4 node tách biệt: Reference Range Checker, Critical Detector, Analyzer, và Guardrail.
- Triển khai Data Reference (explanations.json) định nghĩa khoảng tham chiếu theo độ tuổi, giới tính và trực tiếp bằng đơn vị `mmol/L` cho 3 chỉ số.
- Thiết kế Frontend Premium UI với Next.js cho 2 phân hệ:
  - **Patient Portal**: Hiển thị kết quả dưới dạng thẻ trực quan, tích hợp Gate 3 (Red Banner tĩnh với nút xác nhận bắt buộc) cho trường hợp khẩn cấp.
  - **Doctor Portal**: Data-Grid chi tiết kèm khung nhập liệu HITL (Human-in-the-Loop).
- Tích hợp thành công End-to-End API `/api/v1/analyze`, xử lý lỗi 422 (sửa `raw_indicators` thành `indicators`) và 500 (mở rộng `IndicatorStatus` thành `str`).
- Tích hợp Gemini Flash qua thư viện `langchain-google-genai`.

### Quyết định kỹ thuật đã chốt
- **Kiến trúc luồng AI**: Sử dụng `LangGraph` thay vì LangChain Agent thông thường để kiểm soát luồng dữ liệu (State) đi qua từng màng lọc rõ ràng, tránh AI tự ý lặp vô hạn.
- **LLM Provider**: Chốt sử dụng `Gemini Flash` (model do người dùng tuỳ chỉnh trong `config.py`) làm bộ não suy luận chính vì tốc độ phản hồi nhanh.
- **Frontend Framework**: Sử dụng `Next.js + Tailwind CSS` để đảm bảo tiêu chuẩn giao diện "Premium", render phía client nhanh chóng, dễ tích hợp với FastAPI.
- **Format Dữ liệu**: Thống nhất Pydantic Schema cho Request (`AnalyzeRequest`) và Response (`AnalyzeResponse`), bỏ qua việc chuyển đổi đơn vị động (Unit Conversion) trong V0.1, thay vào đó nhập cứng giá trị theo `mmol/L` để rút ngắn thời gian.

### Vấn đề còn mở / chưa giải quyết
- Hệ thống hiện tại không có khả năng chuyển đổi đơn vị động (ví dụ từ `mg/dL` sang `mmol/L` hoặc ngược lại), đòi hỏi đầu vào phải tuyệt đối khớp với đơn vị cấu hình trong hệ thống.
- Module RAG (ChromaDB) mới ở trạng thái khởi tạo khung và code kết nối, kho dữ liệu y khoa (Vector Embeddings) thực tế bên trong còn rất sơ sài.
- Thiếu Authentication & Authorization. Hiện tại Patient và Doctor Portal đang tách biệt bằng URL path tĩnh mà không có cơ chế login/phân quyền.
- Guardrail hiện dùng fallback tĩnh 1 lớp, chưa có retry + Template Library như kiến trúc gốc — quyết định giản lược để kịp mốc 3 ngày, cần bổ sung ở version sau.
- Chưa có bước khử định danh PHI trước khi vào AI Engine — chưa nguy hiểm vì đang dùng data mock, nhưng cần làm trước khi có dữ liệu thật.

### Rủi ro cần lưu ý ở version tiếp theo
- Mở rộng lên 9 chỉ số sinh hoá sẽ làm phình to file cấu hình khoảng tham chiếu (`explanations.json`), đòi hỏi phải viết test case tự động cho từng chỉ số để tránh sai sót y khoa.
- Nguy cơ LLM "ảo giác" (Hallucination) sẽ tăng cao khi ngữ cảnh RAG bơm vào cho 9 chỉ số bắt đầu phức tạp và chồng chéo.

### Trạng thái ràng buộc an toàn (guardrail)
Hệ thống hiện đang được bảo vệ ở **Mức độ Cao (Validator Riêng + Prompt-Level + UI-Level)**:
- **Prompt-Level**: Lệnh LLM "Tuyệt đối không suy đoán nguyên nhân" và "Không đưa ra lời khuyên y tế / kê đơn".
- **Validator Riêng (Guardrail Node)**: Node quét Regex độc lập ở chặng cuối. Danh sách đen gồm các từ khóa cấm chẩn đoán y khoa và cấm suy đoán nguyên nhân (vd: *có thể do, nguyên nhân do, thường liên quan đến*). Nếu phát hiện vi phạm, node sẽ **xóa hoàn toàn** lời giải thích của AI và đè bằng câu Fallback an toàn, khuyến nghị gặp bác sĩ.
- **UI-Level**: Luôn ghim Disclaimer cứng ở dưới cùng màn hình. Với chỉ số nguy kịch, Gate 3 (Red Banner tĩnh) ép người dùng phải tương tác mới được xem tiếp.

### PLO đã chạm trong version này
- **PLO 2 (Kiến trúc & Framework AI)**: Thể hiện SÂU qua việc cấu trúc LangGraph (AgentState, Node) và phân định rõ trách nhiệm của Rule-based Node (Reference Checker) vs. AI Node (Analyzer).
- **PLO 4 (An toàn & Đạo đức AI)**: Thể hiện RẤT SÂU. Đây là trọng tâm của V0.1, hoàn thiện từ Guardrail chống chẩn đoán, chống suy đoán nguyên nhân, đến cơ chế Fallback và Gate 3 UI.
- **PLO 7 (Full-stack AI Deployment)**: Thể hiện SÂU thông qua việc tích hợp Next.js với FastAPI, xử lý CORS, và cấu trúc schemas Pydantic để chuẩn hoá giao tiếp giữa 2 hệ thống.

### Việc ưu tiên cho version tiếp theo
- Xử lý bài toán Chuyển đổi Đơn vị đo (Unit Conversion) linh hoạt.
- Mở rộng xử lý hệ thống để hỗ trợ trọn vẹn 9 chỉ số theo đúng lộ trình PRD V0.2.
- Nạp bộ dữ liệu nguồn Y khoa chất lượng cao vào ChromaDB để kiểm thử tính chính xác của RAG.
