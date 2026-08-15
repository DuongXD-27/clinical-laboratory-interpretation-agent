# Câu hỏi gợi ý + Ghi chú lâm sàng của bác sĩ — bàn giao

Người thực hiện: Duy · Ngày: 13/08/2026 · Nhánh: `feature/v4-questions-and-doctor-notes`
Người nghiệm thu: Dương

Hai chức năng độc lập nhưng cùng gắn vào một phiếu xét nghiệm: câu hỏi gợi ý là
`<<extend>>` của luồng giải thích kết quả, ghi chú lâm sàng nằm trong luồng riêng
của vai bác sĩ. Một phiếu không có ghi chú vẫn là phiếu hoàn chỉnh.

## 0. Bốn điểm đã chốt trước khi làm

Hai tài liệu nghiệp vụ để ngỏ nhiều điểm, một số chốt ngược nhau. Bốn điểm dưới
đây quyết định code khác nhau nên được chốt trước:

| Điểm | Chốt | Hệ quả |
| --- | --- | --- |
| Cơ chế sinh câu hỏi | Bộ câu mẫu soạn sẵn, để sẵn chỗ cắm LLM cho version sau | Đầu ra cố định, test được bằng assert chính xác, không tốn lượt gọi LLM |
| Lưu câu hỏi nào | Lưu **cả bộ** sinh ra, thêm cờ `is_selected` cho câu bệnh nhân tick | Mở lại phiếu cũ thấy đúng bộ của lần đó; ghi chú (5) trong tài liệu nói ngược, không theo |
| Trigger "đã xem" | Bác sĩ **bấm nút riêng**, lưu dạng danh sách nhiều bác sĩ | Sơ đồ Luồng 1 vẽ tự động theo lượt mở trang; không theo, vì lướt qua/click nhầm sẽ báo sai cho bệnh nhân |
| Bác sĩ trả lời câu hỏi | Trả lời được từng câu trong app, bệnh nhân đọc được | Thêm `answer_text`, `answered_by_doctor_id`, `answered_at` |

## 1. Ba chỗ schema của Vũ chưa đỡ được, và cách xử lý

| Vấn đề | Xử lý |
| --- | --- |
| `doctor_notes.target_type` chỉ nhận `indicator` / `report_question`, không gắn được vào phiếu — trong khi nghiệp vụ quy định ghi chú thuộc về một phiếu | Thêm giá trị `target_type="report"` trỏ vào `lab_reports.id`. Thuần additive, **không đổi cột nào** |
| `report_questions.indicator_id` là NOT NULL, nên không lưu được câu dự phòng của Template Library (không gắn chỉ số nào) | Cho nullable |
| Không có chỗ lưu câu bệnh nhân tick, cũng không có chỗ lưu nội dung bác sĩ trả lời (`status` có `"answered"` nhưng không có trường nội dung) | Thêm `is_selected`, `display_order`, `answer_text`, `answered_by_doctor_id`, `answered_at` |

Thêm một bảng mới: `report_doctor_views (report_id, doctor_id, viewed_at)` với
`UNIQUE(report_id, doctor_id)`. Lưu dạng danh sách chứ không phải một cờ boolean
trên `lab_reports`, vì nếu bác sĩ A xem rồi bác sĩ B xem sau, một cờ chung sẽ mất
thông tin bác sĩ B từng xem.

`create_all()` không ALTER bảng đã tồn tại, nên `_upgrade_sqlite_schema()` được
mở rộng để thêm 5 cột trên cho DB cũ ở máy dev. `tests/test_db_schema.py` của Vũ
vẫn xanh, 10/10.

## 2. Chức năng 1 — câu hỏi gợi ý

Pipeline: `analyzer -> generate_questions -> guardrail -> END`. Node sinh câu hỏi
nằm **trước** guardrail vì guardrail phải là lớp cuối cùng cho mọi nội dung hiển
thị cho bệnh nhân (ADR-004).

Logic ở `src/services/question_templates.py`, node mỏng ở
`src/agents/nodes/question_generator_node.py`, bộ mẫu ở
`data/reference/question_templates.json` (9 chỉ số đã duyệt × 4 trạng thái, cộng
một mẫu trung tính cho chỉ số `unknown`).

