## VERSION 2 — 03/08/2026 12:00 đến 05/08/2026 11:59

### Mục tiêu ban đầu
- Xây dựng Adapter_Vision cho phép tải ảnh phiếu xét nghiệm, trích xuất chỉ số bằng Vision LLM, và đưa qua Gate UI_Review để bệnh nhân/bác sĩ xác nhận thủ công trước khi vào pipeline chính (Vũ + Dương).

- Nâng cấp Guardrail: thêm 1 lượt retry bằng LLM rewrite trước khi rơi vào fallback tĩnh; xây dựng Template Library dùng chung cho cả 2 nhánh dự phòng; bổ sung công cụ kiểm tra ngoài regex (Dương).

- Mở rộng từ 3 chỉ số lên 9 chỉ số theo danh sách đã lọc chất lượng (range_flag=OK, confidence=HIGH, source_priority_tier ∈ {T1,T2}); refactor RuleCheck sang lookup theo (analyte, sex, age_scope); viết test case tự động; tách 17 dòng nghi vấn riêng; khởi động RAGAS eval

- Triển khai backend lên Railway, frontend lên Vercel; xây dựng đăng nhập JWT thật cho 2 vai trò patient/doctor; đảm bảo CORS đúng domain production; không commit secret vào repo; ghi log latency làm baseline (Duy).

### Đã hoàn thành
- Adapter_Vision — src/adapters/vision_adapter.py (class VisionAdapter, 256 dòng): gọi OpenRouter (OpenAI-compatible) với model google/gemma-4-26b-a4b-it:free, trả list[OCRIndicatorDraft] — schema tách biệt hoàn toàn với IndicatorInput của pipeline chính. Đầu ra đúng lược đồ nội bộ và đồng bộ với luồng JSON hiện có qua cùng raw_indicators.

- Xử lý ảnh mờ/nghiêng/thiếu sáng — src/services/image_processor.py (class ImageProcessor): _deskew() dùng Hough transform (OpenCV, hàm HoughLinesP), _auto_contrast() dùng ImageOps.autocontrast(cutoff=2). Có 4 ảnh mẫu thực tế tại data/ocr_samples/{normal,blur,lowlight,skew}/report.png.

- OCR không ghi thẳng vào state chính — src/agents/graph.py: route_on_input() kiểm tra ocr_drafts and not is_ocr_reviewed, chuyển luồng sang ui_review_gate trước khi vào reference_range_checker. src/agents/state.py L92-99 khai báo ocr_drafts: list[OCRIndicatorDraft] | None và is_ocr_reviewed: bool tách biệt khỏi raw_indicators.

- Gate UI_Review trên frontend — frontend/src/app/patient/page.tsx: handleOcrUpload() gọi /api/v1/ocr/upload, trả bản nháp; updateEdit() cho người dùng chỉnh sửa; handleOcrConfirm() (L128-134) lấy bản nháp đã xem xét rồi mới gọi /api/v1/analyze. Không có luồng tự bypass bước này.

- ADR-006 — docs/architecture-decision-record/adr-006-ocr-openrouter.md (Accepted, 2026-08-04): ghi lý do chọn Vision LLM qua OpenRouter thay Tesseract/OCR cục bộ, lý do đưa OCR sớm hơn lộ trình gốc, lịch sử đổi model từ nvidia/nemotron-nano-12b-v2-vl:free sang google/gemma-4-26b-a4b-it:free.

- Guardrail retry — src/agents/nodes/guardrail_node.py L55-77 (hàm rewrite_with_llm) + L180-236: khi phát hiện vi phạm trong summary, explanations, indicators, questions_for_doctor, thử LLM rewrite 1 lần — nếu vẫn vi phạm sau rewrite thì mới fallback về template. Áp dụng cho cả 2 nhánh dự phòng (giải thích và câu hỏi cho bác sĩ).

- Template Library — src/services/template_loader.py (hàm load_templates()), data/reference/templates.json: có fallback_explanation, fallback_summary, disclaimer, doctor_questions_fallback — dùng chung cho cả 2 nhánh dự phòng.

- Công cụ kiểm tra ngoài regex — guardrail_node.py L44-53 (get_forbidden_embeddings()), L142-168 (check_violation()): tích hợp Vector Semantic Similarity (cosine similarity với BGE-M3 embedding, ngưỡng 0.85) vào hàm kiểm tra vi phạm, bổ sung song song với regex blacklist.

