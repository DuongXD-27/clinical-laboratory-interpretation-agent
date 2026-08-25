TASK_ID=APP-HELP-RAG-PHASE2
BRANCH=feature/app-help-rag
PR=(chưa mở — sẽ mở khi bạn xác nhận nội dung này)
BASE_MAIN_SHA=2da389b3e2d8553d63be73c2b8e5380345201bbd
HEAD_SHA=(cập nhật sau commit cuối cùng của Phase 2 — xem `git log -1`)

GOAL=Chatbot phải trả lời đúng câu hỏi "cách dùng app" (upload, lịch sử, xu hướng, OCR review, hồ sơ, cảnh báo, hỏi bác sĩ, nguồn tham chiếu, trợ lý) từ corpus thật của sản phẩm, tách biệt hoàn toàn khỏi RAG y khoa (medical_kb_v4), không được bịa route/nút không tồn tại.

SCOPE_DONE=
- Phase 1: corpus Markdown data/app_how_to_use/ (10 file) + FEATURE_INVENTORY.md + PROVENANCE_REPORT.md, viết từ code/route thật đã đọc trong repo.
- Phase 2: intent APP_HELP mới (IntentEnum), routing xác định (deterministic) chạy trước VIEW_HISTORY/ANALYZE_TREND để tránh nuốt nhầm; collection Chroma riêng app_help_kb_v1 (tách biệt medical_kb_v4); corpus builder + script ingest riêng; retriever dense-only fail-closed dưới ngưỡng; dispatcher trả lời trực tiếp từ chunk retrieve được (không qua LLM paraphrase, tránh hallucination); role-aware caveat khi bác sĩ hỏi flow chỉ-dành-bệnh-nhân; đã ingest thật (50 chunk) và tune ngưỡng bằng evidence thật (không đoán).

OUT_OF_SCOPE=
- Không sửa/không đụng RAG y khoa medical_kb_v4 hay pipeline liên quan.
- Không thêm chunk_id/source_id vào response payload công khai cho end-user (giữ nguyên convention hiện tại là chỉ trả về tiêu đề nguồn, không trả ID nội bộ) — nếu sản phẩm muốn hiển thị cho người dùng, đây là việc mới, cần quyết định riêng.
- Chưa tích hợp UI hiển thị nguồn/route trong khung chat frontend (ngoài field `sources` đã có sẵn từ trước).
- Chưa build một verifier bổ sung (vd LLM kiểm tra lại câu trả lời trước khi trả) — hiện chỉ dùng ngưỡng điểm + gợi ý feature xác định (xem RISKS).

FILES_CHANGED=
Backend:
- src/models/orchestrator_schemas.py — thêm IntentEnum.APP_HELP
- src/orchestrator/intent_router.py — thêm nhánh APP_HELP (deterministic, chạy trước VIEW_HISTORY), cập nhật prompt LLM fallback
- src/orchestrator/dispatcher.py — thêm _dispatch_app_help + đăng ký vào WORKFLOW_DISPATCH
- src/orchestrator/service.py — sửa lỗi: DispatchContext.message trước đây chỉ được set cho luồng provenance follow-up, khiến APP_HELP (và bất kỳ intent tương lai nào cần message thô) luôn nhận chuỗi rỗng; nay luôn truyền message
- src/config.py — thêm APP_HELP_* settings (collection/corpus_version/min_score/top_k riêng)
- src/services/app_help_corpus_builder.py — mới: parse Markdown + front-matter thành chunk theo section
- src/services/app_help_retriever.py — mới: dense-only retriever, strip_explicit_analyte, feature-hint xác định, fail-closed
- src/scripts/ingest_app_help_kb.py — mới: script ingest riêng cho collection app_help_kb_v1

Frontend:
- frontend/src/types/orchestrator.ts — thêm "APP_HELP" vào union OrchestratorIntent (chỉ thêm, không đổi hành vi)

Tests:
- tests/orchestrator/test_app_help.py — mới (AH-01→AH-07, AH-10→AH-12)
- tests/orchestrator/test_scope_guardrail.py — S-16/17/20/21 đổi SAFE_GENERAL→APP_HELP (đúng như docstring đã dự đoán từ trước); thêm AH-08/AH-09
- tests/orchestrator/test_contracts.py — cập nhật hợp đồng đóng băng IntentEnum (7→8 thành viên, có chủ đích)
- tests/test_services/test_app_help_corpus.py — mới, test corpus builder