| Tiêu chí | Quyết định | Test |
| --- | --- | --- |
| Sinh cho chỉ số nào | Chỉ `low`/`high`/`critical_*`. Chỉ số bình thường không sinh câu | `test_normal_indicator_gets_no_question` |
| Toàn bộ bình thường | Trả rỗng, **không** dùng bộ dự phòng | `test_all_normal_report_returns_empty_not_fallback` |
| Giới hạn | 5 câu cho abnormal/critical | `test_cap_is_five_questions_and_keeps_the_critical_ones` |
| Ưu tiên | Nguy kịch trước, rồi lệch xa nhất | `test_critical_indicators_come_before_abnormal_ones` |
| "Lệch xa nhất" đo thế nào | Tỉ lệ so với **độ rộng khoảng tham chiếu** — lệch một lần độ rộng = 1.0, so được giữa mmol/L và 10^9/L | `test_relative_deviation_normalises_across_units` |
| Tie-break | `analyte_id` rồi tên hiển thị, để thứ tự cố định giữa các lần chạy | `test_tie_break_is_stable_so_tests_can_assert_order` |
| Chỉ số `unknown` | **Mỗi chỉ số một câu riêng có nêu tên**, ngân sách riêng tối đa 2 câu, không chiếm suất trong 5 câu | `test_unknown_questions_do_not_crowd_out_real_abnormal_ones` |
| Tên chỉ số trong câu hỏi | Đúng tên bệnh nhân nhập, không phải mã chuẩn | `test_question_uses_the_name_the_patient_typed_not_the_canonical_id` |
| Ranh giới nội dung | Không mẫu nào chứa tên bệnh, tên thuốc, hay giả định đang điều trị | `test_no_shipped_template_contains_forbidden_content` |
| Lưu vào phiếu | Cả bộ, kèm cờ tick riêng | `test_whole_question_set_is_saved_with_the_report` |
| Guardrail chặn | Ghép lại theo số lượng; số lượng khác thì bỏ liên kết chỉ số chứ không đoán | `test_reconcile_drops_indicator_link_when_guardrail_swapped_the_whole_set` |

Câu mẫu trong wireframe màn 6 ("LDL cao có cần đổi thuốc không?") **không** được
dùng: nó giả định bệnh nhân đang dùng thuốc, thông tin hệ thống không có.
`test_no_shipped_template_contains_forbidden_content` chặn luôn cả class lỗi này.

### Nhánh guardrail cho câu hỏi lần đầu chạy với nội dung thật

Nhánh kiểm duyệt câu hỏi tồn tại từ V2 nhưng luôn nhận danh sách rỗng, nên chưa
có bằng chứng nào cho thấy nó đúng. Đã coi là code mới và kiểm từ đầu:
`test_shipped_questions_pass_guardrail_untouched` chứng minh câu sinh từ bộ mẫu
qua được guardrail nguyên văn, không bị thay bằng bộ dự phòng chung.

## 3. Chức năng 2 — ghi chú lâm sàng

| Tiêu chí | Quyết định | Test |
| --- | --- | --- |
| Ghi chú gắn vào đâu | Một phiếu cụ thể (`target_type="report"`), không gắn vào bệnh nhân nói chung | `test_doctor_note_is_saved_and_shown_to_the_patient` |
| Ai ghi được | Chỉ role `doctor`. Bệnh nhân đọc được nhưng không viết được | `test_patient_cannot_write_a_doctor_note` |
| **Không** qua guardrail | Câu "gợi ý rối loạn lipid máu, nên dùng thuốc theo chỉ định" được lưu nguyên văn | `test_doctor_note_is_not_filtered_by_guardrail` |
| Chỉ thêm, không sửa/xoá | Hai lần ghi ra hai bản ghi, mới nhất nằm trên; không có endpoint PATCH/DELETE | `test_notes_are_append_only_newest_first`, `test_there_is_no_endpoint_to_edit_or_delete_a_note` |
| Hệ thống không soạn hộ | Ô nhập bắt đầu trống, không gợi ý, không điền sẵn mẫu câu | (kiểm bằng đọc code — không có đường sinh nội dung nào) |
| Thời điểm ghi | Máy chủ đặt, không nhận từ body | `answered_at` / `created_at` đặt trong repository |
| `target_id` từ body | Bị bỏ qua với ghi chú mức phiếu, luôn lấy từ URL | `test_note_target_id_from_body_cannot_redirect_to_another_report` |
| Bệnh nhân khác | 404, không 403 | `test_patient_cannot_read_another_patients_notes` |
| Bác sĩ khác | Đọc được ghi chú của đồng nghiệp | `test_doctor_reads_notes_written_by_another_doctor` |
| Khách | 403 ở cả ghi chú và đánh dấu đã xem | `test_guest_cannot_reach_notes_or_review` |