- Refactor RuleCheck sang lookup — src/agents/nodes/reference_range_checker_node.py L134-139 dùng repository.select_rule(analyte, unit, patient_gender, patient_age) từ ReferenceRepository (src/services/reference_repository.py): lookup theo (analyte, sex, age_scope) — không còn hardcode 3 chỉ số.

- explanations.json đủ 9 chỉ số — data/reference/explanations.json: ['WBC', 'RBC', 'HGB', 'Glucose', 'HbA1c', 'LDL-Cholesterol', 'HDL-Cholesterol', 'Creatinine', 'Kali'] — so với 3 chỉ số V1.

- Tách file dữ liệu nghi vấn — data/reference/quarantine_v2.csv (22 dòng bị quarantine: Basophils %, Basophils abs, Direct bilirubin, HbA1c, LDL-C, MPV, Potassium, Uric acid, eGFR); data/reference/reference_ranges_v2.json (31 analyte canonical, chỉ accepted vào runtime) tách biệt hoàn toàn. data/reference/reference_build_report.json ghi rõ: strict_quality_eligible_rows: 58, quarantined_rows: 22.

- Map cột CSV → field trong IndicatorAssessment — src/services/reference_repository.py: select_rule() tra cứu range_lower/range_upper từ JSON; reference_range_checker_node.py L152-153 gán assessment["reference_low"] = _json_number_or_none(lower), assessment["reference_high"] = _json_number_or_none(upper).

- Test case tự động — tests/test_agents/test_reference_range_checker_node.py (401 dòng), tests/test_data/test_build_reference_config.py (283 dòng), tests/test_data/test_v2_analyte_manifest.py (192 dòng), tests/test_integration/test_v2_reference_pipeline.py (268 dòng), tests/test_vision/test_ocr.py (190 dòng).

- RAGAS đã chạy thực tế — eval/results/ragas_v2_baseline.json (generated_at: 2026-08-05T02:49:11Z, 12 case, Faithfulness mean=0.909, Context Precision mean=0.955 trên 4 analyte approved: WBC, RBC, Fasting plasma glucose, Creatinine). Script đầy đủ eval/run_ragas.py (1015 dòng) + eval/ragas_compat.py (85 dòng).

- JWT đăng nhập thật — src/services/auth.py (bcrypt + jose JWT), src/api/auth_routes.py (POST /auth/login, GET /auth/me), src/api/deps.py (Bearer token guard). Frontend frontend/src/app/page.tsx là form đăng nhập thật. Route /patient và /doctor có guard kiểm tra token + role, redirect về / nếu thiếu.

- Database user tối thiểu — src/models/db.py: bảng users (id, username, password_hash, role: "patient"/"doctor"), seed 2 tài khoản demo khi khởi động.

- Thông báo lỗi không lộ chi tiết nội bộ — src/main.py L55-64: unhandled_exception_handler trả về {"detail": "Hệ thống đang bận, vui lòng thử lại."} cho mọi exception chưa được bắt — không lộ stack trace hay message nội bộ.

- Ghi nhận latency — src/api/routes.py L38-49: started_at = time.perf_counter(), tính elapsed_ms, log qua logger.info("analyze completed user=%s indicators=%d elapsed_ms=%.1f", ...).

- Backend deploy cấu hình Railway — railway.json (healthcheck /health, restart on failure), Dockerfile được cập nhật.

- CORS chặn wildcard — src/main.py L35-44: ValueError nếu CORS_ORIGINS chứa * khi allow_credentials=True.

- Fail-fast JWT_SECRET — src/config.py L56-65: @model_validator reject nếu app_env == "production" mà jwt_secret vẫn là giá trị mặc định.

### Quyết định kỹ thuật đã chốt
- Vision LLM qua OpenRouter — chọn OpenRouter (OpenAI-compatible API) với model google/gemma-4-26b-a4b-it:free (model mặc định trong VISION_MODEL env). Lý do được ghi trong adr-006-ocr-openrouter.md: OCR cục bộ (Tesseract/PaddleOCR) kém với chữ tiếng Việt có dấu, bảng lồng và ảnh mờ nghiêng; chi phí model free-tier trên OpenRouter ≈ 0. Key riêng OPENROUTER_API_KEY, không tái dùng OPENAI_API_KEY.

