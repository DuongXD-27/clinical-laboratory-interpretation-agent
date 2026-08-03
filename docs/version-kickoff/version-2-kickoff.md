# Version 2 Kickoff — VMEC-05

**Ngày bắt đầu:** 03/08/2026 

**Chu kỳ:** 2-3 ngày theo nhịp lặp đã thống nhất.

---

## 1. Ràng buộc an toàn cố định (không đổi qua các version — luôn tuân thủ)

- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, không kết luận nguyên nhân gây ra chỉ số
  bất thường, không đề nghị điều trị/kê đơn.
- Chỉ giải thích chỉ số LÀ GÌ và Ý NGHĨA CHUNG — không suy đoán lý do
  (cấm các cụm như "có thể do", "nguyên nhân do", "thường liên quan đến").
- Luôn khuyến cáo trao đổi trực tiếp với bác sĩ để được diễn giải chính xác.
- Grounded trên nguồn có thật, chống bịa (hallucination) — không tự sinh
  thông tin y khoa ngoài nguồn RAG.
- Chỉ số nguy kịch (Kali, đường huyết cực đoan...) phải kích hoạt cảnh báo
  khẩn riêng biệt, có gate xác nhận thủ công.
- Bảo mật PHI — không để lộ thông tin định danh bệnh nhân.

---

## 2. Bản Handoff version liền trước (Version 1)

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

---

## 3. Quyết định kiến trúc đã chốt (không tự ý đổi)

Các quyết định dưới đây đã qua ADR, **không bàn lại từ đầu** trong V2 —
chỉ mở rộng/nâng cấp trên nền đã chốt:

- **Orchestration**: LangGraph, không dùng agent tự do kiểu ReAct —
  xem `adr-001-langgraph.md`. Guardrail luôn là node cuối cùng, ép cứng
  thứ tự, không có ngoại lệ.
- **Đơn vị đo**: Chuẩn hóa toàn hệ thống về `mmol/L` — xem
  `adr-002-measurement.md`. *(Lưu ý: quyết định này KHÔNG bao gồm unit
  conversion động — xem mục 5 và 6 bên dưới về khoảng trống này.)*
- **Critical-Value Detection**: Luật cứng (rule-based), KHÔNG dùng LLM,
  ngưỡng lưu riêng ở `critical_thresholds.json`, tách biệt khỏi bảng
  tham chiếu thường — xem `adr-003-critical-value-detection.md`.
- **Guardrail**: Kiến trúc 3 lớp độc lập (Prompt-level + Validator regex
  + UI-level Gate) — xem `adr-004-guardrail.md`. V2 được phép **nâng
  cấp bên trong lớp Validator** (thêm retry + Template Library, thêm
  công cụ kiểm tra ngoài regex) nhưng **không đổi kiến trúc 3 lớp**, và
  **chưa chuyển sang LLM-as-judge** (Lựa chọn 3 trong ADR-004 vẫn để
  dành version sau).
- **Phân loại Critical-Value Detection**: Đã xếp vào nhóm "Cơ bản" của
  dự án từ V1, không xếp theo nhóm "Nâng cao" như đề bài liệt kê gốc —
  xem `adr-005-basic-critical-value.md`.
- **Schema state**: Theo `state.py` hiện tại (`AgentState`,
  `IndicatorAssessment`, `CriticalAlert`, `IndicatorExplanation`...).
  Node OCR mới (xem mục 4) phải tuân thủ nguyên tắc đã ghi chú trong
  state: dữ liệu OCR **không được ghi thẳng vào state chính**, phải đi
  qua bước xác nhận thủ công (UI_Review) trước khi vào pipeline chính —
  đúng tinh thần Gate 3 đã áp dụng cho critical alert.
- **Trường `error`**: Không trả nguyên văn ra API/UI cho người dùng cuối
  (đã từng lộ ở V1) — cần audit lại khi deploy thật (xem việc của Duy).

---

## 4. Mục tiêu & DoD của Version 2

Theo phân công đã thảo luận với team, V2 chạy song song 4 luồng việc.
Mỗi luồng có DoD riêng, nhưng **guardrail và critical-value gate không
được lùi lại** dù các luồng khác chưa xong.

### 4.1. OCR — Gate xác nhận (Dương + Vũ)
- Vision LLM Adapter (`Adapter_Vision`) hoạt động, đầu ra đúng lược đồ
  nội bộ chuẩn, đồng bộ với `Adapter_JSON` đang có.
- OCR **không ghi thẳng vào state chính** — bắt buộc qua Gate `UI_Review`:
  độ tin cậy thấp → bắt buộc bệnh nhân/bác sĩ xác nhận thủ công trước
  khi submit vào hệ thống.