### "Đã xem" tách khỏi "đã có ý kiến"

| Tiêu chí | Test |
| --- | --- |
| Phiếu mới: chưa xem, chưa có ghi chú | `test_a_fresh_report_is_neither_reviewed_nor_noted` |
| Bác sĩ đánh dấu đã xem mà không viết gì | `test_doctor_marks_reviewed_without_writing_a_note` |
| Bấm hai lần không sinh thêm dòng | `test_marking_reviewed_twice_does_not_duplicate_the_row` |
| Bác sĩ thứ hai xem không bị mất | `test_second_doctor_viewing_is_not_lost` |
| Phiếu có ghi chú thì hiển nhiên đã xem | `test_a_noted_report_counts_as_reviewed_without_pressing_the_button` |
| Bệnh nhân không tự đánh dấu được | `test_patient_cannot_mark_their_own_report_reviewed` |

## 4. Endpoint mới

```
POST /api/v1/history/{report_id}/questions/selection          patient
POST /api/v1/history/{report_id}/questions/{question_id}/answer  doctor
POST /api/v1/history/{report_id}/notes                        doctor
POST /api/v1/history/{report_id}/review                       doctor
```

Bất đối xứng theo role có chủ đích: bệnh nhân tick chọn, bác sĩ ghi chú và trả
lời. Cả bốn dùng chung `_load_report_for()` để không endpoint nào tự nghĩ ra luật
quyền riêng, và giữ đúng luật 404-thay-vì-403 của phần lịch sử.

## 5. Giao diện

| Màn | Thay đổi | File |
| --- | --- | --- |
| Bệnh nhân, sau kết quả | Màn 6 câu hỏi gợi ý: danh sách có ô tích, nút sao chép và in **chỉ áp dụng cho câu đã chọn** | `frontend/src/components/QuestionsForDoctorPanel.tsx` |
| Bệnh nhân, lịch sử | Khối "Ghi chú của bác sĩ" tách bạch bằng viền và màu riêng, kèm tên bác sĩ + thời điểm | `frontend/src/components/HistoryPanel.tsx` |
| Cả hai, danh sách phiếu | Nhãn trạng thái: chưa có bác sĩ xem / bác sĩ đã xem / đã có ý kiến bác sĩ | `HistoryPanel.tsx` |
| Bác sĩ, màn 9 | Ô ghi chú + nút Lưu ghi chú, nút Đánh dấu đã xem, danh sách câu bệnh nhân đã tick, ô trả lời từng câu | `HistoryPanel.tsx` |
| Bác sĩ, màn phân tích thử | **Gỡ** ô "Ghi chú lâm sàng (HITL)" + nút "Lưu Ghi Chú & Xác Nhận" | `frontend/src/app/doctor/page.tsx` |

Câu hỏi gợi ý chỉ hiện **sau khi Gate 3 được xác nhận**: danh sách câu hỏi phục
vụ một cuộc hẹn khám trong tương lai, còn cảnh báo nguy kịch yêu cầu hành động
ngay, nên không được đặt ở vị trí làm loãng cảnh báo.

### Vì sao gỡ nút "Lưu Ghi Chú & Xác Nhận" thay vì nối nó

Nút đó nằm trên màn bác sĩ tự phân tích dữ liệu mô phỏng. Phân tích của bác sĩ
không được lưu thành lịch sử bệnh nhân (`saved_report_id: null`), nên **không có
phiếu nào để gắn ghi chú vào** — không thể nối nút đó vào chức năng thật. Theo
Luồng 1 của tài liệu, ghi chú thuộc màn 9 mở từ danh sách phiếu, và đó là nơi đã
làm. Chỗ cũ giờ là một dòng chỉ đường sang đúng chỗ.

### Một lỗi sẵn có đã sửa nhân đây

`HistoryPanel` đang đọc `detail.patient_age` / `detail.patient_gender`, nhưng
schema sau khi gộp PR #42 đổi thành `patient_age_at_test` /
`patient_gender_at_test`. Màn chi tiết vì thế render ra "undefined tuổi". Đã sửa
type và chỗ đọc.