- OCR hai bước với Gate UI_Review — lý do trong adr-006-ocr-openrouter.md: tránh VLM đọc sai trực tiếp lan vào kết quả giải thích và cảnh báo nguy kịch. Bản nháp có confidence và raw_text để đối chiếu.

- Guardrail nâng cấp sang Regex + Semantic Similarity + LLM Retry — giữ nguyên kiến trúc 3 lớp (Prompt-level + Validator + UI-level) từ ADR-004; bổ sung bên trong lớp Validator: thêm embedding similarity (BGE-M3) và LLM self-correction 1 vòng trước fallback tĩnh. Chưa chuyển sang LLM-as-judge (ADR-004 Lựa chọn 3) — để dành version sau, đúng quyết định đã ghi trong kickoff V2.

- LDL-C, Potassium, HbA1c vào pending_analytes — reference_checker_v2_config.json: 3 chỉ số này quarantined trong build vì range_flag != OK (theo reference_build_report.json), không được đưa vào approved dù có trong explanations.json. Lý do quarantine ghi trong quarantine_v2.csv từng dòng.

- JWT tự viết — src/services/auth.py dùng python-jose + bcrypt. Fail-fast trong production nếu dùng JWT_SECRET mặc định (ghi trong src/config.py _reject_insecure_jwt_secret_in_production).

### Vấn đề còn mở / chưa giải quyết

**Vấn đề của phiên bản hiện tại**

-  Gate UI_Review chưa phân biệt theo confidence thấp — graph.py:route_on_input() và frontend/src/app/patient/page.tsx đã có gate bắt buộc xem xét bản nháp OCR trước khi submit, nhưng không có logic riêng "độ tin cậy thấp → bắt buộc xác nhận thêm bước / hiển thị cảnh báo riêng" so với bản nháp confidence cao. Yêu cầu checklist ghi "độ tin cậy thấp → bắt buộc xác nhận, không tự động chuyển thẳng" — gate hiện tại áp dụng đồng đều cho mọi bản nháp OCR, không phân biệt theo confidence.

- PRD cập nhật phân loại OCR ("Cơ bản" hay "Nâng cao làm sớm") — không tìm thấy file PRD nào được tạo hoặc cập nhật trong V2 với nội dung này. ADR-006 có ghi lý do nhưng không thay thế được PRD.

- PRD ghi rõ các chỉ số mới chỉ có mức "abnormal" (trừ Kali có "critical") — không tìm thấy file PRD nào chứa tuyên bố này. Kickoff V2 có ghi kế hoạch nhưng không có artifact PRD thực tế.

- Test case tự động chưa đủ theo từng chỉ số mới riêng lẻ — có test_reference_range_checker_node.py và test_v2_analyte_manifest.py kiểm tra cơ chế lookup và danh sách approved/pending, nhưng không có test case riêng biệt theo từng chỉ số mới (HGB, HbA1c, LDL-C, HDL-C, Potassium) với giá trị cụ thể trên/dưới/bình thường như cam kết ở Handoff V1.

- Xác nhận triển khai (Deploy) thành công — hoàn tất việc cấu hình trên platform (Vercel cho frontend, Railway cho backend), URL và biến môi trường (CORS) được cài đặt trực tiếp trên hệ thống của platform nên không có trong code repo. Tuy nhiên, vẫn nên ghi chú URL thật vào `README.md` hoặc comment trong `.env.example` để team dễ theo dõi.

- Model Embedding quá nặng — theo phản hồi từ Duy, model BGE-M3 dùng cho Guardrail Semantic Similarity hiện tại quá nặng, gây crash backend nhiều lần trên môi trường free-tier (Railway/Render). Cần tìm model nhẹ hơn (ví dụ: `all-MiniLM-L6-v2`) hoặc chuyển sang gọi API ngoài để thay thế ở version sau.

- CORS vẫn trỏ localhost trong .env — .env cục bộ hiện tại CORS_ORIGINS=http://localhost:3000,http://localhost:5173. Code src/main.py đã có guard chặn wildcard và hướng dẫn trong .env.example yêu cầu ghi domain production. Môi trường production đã được set cứng trên nền tảng cloud, nhưng môi trường local vẫn cần lưu ý đồng bộ nếu test.