- Đã kiểm tra case ảnh mờ/nghiêng/thiếu sáng, ghi nhận sai số làm đường
  cơ sở (baseline).
- ADR mới: lý do đưa OCR sớm hơn lộ trình gốc, ghi rõ đánh đổi đã chấp
  nhận.
- PRD cập nhật: xác định OCR thuộc nhóm "Cơ bản" hay "Nâng cao nhưng làm
  sớm" — kèm lý do (tương tự cách ADR-005 đã làm cho Critical-Value
  Detection).

### 4.2. Guardrail nâng cấp (Dương)
- Thêm 1 lượt **retry** trước khi rơi vào Template Fallback (đúng sơ đồ
  gốc, còn thiếu ở V1 theo Handoff).
- Build **Template Library** (mẫu giải thích + câu hỏi kiểm duyệt), dùng
  chung cho cả 2 nhánh dự phòng (giải thích & câu hỏi cho bác sĩ).
- Bổ sung công cụ kiểm tra tại chỗ **ngoài regex** để giảm rủi ro lọt
  câu suy đoán/kê đơn diễn đạt kiểu mới (không thay thế 3-layer, chỉ
  làm dày lớp Validator).

### 4.3. Mở rộng 9 chỉ số + khởi động RAGAS (Tuấn)
- Lọc trước: chỉ tích hợp dòng `range_flag = OK` + `confidence = HIGH`
  + `source_priority_tier ∈ {T1, T2}` cho V2.
- Refactor `RuleCheck` + `IndicatorAssessment`: chuyển từ hardcode 3 chỉ
  số sang lookup theo `(analyte, sex, age_scope)` — cần Vũ duyệt vì đụng
  graph/state.
- Map cột CSV → field trong `IndicatorAssessment`/`explanations.json`
  (`range_lower → reference_low`, `range_upper → reference_high`,
  `unit_display_vn → unit`...).
- Test case tự động cho từng chỉ số mới (đúng cam kết ở Handoff V1).
- PRD ghi rõ: các chỉ số mới chỉ có mức "abnormal", **không có
  "critical"** — trừ Kali (đúng ADR-003, ADR-005).
- Khởi động RAGAS eval song song để đo chất lượng retrieval, không chỉ
  "nhét vector DB là xong".

### 4.4. Triển khai thật + Đăng nhập thật (Duy)
- Deploy: Next.js → Vercel; FastAPI → Render/Railway/Fly.io.
- Biến môi trường (API key Gemini, DB URL...) — không commit secret vào
  repo.
- CORS đúng tên miền sản xuất.
- Auth tối giản phù hợp 2 vai trò hiện có (NextAuth hoặc JWT tự viết).
- Migrate user tối thiểu: `(id, vai trò: bệnh nhân/bác sĩ)`.
- Audit lại trường `error` trong state — đảm bảo không lộ ra UI (đúng
  ghi chú trong `state.py`, từng xảy ra ở V1).
- Kiểm thử end-to-end trên môi trường deploy thật, không chỉ localhost.
- Ghi log độ trễ ban đầu — làm chuẩn nền cho PLO liên quan đến "giá sát"
  ở V4/V5.

---

## 5. Phạm vi KHÔNG làm ở version này

- **Không** làm Unit Conversion linh hoạt (mg/dL ↔ mmol/L), dời tiếp sang V3 vì ưu
  tiên OCR/9 chỉ số/deploy trước.
- Không làm đa ngôn ngữ.
- Không làm memory/trend theo dõi xu hướng qua nhiều lần xét nghiệm.
- Không chuyển guardrail sang LLM-as-judge (ADR-004, Lựa chọn 3) — vẫn
  để dành đánh giá ở version sau.
- Không merge 17 dòng chỉ số chất lượng thấp/chưa verify (`range_flag`
  hoặc `confidence` không đạt, hoặc `source_priority_tier` ngoài T1/T2)
  vào config chính — tách thành file/list riêng, chờ Dương review.
- Không hoàn thiện toàn bộ pipeline khử định danh PHI — V2 chỉ dừng ở
  migrate user tối thiểu `(id, role)` cho auth, **chưa phải** bước khử
  định danh PHI đầy đủ trước khi dữ liệu vào AI Engine (xem cảnh báo ở
  mục 6).

---

## 6. Known issues đang cố ý để đó (không phải bug bị bỏ sót)

- Chưa có unit conversion động — quyết định có chủ đích cho V1, **nhưng
  cần team xác nhận lại có chủ đích tiếp tục hoãn ở V2 hay không** (xem
  cảnh báo mục 5).
- Guardrail vẫn dựa một phần trên regex/từ khóa cấm (dù đã thêm retry +
  Template Library + công cụ kiểm tra bổ sung ở V2) — LLM-as-judge vẫn
  chưa triển khai, theo đúng ADR-004.