## 6. Kết quả kiểm

Chạy trên nhánh này:

- `pytest tests/ -q` → **449 passed, 0 failed** (387 trước khi làm; **+62 test mới**)
- `ruff check src/ tests/` → sạch
- `cd frontend && npm run lint` → sạch
- `cd frontend && npm run build` → thành công, TypeScript sạch
- `node --test src/lib/*.test.mjs` → 9 passed

Test mới chia theo file:

| File | Số test | Nội dung |
| --- | --- | --- |
| `tests/test_services/test_question_templates.py` | 22 | Logic sinh câu: ưu tiên, cap, chuẩn hoá độ lệch, tie-break, unknown, ranh giới nội dung |
| `tests/test_api/test_doctor_questions_and_notes.py` | 32 | Hai chức năng qua HTTP, gồm toàn bộ ma trận quyền |
| `tests/test_agents/test_question_generator_node.py` | 8 | Node, vị trí trong graph, nhánh guardrail cho câu hỏi |

## 7. Ba lỗi của bản gộp PR #42, phát hiện khi chạy app thật

Ba lỗi dưới đây **không do hai chức năng mới**. Chúng có sẵn trên `main` sau đợt
gộp và chỉ lộ ra khi mở app lên bấm thử — không test nào bắt được, vì test API
mock `routes.agent.ainvoke` và dùng file SQLite tạm mới, còn `page.tsx` thì không
có test nào.

| Lỗi | Biểu hiện | Đã xử lý |
| --- | --- | --- |
| `lab_reports` chưa migrate | `POST /analyze` trả 500: `table lab_reports has no column named patient_id`. DB local còn schema trước PR #42 (`patient_user_id`, `patient_age`), và `create_all()` chỉ tạo bảng thiếu chứ không ALTER bảng đã có | Sao lưu DB rồi để tạo lại. **Chưa sửa gốc** — cần quyết định viết migration hay bảo cả nhóm xoá DB local |
| Frontend đọc tên cột cũ | Màn chi tiết phiếu render "undefined tuổi" vì `HistoryPanel` đọc `detail.patient_age`, còn schema đã đổi thành `patient_age_at_test` | Đã sửa type và chỗ đọc |
| Mất `HistoryPanel` + guard phiên khách | Trang bệnh nhân không còn mục "Lịch sử xét nghiệm của tôi". Nặng hơn: guard là `getRole() !== "patient"` nên **phiên khách bị đá về `/`** — nút "Dùng thử với tư cách khách" thành vòng lặp chết, đúng tiêu chí đã pass nghiệm thu V3 | Đã thêm lại cả hai, kèm banner khách và nhãn "Thoát phiên khách" |