- Vũ duyệt code Tuấn nối 9 chỉ số vào graph — Vũ được giao vai trò "duyệt code Tuấn nối 9 chỉ số vào graph (giữ vai trò chốt kiến trúc)". Không tìm thấy bằng chứng review cụ thể trong commit history hay comment.

**Từ vấn đề mở V1 chưa được giải quyết trong V2**

- Unit Conversion động (mg/dL ↔ mmol/L) — Không làm, chủ đích dời sang V3 (ghi trong kickoff V2 mục 5).

- PHI de-identification trước khi vào AI Engine — Vẫn là open issue, V2 thêm auth (Duy) nhưng không có bước khử định danh PHI đầy đủ. Kickoff V2 mục 6 ghi rõ đây là ràng buộc an toàn bắt buộc trước khi go-live với dữ liệu thật.

- RAG ChromaDB — kho dữ liệu y khoa thực tế — RAGAS đã chạy với curated fixtures (không phải retrieved contexts từ production graph), report.md ghi rõ: "Results are not production RAG validation." Dữ liệu thật trong ChromaDB vẫn chưa được xác nhận chất lượng.

- LDL-C và Potassium (Kali) vẫn ở pending — 2 trong 3 chỉ số cốt lõi của V1 (LDL-Cholesterol, Kali) hiện bị quarantine và chưa vào được approved_analytes trong V2, vì range_flag != OK trong dữ liệu nguồn.




### Rủi ro cần lưu ý ở version tiếp theo
- LDL-C và Potassium quarantined — 2 chỉ số từ V1 đang bị chặn ở pending do chất lượng dữ liệu nguồn. Cần Dương review quarantine_v2.csv (theo phân công gốc) để quyết định có thể đưa lên approved hay không, hoặc tìm nguồn dữ liệu thay thế.

- OCR confidence gate chưa hoàn chỉnh — gate hiện đồng đều cho mọi bản nháp OCR, không tăng cường cảnh báo/chặn khi confidence thấp. Bản nháp OCR có confidence thấp có thể vào pipeline nếu người dùng xác nhận mà không đọc kỹ.

- RAGAS chưa đo trên production RAG — RAGAS V2 chạy trên curated fixtures, không phải retrieved contexts từ ChromaDB production. Hallucination risk khi RAG thật chưa được đo.

- Deploy production đã hoàn tất nhưng có rủi ro về tài nguyên — model Semantic Similarity (BGE-M3) quá nặng làm crash backend. Phải sớm thay model nhẹ hơn hoặc dùng API ngoài.

- PHI de-identification vẫn là lỗ hổng an toàn mở — nếu V3 bắt đầu nhận dữ liệu bệnh nhân thật, đây là ràng buộc an toàn bắt buộc phải đóng trước.

- HbA1c, LDL-C, HDL-C, HGB có trong explanations.json nhưng chưa vào được pipeline — sự không đồng bộ giữa explanations.json (9 chỉ số) và approved_analytes (5 chỉ số) có thể gây hiểu nhầm về khả năng thực sự của hệ thống.

### Trạng thái ràng buộc an toàn (guardrail)
Cơ chế hiện tại (V2):

1. Prompt-level (giữ từ V1): 

- src/agents/nodes/analyzer_node.py có prompt cấm suy đoán nguyên nhân, cấm chẩn đoán, cấm kê đơn.

2. Validator Node — Lớp kép (mới ở V2):

- Regex: RESTRICTED_KEYWORDS (L16-32) gồm 14 pattern (chẩn đoán bạn bị, kê đơn, uống thuốc, có thể do, nguyên nhân do...).

- Vector Semantic Similarity: FORBIDDEN_SAMPLE_SENTENCES (L35-42, 6 câu mẫu), embed bằng BGE-M3, cosine similarity > 0.85 → vi phạm. (get_forbidden_embeddings(), check_violation()).

- LLM Self-Correction Retry (mới ở V2): nếu vi phạm, rewrite_with_llm() (L55-77) / rewrite_questions_with_llm() (L79-103) gọi LLM viết lại 1 lần → quét lại. Nếu vẫn vi phạm sau rewrite → fallback template.

3. Template Library (mới ở V2): 