- 17 dòng ngưỡng chỉ số chất lượng thấp/chưa verify — tách riêng, không
  đưa vào production, chờ review.
- **Bảo mật PHI vẫn là open issue an toàn chưa đóng**: từ V1 đã ghi nhận
  "chưa có bước khử định danh PHI trước khi vào AI Engine — chưa nguy
  hiểm vì đang dùng data mock". V2 bắt đầu có login thật + user thật
  (Duy) nhưng chưa thấy trong phân công một bước khử định danh PHI đầy
  đủ. Nếu V2 hoặc V3 bắt đầu nhận dữ liệu bệnh nhân thật (không còn là
  mock), đây là ràng buộc an toàn bắt buộc (mục 1) cần được ưu tiên
  trước khi go-live, không thể tiếp tục hoãn vô thời hạn.

---

## 7. Bản đồ code hiện tại

- `state.py` — schema `AgentState` dùng chung cho toàn bộ graph.
- `data/reference/explanations.json` — bảng khoảng tham chiếu theo độ
  tuổi/giới tính, đơn vị `mmol/L`.
- `data/reference/critical_thresholds.json` — ngưỡng nguy kịch, tách
  biệt khỏi bảng tham chiếu thường (ADR-003).
- Node pipeline theo LangGraph: Reference Range Checker → Critical
  Detector → (RAG) Analyzer/Explainer → Guardrail (đúng thứ tự bắt buộc
  trong `state.py`: `check_reference_range → detect_critical_values →
  retrieve_explanation → personalize_explanation → generate_questions →
  guardrail_check → build_summary`).
- Adapter đầu vào: `Adapter_JSON` (đã có ở V1) và `Adapter_Vision` (mới,
  do Vũ phụ trách ở V2, đầu ra phải đồng bộ schema với `Adapter_JSON`).
- Guardrail node: hiện có Regex Validator; V2 bổ sung retry + Template
  Library.

---

## 8. Phân công Version 2

| Thành viên | Mục tiêu (user story) | Việc làm chính | Checklist trọng tâm |
|---|---|---|---|
| **Dương** | Là PO giữ Guardrail, muốn có retry + Template Library thay vì fallback tĩnh 1 lớp; là bệnh nhân, muốn xác nhận lại chỉ số do OCR đọc | Cổng an toàn cho OCR + nâng cấp Guardrail + cập nhật PRD/ADR | Thiết kế UI_Review; viết Gate riêng cho luồng OCR (độ tin cậy thấp → bắt buộc xác nhận); thêm retry trước Template Fallback; build TemplateLib; cập nhật PRD (OCR "Cơ bản" hay "Nâng cao làm sớm"); viết ADR mới; bổ sung công cụ kiểm tra ngoài regex |
| **Vũ** | Là bệnh nhân, muốn tải ảnh chụp phiếu xét nghiệm | OCR qua Vision LLM Adapter | Chốt phương án Vision LLM (Gemini Vision/GPT-4V/Document AI...) → ghi ADR; xây `Adapter_Vision` đồng bộ schema với `Adapter_JSON`; đảm bảo OCR đi qua UI_Review, không ghi thẳng state chính; test ảnh mờ/nghiêng/thiếu sáng; duyệt code Tuấn nối 9 chỉ số vào graph (giữ vai trò chốt kiến trúc); phối hợp RAGAS với Tuấn |
| **Tuấn** | Là bệnh nhân, muốn xem giải thích đủ 9 chỉ số; là PO, muốn biết RAG có "ảo giác" không | Mở rộng 9 chỉ số + khởi động RAGAS | Lọc dòng `range_flag=OK` + `confidence=HIGH` + `source_priority_tier∈{T1,T2}`; tách 17 dòng nghi vấn riêng; refactor `RuleCheck`/`IndicatorAssessment` sang lookup `(analyte, sex, age_scope)` (cần Vũ duyệt); map cột CSV → field chuẩn; test case tự động từng chỉ số; PRD ghi rõ chỉ Kali có mức "critical" |
| **Duy** | Là bệnh nhân/bác sĩ, muốn truy cập qua URL thật và đăng nhập thật | Triển khai thật + Đăng nhập thật | Chọn nền tảng deploy (Vercel/Render/Railway/Fly.io); cấu hình env var an toàn; CORS đúng domain; chọn giải pháp auth (NextAuth/JWT); migrate user tối thiểu `(id, role)`; audit trường `error` không lộ ra UI; test end-to-end trên môi trường thật; log độ trễ ban đầu |

*Quyết định phân công dựa theo tài liệu phân công V2 đã thảo luận với
team, đối chiếu với "Việc ưu tiên cho version tiếp theo" ở mục 2.*

---