Nguyên nhân chung: `frontend/src/app/patient/page.tsx` là một trong 9 file
conflict của đợt gộp. Bản `refactor/patient-screen` (PR #36) được giữ và phần V3
thêm vào file đó bị bỏ. Trang bác sĩ và trang đăng nhập không bị ảnh hưởng — đã
kiểm từng chuỗi.

Điều cần nói với Dương: **bản gộp `main` chưa ai chạy thử trên trình duyệt.** Suite
387 test xanh không phát hiện được cả ba lỗi này.

## 8. Production đã chuyển sang Postgres (15/08)

Rủi ro số 1 ở mục dưới đã được xử lý. Tài liệu nghiệp vụ yêu cầu không phát hành
chức năng ghi chú trước khi dữ liệu được lưu bền vững; điều kiện đó giờ đã đạt.

`DATABASE_URL` trên Railway trỏ sang **Neon Postgres, region AWS Europe Central 1
(Frankfurt)**. Chọn Postgres ngoài thay vì Postgres của Railway vì hai lý do: nó
không ăn vào credit Railway đang cạn, và dữ liệu sống độc lập với host — nếu phải
đổi host thì chỉ trỏ host mới vào cùng `DATABASE_URL`.

**Không sửa dòng code nào.** Toàn bộ phần SQLite-only đã nằm sau `_is_sqlite`
guard (`PRAGMA foreign_keys`, `connect_args`, `_migrate_sqlite_schema()`), và
`psycopg2-binary` đã có trong `requirements.txt` từ trước. `create_all()` tạo đủ 9
bảng, `seed_demo_users()` chạy đúng trên Postgres.

Lưu ý cho người đọc code: `src/config.py` vẫn mặc định
`sqlite:///./data/app.db`. Đó chỉ là giá trị fallback cho máy dev — **production
không dùng SQLite nữa**.

### TC-02 lần đầu chạy thật trên production

Trước đây TC-02 chỉ pass ở local bằng `TestDatabase.restart()`, còn trên Railway
thì chắc chắn fail vì không có Volume. Đã kiểm bằng dữ liệu thật:

```
Tạo      đăng ký duy_pg_798176, phiếu #1, tick 1 câu hỏi,
         ghi chú bác sĩ, đánh dấu đã xem
Redeploy 55f978a9  BUILDING -> DEPLOYING -> SUCCESS
Sau đó   login lại 200
         1 phiếu còn nguyên, reviewed_by_doctor=True, has_doctor_notes=True
         2 câu hỏi, 1 câu vẫn được tick
         ghi chú còn đủ tên "bacsi" và mốc 2026-08-15T12:49:40
```

Với SQLite thì lần redeploy đó sẽ xoá sạch cả ba thứ trên.

### Hai điều về vận hành Railway

Credit còn **"20 days or $3.78"**. Đây là lý do build kích từ git push bị dừng ở
`NEEDS_APPROVAL` và phải bấm duyệt tay trên dashboard — hành vi mới, các bản
trước 12/08 vẫn tự chạy.

Redeploy kích từ CLI **không** đi qua cửa duyệt đó:

```bash
railway deployment redeploy -s vmec-05-api -e production -y
# thêm --from-source nếu muốn lấy commit mới nhất thay vì redeploy commit đang chạy
```

Dữ liệu giờ nằm ngoài Railway nên khi credit hết sẽ không mất gì, nhưng app vẫn
tắt. Việc xin credit thuộc BTC.

## 9. Rủi ro và điểm cần chốt còn lại

1. ~~**Chưa phát hành được lên production.**~~ **Đã xử lý 15/08, xem mục 8.** Production dùng Neon Postgres (Frankfurt), TC-02 đã chứng minh tài khoản, câu hỏi đã tick và ghi chú bác sĩ sống qua redeploy. Rủi ro còn lại không phải mất dữ liệu mà là credit Railway cạn.
2. **Xoá phiếu: hai tài liệu chốt ngược nhau.** Tài liệu câu hỏi nói cascade, tài liệu ghi chú nói có thể phải chặn xoá với phiếu đã có ghi chú. Hiện **chưa có endpoint xoá phiếu nào** nên chưa phải chọn. Hành vi thật của DB đã được ghi lại bằng test: câu hỏi cascade theo phiếu, còn ghi chú thì không (vì `target_id` không phải FK thật) nên sẽ thành mồ côi. Cần Dương chốt khi làm chức năng xoá.
3. **Sửa phiếu chưa xử lý.** Nếu sau này cho sửa giá trị (ví dụ sửa lỗi OCR làm đổi trạng thái), bộ câu hỏi cũ sẽ không còn khớp. Chưa có luật nào cho việc sinh lại.
4. **Chưa gộp nhóm chỉ số liên quan lâm sàng.** LDL, HDL và Cholesterol toàn phần cùng lệch sẽ sinh ba câu riêng, chiếm ba suất trong năm. Luật gộp cần đầu vào chuyên môn, thuộc miền của Dương.
5. **Mọi bác sĩ ghi được vào mọi phiếu.** Hệ thống không có khái niệm bác sĩ phụ trách. Giới hạn lại là một phần việc riêng, không nhỏ.
6. **Bộ câu mẫu chưa được duyệt nội dung.** 9 chỉ số × 4 trạng thái đã soạn nhưng chưa có ai ngoài tác giả đọc lại. Cần Dương và người phụ trách nội dung y khoa duyệt trước khi phát hành.
7. **Kỳ vọng thời gian phản hồi.** Khi bệnh nhân thấy nhãn "chưa có bác sĩ xem", họ sẽ chờ. Nếu không có bác sĩ nào phụ trách, nhãn đó tồn tại vĩnh viễn và tạo cảm giác bị bỏ rơi. Cách diễn đạt hiện tại là trung tính nhất có thể, nhưng vấn đề vận hành vẫn còn.
8. **Giao diện chưa ai click thử ngoài tác giả**, và nhánh này chưa deploy.