- data/reference/templates.json — fallback_explanation, fallback_summary, disclaimer, doctor_questions_fallback — dùng chung cho cả giải thích và câu hỏi kiểm duyệt. Load qua src/services/template_loader.py:load_templates() (cached bằng lru_cache).

4. UI-level (giữ từ V1): 

- Disclaimer cố định; Gate 3 Red Banner cho has_critical_values.

Chưa có (so với ADR-004 Lựa chọn 3): LLM-as-judge — chưa triển khai, theo đúng quyết định chốt trong kickoff V2.

### PLO đã chạm trong version này
- PLO2 (Kiến trúc & Framework AI) — Sâu: src/agents/graph.py mở rộng LangGraph với interrupt_before=["ui_review_gate"] và Conditional Entry Point route_on_input() — tích hợp Human-in-the-loop pattern. src/services/reference_repository.py (382 dòng) xây dựng lookup engine theo (analyte, sex, age_scope) với index, validation, và unit normalization. src/adapters/vision_adapter.py xây dựng Adapter mới song song với luồng JSON cũ mà không thay đổi graph core.

- PLO4 (An toàn & Đạo đức AI) — Rất Sâu: Guardrail nâng từ 1 lớp regex lên 3 cơ chế độc lập (regex + semantic similarity + LLM retry). Template Library tách nội dung an toàn ra khỏi code logic. Gate UI_Review ngăn dữ liệu OCR chưa kiểm tra lọt vào pipeline chính. Fail-fast JWT_SECRET trong production (src/config.py). Ẩn lỗi nội bộ khỏi API response (src/main.py). Chặn CORS wildcard khi allow_credentials=True.

- PLO5 (Giám sát & Đánh giá) — Bắt đầu: RAGAS eval đã chạy 1 lần thực tế với kết quả định lượng (Faithfulness 0.909, Context Precision 0.955 trên 4 analyte). Latency được ghi log server-side (elapsed_ms) làm baseline — chưa phải monitoring đầy đủ nhưng đã có cơ sở đo lường.

- PLO7 (Full-stack AI Deployment) — Sâu: JWT authentication hoàn chỉnh từ backend (bcrypt, jose) đến frontend (guard, redirect, token storage). railway.json + Dockerfile cho deploy backend. OCR API endpoint (POST /api/v1/ocr/upload) kết nối VLM qua OpenRouter. CORS guard chống misconfiguration trong production.

### Việc ưu tiên cho version tiếp theo
- Thay thế Model Embedding cho Guardrail — chuyển BGE-M3 sang model nhẹ hơn (ví dụ: `all-MiniLM-L6-v2`) hoặc dùng API ngoài để tránh crash backend trên môi trường Railway/Render free-tier.

- Xác nhận URL production thật của Railway (backend) và Vercel (frontend) — commit/ghi lại trong `.env.example` hoặc `README.md` để cả team nắm thông tin, dù biến môi trường đã được set trực tiếp trên cloud.

- Kiểm tra và xử lý file quarantine_v2.csv (Dương review theo phân công): quyết định số phận LDL-C và Potassium (Kali) — hoặc tìm nguồn dữ liệu mới range_flag=OK, hoặc chấp nhận để pending đến V4.

- Cập nhật PRD: ghi rõ OCR thuộc phạm vi "Cơ bản" hay "Nâng cao làm sớm", và ghi rõ mức phân loại (abnormal/critical) cho từng chỉ số mới theo cam kết V2.

- Nâng cấp Gate UI_Review: thêm phân biệt theo confidence — cảnh báo riêng hoặc chặn thêm bước xác nhận khi có chỉ số confidence < ngưỡng (ví dụ 0.7).

- RAGAS đo trên retrieved contexts thật từ ChromaDB production (không chỉ curated fixtures).

- Bổ sung test case theo từng chỉ số mới riêng lẻ (HGB, HbA1c, LDL-C, HDL-C, Potassium) với giá trị biên cụ thể.
Bắt đầu xây dựng bước khử định danh PHI trước khi dữ liệu vào AI Engine — bắt buộc trước khi nhận dữ liệu bệnh nhân thật.
Unit Conversion động (mg/dL ↔ mmol/L) — dời từ V1 và V2, cần ưu tiên nếu V3 bắt đầu nhận đầu vào từ nguồn đa đơn vị.