Data/eval:
- data/app_how_to_use/*.md — 10 file corpus (Phase 1) + FEATURE_INVENTORY.md + PROVENANCE_REPORT.md
- data/app_how_to_use/app_help_kb_manifest.json — manifest sau khi ingest thật
- eval/app_help/adversarial_threshold_test.py — script đo ngưỡng (evidence-based, giống eval/rag/)
- eval/app_help/adversarial_threshold_evidence.md — kết quả đo, kèm phần "Caveats" trung thực
- eval/app_help/manual_demo.md — bằng chứng 5 câu hỏi bắt buộc (mục F)

Không đụng: gates.py (không cần sửa — out_of_scope_gate đã có sẵn allowlist cho câu hỏi app-help, xác nhận qua investigation + test), schemas DB, migrations, evaluators/golden của medical RAG.

DB_CHANGE=Không.
API_CHANGE=Không thêm/đổi REST endpoint. Response cho câu hỏi APP_HELP dùng lại đúng shape ExplanationDataPayload{explanation, sources} đã có.
FRONTEND_CHANGE=Chỉ thêm 1 giá trị union type (không đổi UI/logic).
BACKEND_CHANGE=Có — xem FILES_CHANGED.

TESTS_ADDED=
- tests/orchestrator/test_app_help.py (11 test: AH-01..AH-07 routing, AH-10/AH-12 fail-closed, AH-11 role-aware, disabled-fails-closed)
- tests/test_services/test_app_help_corpus.py (6 test: corpus builder)
- tests/orchestrator/test_scope_guardrail.py: +2 test (AH-08, AH-09), 4 test cập nhật assertion (S-16/17/20/21)
- tests/orchestrator/test_contracts.py: 1 test cập nhật (8 thành viên)

TESTS_RUN=
pytest tests/ -q --deselect tests/test_services/test_langfuse_tracing.py --deselect tests/test_services/test_langfuse_wire_masking.py
cd frontend && npm run lint

TEST_RESULTS=
- Backend: 1440 passed, 0 failed (9 test bị deselect là lỗi môi trường có sẵn từ trước — thiếu package `langfuse` trong venv, không liên quan thay đổi này, đã xác nhận bằng cách chạy full suite trước khi bắt đầu Phase 2 và thấy đúng 9 lỗi tương tự).
- Frontend lint: 0 lỗi, 1 warning không liên quan (HistoryPanel.tsx, có sẵn từ trước, không phải file tôi sửa).
- Frontend build: `next build` thành công, biên dịch + TypeScript check + generate 14 route đều pass.
- Frontend test: 56 passed, 0 failed.

MANUAL_PROBES=
Xem eval/app_help/manual_demo.md — 5 câu hỏi bắt buộc, chạy qua dispatcher thật (_dispatch_app_help) + retriever thật (Chroma collection app_help_kb_v1, embedding Gemini thật), có RETRIEVED_CHUNK_IDS/SOURCE_DOC/FINAL_RESPONSE/PASS-FAIL cho từng câu, không chỉnh sửa tay output.

KNOWN_LIMITATIONS=
1. Retrieval dựa trên embedding similarity đơn thuần cho các câu hỏi "app-shaped nhưng tính năng không tồn tại" (VD "xuất PDF ký số") có margin điểm khá hẹp (~0.02) so với câu hỏi thật — xem phần "Caveats" trong eval/app_help/adversarial_threshold_evidence.md. Corpus hiện che được nhiều case nhờ các mục "Không làm được gì?" đã viết kỹ ở Phase 1 (VD "xóa tài khoản", "đặt lịch hẹn bác sĩ" đều được trả lời đúng nhờ nội dung phủ định có sẵn), nhưng một câu hỏi về khả năng thật sự chưa được viết vào corpus vẫn có rủi ro fail-closed đúng cách chỉ nhờ ngưỡng, chưa có lớp verify thứ hai.
2. strip_explicit_analyte chỉ xử lý tên viết tắt kiểu ASCII (WBC, HbA1c...), chưa xử lý tên tiếng Việt có dấu (VD "bạch cầu") do bảng alias đã chuẩn hóa bỏ dấu còn message người dùng thì không — rủi ro thấp vì câu hỏi app-help thường dùng viết tắt.
3. Role field trong front-matter hiện chỉ có 2 giá trị "patient"/"doctor" (hoặc kết hợp) — chưa có test cho vai trò "guest" hỏi APP_HELP (khả năng cao vẫn hoạt động vì APP_HELP không cần current_report_ref, nhưng chưa viết test xác nhận tường minh).

RISKS=
- Thay đổi src/orchestrator/service.py (luôn truyền `message` vào DispatchContext) là thay đổi ở đường dẫn dùng chung cho MỌI intent, không riêng APP_HELP — đã chạy lại toàn bộ 1440 test sau thay đổi này để xác nhận không hồi quy, nhưng đây là file nhạy cảm (orchestrator core) nên cần review kỹ đặc biệt ở đây.
- FEATURE_HINTS trong app_help_retriever.py là danh sách cụm từ tường minh thủ công, cần cập nhật nếu intent_router.app_help_explicit_patterns đổi — hiện không tự đồng bộ giữa 2 nơi (chấp nhận trade-off vì tách biệt concern routing vs retrieval, nhưng là điểm cần lưu ý khi bảo trì).

HARD_EVAL=Chưa chạy scripts/run_response_quality_eval.py (thay đổi này không tác động response quality của luồng y khoa — chỉ thêm 1 intent mới hoàn toàn tách biệt — nhưng cần xác nhận với script thật trước khi merge nếu yêu cầu).
REGRESSION_STATUS=Không phát hiện hồi quy. Toàn bộ 1440 test trước đó đang pass vẫn pass sau thay đổi (baseline đo trước khi bắt đầu Phase 2 cũng có đúng 9 lỗi langfuse tương tự, không tăng thêm).

READY_FOR_REVIEW=NO
(Lý do: PR chưa mở, chưa merge; cần bạn xác nhận có muốn hiển thị RETRIEVED_CHUNK_IDS cho end-user hay giữ ẩn như hiện tại trước khi khóa scope. Về mặt kỹ thuật — code, test, build, lint — đã sẵn sàng.)

---

## Evidence chạy thật

```
git status --short
git diff --stat main...HEAD
pytest tests/ -q --deselect tests/test_services/test_langfuse_tracing.py --deselect tests/test_services/test_langfuse_wire_masking.py
# -> 1440 passed, 23 deselected

cd frontend && npm run lint
# -> 0 errors, 1 pre-existing warning (unrelated file)
cd frontend && npm run build
# -> Compiled successfully, TypeScript OK, 14/14 routes generated
cd frontend && npm run test
# -> tests 56, pass 56, fail 0
```

## Files Changed review (tự khai theo yêu cầu mục "Files Changed review")

- File nào chủ động sửa: xem FILES_CHANGED ở trên — mỗi dòng đều ghi lý do sửa ngay sau tên file.
- File nhạy cảm đã đụng: `src/orchestrator/service.py` (core dispatch path, sửa 1 dòng logic message-carrying + xoá 1 import không dùng), `src/orchestrator/dispatcher.py` (thêm handler mới + đăng ký vào WORKFLOW_DISPATCH, không sửa handler cũ), `src/orchestrator/intent_router.py` (thêm nhánh mới trước VIEW_HISTORY, rút gọn safe_general_patterns — không xoá logic nào, chỉ di chuyển cụm từ sang nhánh mới), `src/models/orchestrator_schemas.py` (thêm 1 giá trị enum).
- Có đụng gates.py: KHÔNG (đã xác nhận qua investigate + test AH-08/AH-09: out_of_scope_gate/medical_safety_gate chạy trước routing, không cần sửa).
- Có đụng dispatcher: CÓ (thêm handler mới, không sửa handler cũ).
- Có đụng schemas: CÓ (thêm 1 giá trị IntentEnum — đã cập nhật test hợp đồng đóng băng tương ứng).
- Có đụng migrations: KHÔNG.
- Có đụng reference data: KHÔNG (không sửa data/reference/*).
- Có đụng evaluators/golden: KHÔNG (không sửa gì trong eval/rag/, eval/reference-range-checker/, hay bất kỳ golden file y khoa nào).
