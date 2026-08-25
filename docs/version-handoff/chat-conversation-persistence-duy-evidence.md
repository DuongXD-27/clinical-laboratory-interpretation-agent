# Conversation Persistence & New Chat — Implementation Report

```
TASK_ID        = chat-conversation-persistence
BRANCH         = feature/chat-conversation-persistence
PR             = #87  https://github.com/AI20K-Build-Phase-Cohort-3/P-056/pull/87
BASE_MAIN_SHA  = cf4643000951ad30044425188d69851ee112ece5
HEAD_SHA       = 73eb16b9cec94f52a19e574c57e0c38c76e7027c
```

## GOAL

Chatbot đang có session/context runtime nhưng chưa phải trải nghiệm hội thoại
thật. Việc cần làm: hội thoại được lưu, tải lại trang vẫn thấy lịch sử, mỗi
cuộc trò chuyện có context riêng, và hội thoại thuộc đúng bệnh nhân đã xác thực.

## SCOPE_DONE

- Audit kiến trúc hiện tại (mục A dưới đây).
- Hai bảng mới `conversations` / `conversation_messages`, context nằm trên hàng
  hội thoại.
- Repository chuyên trách, enforce quyền sở hữu ở một chỗ duy nhất.
- Store gắn theo hội thoại, DB làm nguồn sự thật, thay cho store khoá theo
  bệnh nhân.
- 4 endpoint hội thoại + `conversation_id` trên hai endpoint chat.
- Frontend: danh sách hội thoại, nút New Chat, nạp lại transcript khi vào trang.
- 25 test backend cho CP-01..CP-12, 10 test frontend cho phần logic thuần.

## OUT_OF_SCOPE

- Xoá / đổi tên hội thoại. Chưa ai yêu cầu, và xoá là hành động không hoàn lại
  nên cần bàn riêng.
- Tìm kiếm trong transcript.
- Hội thoại cho bác sĩ. V1 không có khái niệm này; mở cửa bây giờ là thêm một ô
  trống vào ma trận quyền.
- Đổi tên miền sang `lumilab.vercel.app` — việc riêng, đang bị chặn vì tên đó
  thuộc tài khoản Vercel khác.

## DB_CHANGE / API_CHANGE / FRONTEND_CHANGE / BACKEND_CHANGE

Bốn trường này để riêng thành một khối để soi nhanh; chi tiết ở các mục A–D bên dưới.

```
DB_CHANGE       = THÊM 2 bảng: conversations, conversation_messages.
                  0 cột thêm vào bảng cũ, 0 rename, 0 đổi kiểu, 0 drop.
                  2 index compound + 2 index FK. Chi tiết: mục A và C.

API_CHANGE      = THÊM 4 endpoint dưới /api/v1/conversations (POST, GET,
                  GET /{id}, GET /{id}/messages).
                  SỬA: + conversation_id (optional) trên OrchestratorRequest.
                  KHÔNG đổi OrchestratorResponse — một trường cũng không.
                  Chi tiết: mục B.

FRONTEND_CHANGE = 6 file. Danh sách hội thoại + nút New Chat trong ChatPanel;
                  useOrchestratorChat giữ conversationId, nạp lại transcript
                  khi vào trang; api.ts thêm 3 hàm + gửi conversation_id;
                  conversationTranscript.mjs (logic thuần) + test;
                  AssistantTurn vẽ lượt dựng lại; CSS cho danh sách.

BACKEND_CHANGE  = conversation_repository (nơi DUY NHẤT enforce sở hữu);
                  ConversationScopedSessionStore kế thừa InMemorySessionStore,
                  chỉ đổi khoá + lưu DB, giữ nguyên logic chuyển trạng thái;
                  handle_message được bọc thêm lớp gắn hội thoại + ghi
                  transcript, lõi cũ đổi tên thành _handle_message_core với
                  nội dung nguyên vẹn; acknowledge_onboarding nhận db +
                  conversation (xem RISKS — chỗ này từng hỏng thật).
```

---

## A. Architecture note

### Audit: hiện trạng trước khi sửa

| Thứ | Trạng thái trước | Vấn đề |
| --- | --- | --- |
| `InMemorySessionStore` | khoá `patient:{user_id}` | **một bệnh nhân = đúng một context vĩnh viễn** |
| `current_analyte` | trong context đó | New Chat không xoá được, vì không có chỗ nào để xoá |
| Transcript | không lưu ở đâu cả | F5 là mất trắng |
| `OrchestratorRequest` | không có `conversation_id` | client không có cách nói nó đang ở hội thoại nào |
| `patient_id` | từ claim `uid` trong JWT | phần này đã đúng, giữ nguyên |

Hệ quả cụ thể của dòng đầu: hỏi WBC ở "hội thoại 1" đặt `current_analyte="WBC"`;
bấm New Chat chỉ xoá giao diện; hỏi "chỉ số này" ở "hội thoại 2" vẫn resolve ra
WBC. Đúng là kịch bản CP-05 trong đề bài.

### Model dữ liệu

```
users (1) ──< (n) conversations (1) ──< (n) conversation_messages
```

```python
class Conversation:
    id                      Integer  PK
    patient_id              Integer  FK users.id ON DELETE CASCADE, NOT NULL, indexed
    title                   String(200)  nullable   # rút từ câu hỏi đầu tiên
    created_at              DateTime NOT NULL
    updated_at              DateTime NOT NULL (onupdate)
    # --- context của riêng hội thoại này ---
    onboarding_acknowledged Boolean  NOT NULL default False
    current_report_ref      String(64)  nullable
    current_analyte         String(64)  nullable
    last_intent             String(64)  nullable
    pending_question        String(64)  nullable
    pending_question_at     Float       nullable
    expected_entity         String(64)  nullable
    Index("ix_conversations_patient_id_updated_at", patient_id, updated_at)

class ConversationMessage:
    id              Integer PK
    conversation_id Integer FK conversations.id ON DELETE CASCADE, NOT NULL, indexed
    role            String(16) NOT NULL      # "user" | "assistant"
    content         Text       NOT NULL      # văn bản ĐÃ qua guardrail
    created_at      DateTime   NOT NULL
    intent          String(64)  nullable
    reason_code     String(64)  nullable
    data_type       String(32)  nullable
    Index("ix_conversation_messages_conversation_id_id", conversation_id, id)
```

Đề bài gợi ý `owner_user_id`; ở đây dùng `patient_id`, khớp với
`lab_reports.patient_id` đã có. Cùng một khái niệm, đặt tên cho nhất quán với
schema hiện hành thay vì thêm cách gọi thứ hai.

### Ba lựa chọn cần giải thích

**1. Vì sao context nằm TRÊN hàng Conversation, không ở bảng riêng.**

Vì như vậy **New Chat = hàng mới = context rỗng theo cấu trúc**. Không có bước
"xoá context cũ" nào để mà quên gọi, và không có đường nào để context của hội
thoại 1 chảy sang hội thoại 2 — hai hội thoại đọc hai hàng khác nhau. Đây là
khác biệt giữa "nhớ reset state" và "không có state để mà quên reset"; cách thứ
hai không hỏng được.

Vòng đời của các trường này cũng TRÙNG với vòng đời hội thoại: sinh ra cùng
nhau, chết cùng nhau, không bao giờ chia sẻ. Đó là định nghĩa của một cột trên
chính bảng đó.

**2. Vì sao `conversation_messages` KHÔNG có `patient_id`.**

Quyền sở hữu **suy ra** qua `conversation_id`. Lặp lại `patient_id` ở đây là tạo
hai nguồn sự thật có thể lệch nhau — lúc đó câu hỏi "tin nhắn này của ai" có hai
câu trả lời khác nhau, và không có cách nào biết cái nào đúng.

**3. Vì sao `content` chỉ lưu văn bản, không lưu payload có cấu trúc.**

Đánh đổi có chủ ý, và nó có cái giá — nêu ở KNOWN_LIMITATIONS:

- Lưu nguyên payload JSON là nhân đôi giá trị xét nghiệm sang một chỗ nữa, trong
  khi `report_indicators` đã giữ chúng.
- Schema payload có `extra="forbid"`. Một payload lưu từ bản cũ, sau khi schema
  đổi, sẽ không validate được nữa — và cả cuộc trò chuyện thành **không mở được
  nữa**. Văn bản thì không bao giờ hết hạn.

Và chỉ lưu bản **đã qua guardrail**: đọc lại lịch sử phải thấy đúng thứ đã hiện
trên màn hình, không thấy thứ hệ thống đã cố ý chặn.

### Bốn câu hỏi đề bài yêu cầu trả lời rõ

**Conversation ownership được enforce ở đâu?**

`src/services/conversation_repository.py`, và chỉ ở đó. **Mọi hàm đọc hoặc ghi
đều nhận `patient_id` tường minh**; không hàm nào tra Conversation chỉ bằng
`conversation_id`. Cùng khuôn với `history_repository` và vì cùng lý do: nếu tồn
tại một hàm `get(conversation_id)` không kèm chủ sở hữu thì sớm muộn có route gọi
nó và quên lọc.

`append_message` nhận **đối tượng** `Conversation`, không nhận id — muốn ghi thì
phải có trong tay một hàng lấy từ `get_conversation`, tức đã qua cửa
`patient_id`. Nhận id thì hàm này lại thành đường vòng bỏ qua kiểm quyền.

**Message ownership được suy ra thế nào?**

`list_messages` gọi `get_conversation(patient_id=...)` trước; không qua thì trả
`None` và route trả 404. Không có truy vấn nào chạm `conversation_messages` mà
không đi qua cửa đó.

**Server lấy user_id từ JWT ở đâu?**

`get_current_user` (`src/api/deps.py`) → claim `uid` đã kiểm chữ ký →
`current_user.user_id`. `require_roles(ROLE_PATIENT)` chặn khách/bác sĩ/admin
trước khi route chạy. `_patient_id()` trong `conversation_routes.py` kiểm lại
`uid` là `int` và trả 401 nếu không — token ký trước V3 không có claim đó, và nó
không được phép biến thành `patient_id=None` rồi ghi bậy.

**Không có chỗ nào đọc `patient_id` từ thân request.** `conversation_id` client
gửi lên chỉ là *gợi ý về hội thoại*, không phải bằng chứng sở hữu: nó luôn được
tra kèm `patient_id` lấy từ token, nên gửi id của người khác ra 404.

**New Chat reset context bằng cơ chế gì?**

Bằng việc **không reset gì cả**. `POST /conversations` tạo một hàng mới; các cột
context của hàng mới là NULL vì chưa ai ghi vào đó. Store đọc context từ đúng
hàng đang nói chuyện, nên hội thoại mới đọc ra rỗng.

**Một ngoại lệ duy nhất: `onboarding_acknowledged` được kế thừa.** Xác nhận "tôi
đã đọc hướng dẫn" là thuộc tính của NGƯỜI, còn `current_analyte` là thuộc tính
của CUỘC TRÒ CHUYỆN. Bắt bệnh nhân bấm lại "Tôi đã hiểu" mỗi lần mở hội thoại
mới là biến một cam kết an toàn thành cái nút bấm cho qua, tức làm nó mất tác
dụng. Kế thừa ngữ cảnh y khoa thì trực tiếp gây trả lời sai — đó mới là thứ phải
chặn. Test `test_new_chat_does_not_ask_for_onboarding_again` khẳng định cả hai
nửa: onboarding kế thừa, `current_analyte`/`current_report_ref` thì không.

### Store: kế thừa chứ không viết lại

`ConversationScopedSessionStore(InMemorySessionStore)` chỉ ghi đè hai thứ:
**khoá** (`conv:{id}` thay cho `patient:{uid}`) và **việc lưu xuống DB**. Toàn bộ
logic chuyển trạng thái (`update_after_turn`, `activate_report`,
`replace_pending_review`) giữ nguyên — nó rất tinh vi (quyết định khi nào xoá
`current_analyte`, khi nào giữ) và đang được cả bộ test orchestrator bảo vệ. Viết
lại là viết lại cả những quyết định đó. Vì mọi method dẫn xuất đều gọi
`self.get_or_create()` và `self.save()`, chúng tự động thành gắn-theo-hội-thoại
mà không sửa dòng nào.

**Đọc lại từ hàng DB ở MỖI lượt, không phải chỉ khi cache RAM truợt.** Bản đầu
tôi viết cache-first, rồi nhận ra như vậy "tải lại trang" chẳng chứng minh được
gì: context còn vì nó nằm trong tiến trình, không phải vì nó đã được lưu. Và ở
production nhiều worker thì lượt sau rơi vào worker khác là mất ngữ cảnh — đúng
loại lỗi mà checkpointer in-memory của graph đang mắc.

Hai trường **không** có cột DB và không nên có: `pending_ocr_review` và
`transient_ui_context`. Bản nháp OCR chờ duyệt sống trong checkpointer
in-memory, nên lưu con trỏ tới nó xuống DB là tạo một con trỏ treo sau khi
restart. Chúng đi theo `carry` — vẫn trong tiến trình, đúng như trước.

`bind_conversation(db, conversation)` là context manager, gắn cho suốt một lượt.
Dùng contextvar chứ không thêm tham số vào mười method của store: làm vậy phải
sửa mọi chỗ gọi trong `service.py`, là vùng code của người khác. Repo đã có tiền
lệ đúng khuôn — `request_timing` cũng gắn theo request bằng contextvar.

---

## B. API contract

Tất cả dưới `/api/v1`. Auth: `Authorization: Bearer <JWT>`.

| Method | Path | Role | Input | Output |
| --- | --- | --- | --- | --- |
| POST | `/conversations` | patient | `{title?}` | 201 `ConversationSummary` |
| GET | `/conversations` | patient | `?limit=50&offset=0` | 200 `{items[], total}` |
| GET | `/conversations/{id}` | patient | — | 200 `{conversation, messages[]}` |
| GET | `/conversations/{id}/messages` | patient | — | 200 `ConversationMessage[]` |
| POST | `/orchestrator/message` | patient, guest | `+ conversation_id?` | không đổi |
| POST | `/orchestrator/message/stream` | patient, guest | `+ conversation_id?` | không đổi |
| POST | `/orchestrator/onboarding/acknowledge` | patient, guest | — | không đổi |

### Semantics

- **401** — không có token, token hỏng, hoặc token thiếu claim `uid` (ký trước V3
  → buộc đăng nhập lại thay vì đoán bừa chủ sở hữu).
- **403** — role không được phép. Khách nhận kèm lời mời đăng ký, giống
  `/history`. Bác sĩ và admin cũng 403: V1 không có hội thoại của họ.
- **404** — hội thoại không tồn tại **hoặc** không thuộc người gọi. Hai trường
  hợp không phân biệt được từ bên ngoài, có chủ ý: 403 sẽ xác nhận id đó tồn
  tại, đủ để dò ra hội thoại của bệnh nhân khác bằng cách thử id. Cùng quy tắc
  đã áp cho `/history/{report_id}`.
- **422** — `conversation_id` không phải số nguyên.

### Ownership behavior

`patient_id` **luôn** từ token. Gửi `conversation_id` của người khác:

- đọc → 404, không lộ một chữ nào của nội dung;
- chat vào → 404, và **không có tin nhắn nào được ghi** (chặn cả chiều ghi, vì
  chỉ chặn đọc thì A vẫn chèn được lượt vào hội thoại của B, hỏng nặng hơn).

### Tương thích ngược

`conversation_id` là **optional**. Bản frontend đã deploy gọi
`/orchestrator/message` không kèm id và phải tiếp tục chạy — bắt buộc trường mới
là làm sập production ngay lúc backend lên trước frontend. Thiếu id thì server
dùng hội thoại gần nhất, tạo mới nếu chưa có.

`OrchestratorResponse` **không đổi một trường nào** — có ý: các golden chất lượng
phản hồi khoá cứng hợp đồng đó. Client biết `conversation_id` qua
`POST /conversations` và `GET /conversations`.

### Không chấp nhận

Đề bài nêu rõ không chấp nhận frontend gửi `{"patient_id": 123}` rồi backend tin.
Không có endpoint nào ở đây nhận `patient_id` từ client. `grep -rn "patient_id"
src/api/conversation_routes.py` chỉ ra các chỗ lấy từ `current_user`.

---

## C. Migration / DB evidence

```
migration mechanism   = mechanism sẵn có của repo: create_all() +
                        add_missing_columns() + add_missing_indexes(),
                        đều suy từ Base.metadata. KHÔNG thêm Alembic.
backward compatibility= chỉ THÊM 2 bảng và 0 cột vào bảng cũ. Không rename,
                        không đổi kiểu, không drop.
fresh DB PASS         = có — mỗi test có SQLite tạm mới, 25/25 xanh.
existing DB PASS      = có — create_all() tạo bảng còn thiếu; hai bảng mới
                        không tồn tại trên DB cũ nên được tạo nguyên vẹn cùng
                        index. Không bảng cũ nào bị ALTER.
```

Vì hai bảng hoàn toàn mới, đây là trường hợp `create_all()` xử lý đúng — khác
với vụ `report_indicators.critical_status` từng 500 production, ở đó cột được
thêm vào một bảng đã tồn tại. `add_missing_indexes()` phủ nốt phần index nếu ai
đó đã tạo bảng bằng tay trước.

**Không tự nhét framework migration mới vào giữa task**, đúng yêu cầu.

---

## FILES_CHANGED — tự khai

### File mới (chủ động tạo)

| File | Vì sao |
| --- | --- |
| `src/services/conversation_repository.py` | nơi duy nhất enforce quyền sở hữu |
| `src/models/conversation_schemas.py` | hợp đồng API phần quản lý hội thoại, tách khỏi hợp đồng một lượt chat |
| `src/api/conversation_routes.py` | 4 endpoint + `resolve_conversation` dùng chung |
| `tests/test_api/test_conversation_persistence.py` | CP-01..04, 06..10 + hồi quy onboarding |
| `tests/orchestrator/test_conversation_context_isolation.py` | CP-05, CP-11, CP-12 |
| `frontend/src/lib/conversationTranscript.mjs` | logic thuần: transcript → lượt |
| `frontend/src/lib/conversationTranscript.test.mjs` | 10 test cho file trên |

### File sửa (chủ động sửa)

| File | Sửa gì | Nhạy cảm? |
| --- | --- | --- |
| `src/models/db.py` | +119 dòng, **0 xoá** — thêm 2 model | schema — chỉ thêm bảng |
| `src/orchestrator/session_store.py` | thêm store gắn theo hội thoại; `InMemorySessionStore` **không đổi một dòng** | có — đọc kỹ mục A |
| `src/orchestrator/service.py` | bọc `handle_message`; lõi cũ đổi tên thành `_handle_message_core`, **nội dung nguyên vẹn**; `acknowledge_onboarding` nhận `db`/`conversation` | có |
| `src/api/orchestrator_routes.py` | giải hội thoại rồi truyền xuống | — |
| `src/orchestrator/streaming.py` | +4 dòng, chuyền `conversation` qua | — |
| `src/models/orchestrator_schemas.py` | +1 trường optional trên `OrchestratorRequest`; `OrchestratorResponse` **không đổi** | có — nhưng không chạm response |
| `src/main.py` | +2 dòng đăng ký router | — |
| `tests/conftest.py` | fixture autouse xoá cache store giữa các test | — |
| frontend (6 file) | danh sách hội thoại, New Chat, nạp lại transcript | — |

### Có đụng những file bị cấm không?

| Yêu cầu | Trả lời |
| --- | --- |
| `gates.py` | **không** — `git diff` không có file này |
| medical safety gates | **không** |
| Reference Checker / Critical Detector | **không** |
| G1 provenance | **không** |
| HAL-039 | **không** |
| G2 | **không** |
| RAG medical | **không** |
| frozen response-quality goldens | **không** — `eval/` không xuất hiện trong diff |
| reference data | **không** — `data/` không xuất hiện trong diff |
| evaluators | **không** — `scripts/run_response_quality_eval.py` không sửa |
| migrations | không có framework migration nào trong repo; dùng mechanism sẵn có |
| dispatcher | **không** |
| schemas | có, chỉ THÊM: 1 trường optional trên request + 1 file schema mới |

**Không sửa golden hay evaluator để làm test xanh.** Cách kiểm: `git diff
--cached --stat` không liệt kê `eval/`, `data/`, `scripts/`.

---

## D. Test bắt buộc — CP-01..CP-12

### TESTS_ADDED

Backend, 25 test:

| CP | Test | Kiểm gì |
| --- | --- | --- |
| CP-01 | `test_cp_01_patient_creates_conversation_and_it_is_saved` | tạo → lưu → thấy trong danh sách |
| CP-02 | `test_cp_02_messages_are_persisted_with_both_roles` | cả hai lượt được lưu, kèm metadata |
| CP-02 | `test_cp_02_first_question_becomes_the_title` | câu đầu đặt tên, câu sau không đổi tên |
| CP-03 | `test_cp_03_transcript_survives_a_backend_restart` | **qua `test_db.restart()`** |
| CP-04 | `test_cp_04_new_chat_creates_a_second_conversation_with_empty_transcript` | hội thoại B trống |
| **CP-05** | `test_cp_05_new_chat_starts_with_a_structurally_empty_context` | B rỗng, **A vẫn còn** (đối chứng) |
| **CP-05** | `test_cp_05_referential_question_in_a_new_chat_must_not_resolve_wbc` | đúng kịch bản đề bài |
| **CP-05** | `test_cp_05_end_to_end_new_chat_asks_which_indicator` | qua cả `handle_message` |
| **CP-05** | `test_cp_05_isolation_holds_between_two_different_patients` | context không qua ranh giới tài khoản |
| CP-06 | `test_cp_06_switching_back_restores_the_right_transcript` | quay lại A đúng nội dung A |
| **CP-07** | `test_cp_07_patient_a_cannot_read_patient_b_conversation` | 404, không lộ nội dung |
| **CP-07** | `test_cp_07_patient_a_cannot_chat_into_patient_b_conversation` | chặn cả chiều **ghi** |
| **CP-08** | `test_cp_08_patient_a_cannot_read_patient_b_messages` | 404 + **đối chứng chính chủ đọc được** |
| CP-09 | `test_cp_09_unknown_conversation_id_fails_closed` | 404 cả đọc và chat; 422 khi sai kiểu |
| CP-09 | `test_cp_09_unauthenticated_access_is_401` | không token → 401/403 |
| CP-10 | `test_cp_10_guest_gets_no_persistence_and_is_invited_to_register` | khách chat được, 403 ở `/conversations` |
| CP-10 | `test_cp_10_guest_chat_writes_no_conversation_row` | **đếm hàng DB = 0** |
| CP-10 | `test_cp_10_doctor_has_no_conversation_area` | bác sĩ 403, không phải 200-rỗng |
| **CP-11** | `test_cp_11_provenance_followup_still_works_inside_one_conversation` | chuỗi CRQ-014 2 lượt, **có `store.reset()` ở giữa** |
| **CP-11** | `test_cp_11_provenance_followup_does_not_leak_into_a_new_chat` | cùng câu hỏi ở hội thoại mới không trả về WBC |
| **CP-12** | `test_cp_12_doctor_question_followup_still_works_inside_one_conversation` | HAL-039 vẫn định tuyến đúng qua context lấy từ DB |
| — | `test_context_round_trips_through_the_database_without_loss` | mắt xích CP-03/11/12 dựa vào, kiểm riêng |
| — | `test_backward_compatible_request_without_conversation_id_still_works` | client cũ không 422, và 2 lượt vào **cùng** một hội thoại |
| — | `test_onboarding_acknowledgement_lands_on_the_conversation` | hồi quy lỗi thật, xem RISKS |
| — | `test_new_chat_does_not_ask_for_onboarding_again` | onboarding kế thừa, context thì không |

Frontend, 10 test (`node --test`): ghép lượt, câu hỏi chưa có trả lời, trả lời
không có câu hỏi, hai trả lời liền nhau, dữ liệu méo, transcript rỗng, nhãn hội
thoại, mở lại đúng hội thoại cũ, id đã cũ rơi về hội thoại mới nhất, danh sách
rỗng.

### Hai nguyên tắc đã áp khi viết test

**Mỗi khẳng định phủ định có một vế đối chứng.** "Không resolve ra WBC" cũng xanh
khi bộ giải context hỏng hoàn toàn. Nên CP-05 khẳng định thêm: **cùng câu hỏi
đó, trong hội thoại A, PHẢI ra WBC**. CP-08 khẳng định thêm: **chính chủ đọc
được**. Thiếu vế đó thì test chứng minh được rất ít.

**Phiếu dùng cho CP-05 có HAI chỉ số bất thường**, nên bản thân phiếu không đủ để
suy ra chỉ số nào — con đường duy nhất để ra WBC là thừa hưởng từ hội thoại 1.
Một phiếu chỉ có WBC bất thường sẽ resolve ra WBC một cách hợp lệ, và test sẽ
đo hộ thứ khác.

### TESTS_RUN / TEST_RESULTS

```
pytest tests/test_api/test_conversation_persistence.py
pytest tests/orchestrator/test_conversation_context_isolation.py
                                                    -> 25 passed

pytest tests/orchestrator -q   -> 398 passed, 1 failed, 1 error  (cả 2 đỏ sẵn trên main)
pytest tests/ -q               -> 1473 passed, 1 failed, 3 errors (cả 4 đỏ sẵn trên main)

ruff check src/ tests/   -> 104 errors trên HEAD
                            104 errors trên main (cf46430) — cùng con số,
                            KHÔNG có lỗi nào trong file tôi thêm/sửa.

cd frontend
npm run lint   -> PASS, 0 problem
npm run build  -> PASS
node --test src/lib/*.test.mjs -> 68 passed (10 mới)
```

`npm test` vẫn hỏng trên Node 22.14 (`--test-isolation=none` bị từ chối) — lỗi
sẵn có, không phải của task này. Chạy `node --test src/lib/*.test.mjs` **từ
`frontend/`**.

### REGRESSION_STATUS

Bốn test đỏ ở lần chạy đầu, và tôi đã soi từng cái thay vì báo gộp:

| Test | Kết luận |
| --- | --- |
| `test_conversational_independence::test_stale_pending_question_expiration` | **đỏ sẵn trên main** (đã kiểm bằng `git stash`) — không phải của tôi |
| 3 ERROR: `test_orchestrator_core::test_ac12...`, `test_request_tracing::test_orchestrator_log_shares...`, `test_ocr::test_trace_contains...` | **đỏ sẵn trên main** |
| `test_tip006_e2e_c_patient_analysis_persistence_and_history` | **lỗi của tôi**, đã sửa |
| `test_tip006_e2e_f_unsafe_requests_use_bounded_orchestrator_response` | **lỗi của tôi**, đã sửa |

---

## E. Manual demo / MANUAL_PROBES — runtime thật, không phải ảnh IDE

Backend chạy thật trên `127.0.0.1:8123`, DB SQLite riêng (`data/e2e_probe.db`,
đã xoá sau khi đo), LLM thật. Toàn bộ qua `curl`.

### Vòng 1 — CP-01..CP-10 qua HTTP

| Bước | Input | Output thật | Expected | Kết quả |
| --- | --- | --- | --- | --- |
| CP-01 | `POST /conversations` (A) | `{"id":1,"title":null,...}` | 201, có id | **PASS** |
| onboarding | `POST /orchestrator/onboarding/acknowledge` | `HTTP 200` | 200 | **PASS** |
| CP-02 | `POST /orchestrator/message` `{msg, conversation_id:1}` | `intent=EXPLAIN_CURRENT_RESULT` | không bị chặn onboarding | **PASS** |
| CP-03 | `GET /conversations/1` | `title="Giai thich chi so WBC cua toi"`, 2 tin: `user` + `assistant` | transcript đủ, tiêu đề rút từ câu đầu | **PASS** |
| CP-04 | `POST /conversations` | `id=2`, `so tin nhan = 0` | hội thoại mới, transcript trống | **PASS** |
| CP-06 | `GET /conversations/1` sau khi sang 2 | `2 tin`, tin đầu đúng nội dung cũ | transcript của 1 nguyên vẹn | **PASS** |
| CP-07 | `GET /conversations/1` bằng token B | `HTTP 404` + `{"detail":"Không tìm thấy cuộc trò chuyện."}` | chặn, không lộ nội dung | **PASS** |
| CP-07b | B chat vào hội thoại 1 của A | `HTTP 404`; A vẫn đúng **2 tin** | chặn cả chiều ghi | **PASS** |
| CP-08 | `GET /conversations/1/messages` bằng token B | `HTTP 404` | chặn | **PASS** |
| CP-08 đối chứng | cùng URL, token A | `HTTP 200` | chính chủ đọc được | **PASS** |
| CP-09 | `GET /conversations/999999` | `HTTP 404` | fail closed | **PASS** |
| CP-09 | `POST message` `conversation_id:999999` | `HTTP 404` | không âm thầm rơi về hội thoại khác | **PASS** |
| CP-09 | `GET /conversations` không token | `HTTP 401` | 401 | **PASS** |
| CP-10 | `GET /conversations` token khách | `HTTP 403` | 403 | **PASS** |
| CP-10 | `POST /orchestrator/message` token khách | `HTTP 200` | khách vẫn chat được | **PASS** |
| CP-10 | `POST onboarding/acknowledge` token khách | `HTTP 200` | không hỏng với khách | **PASS** |

Danh sách hội thoại của A cuối vòng: `total = 2`, sắp mới-trước
(`2 | Giai thich ky hon chi so nay`, `1 | Giai thich chi so WBC cua toi`).

### Vòng 2 — CP-05, có vế đối chứng

Vòng 1 chưa chứng minh được CP-05: bệnh nhân A chưa có phiếu nào, nên "chỉ số
này" ở đâu cũng ra `AMBIGUOUS_CONTEXT` — tức "không carry WBC" xanh vì lý do
khác. Vòng 2 seed một phiếu thật **có HAI chỉ số bất thường** (WBC 14.2 10^9/L,
HbA1c 8.1%) qua `POST /analyze`, `saved_report_id=7`.

Hai chỉ số bất thường là điểm then chốt: bản thân phiếu không đủ để suy ra chỉ
số nào, nên con đường duy nhất để ra WBC là thừa hưởng từ hội thoại cũ.

```
Hội thoại 4: "Giai thich chi so WBC trong phieu 7"   -> status=success

  ĐỐI CHỨNG, cùng hội thoại 4: "Giai thich ky hon chi so nay"
  -> status = success, reason = None
     "Kết quả WBC của bạn:
      - Giá trị: 14.2 10^9/L
      - Trạng thái: CAO
      - Khoảng tham chiếu: 4.72 - 11.3 10^9/L ..."

New Chat -> hội thoại 5, ĐÚNG CÂU HỎI ĐÓ: "Giai thich ky hon chi so nay"
  -> status = needs_input, reason = AMBIGUOUS_CONTEXT
     "Bạn muốn xem chỉ số nào?
      Bạn có thể chọn một chỉ số trong phiếu xét nghiệm hoặc nhập tên chỉ số,
      ví dụ: - WBC - Glucose - HbA1c - Cholesterol"
```

**Expected:** hội thoại 4 resolve ra WBC; hội thoại 5 hỏi lại.
**Kết quả: PASS.** Cùng một câu hỏi, cùng bệnh nhân, cùng phiếu — khác nhau
đúng ở chỗ hội thoại nào.

Một ghi chú về cách đọc bằng chứng này: probe đầu tiên của tôi kiểm bằng
`"WBC" in message`, và nó báo `True` cho hội thoại 5. Đó là **kim sai**, không
phải lỗi — chữ WBC ở đó chỉ nằm trong danh sách ví dụ của câu hỏi lại. Bằng
chứng thật là `reason_code = AMBIGUOUS_CONTEXT` cùng với nguyên văn "Bạn muốn
xem chỉ số nào?". Cùng loại sai với vụ needle `"54"` khớp vào một span id trong
test wire-capture Langfuse.

### Còn thiếu

Chưa bấm trên trình duyệt. Backend đã được chứng minh bằng runtime thật ở trên,
nhưng phần giao diện (danh sách hội thoại, nút New Chat, nạp lại sau F5) mới chỉ
qua `tsc`, `eslint`, `next build` và 10 test logic thuần. Repo này có tiền lệ: ba
lỗi thật của PR #42 lọt qua một bộ 387 test xanh, vì test không mở app ra bấm.
Chưa deploy nên cũng chưa có transcript trên production.

---

## KNOWN_LIMITATIONS

1. **Lượt dựng lại chỉ có văn bản.** Không có nút hành động, không có khối chỉ
   số — hệ quả trực tiếp của việc không lưu payload có cấu trúc (mục A.3). Người
   dùng đọc lại được mọi thứ đã hiện ra, chỉ không bấm lại được nút của lượt cũ.
2. **Chưa xoá / đổi tên được hội thoại.** Danh sách chỉ dài thêm.
3. **`pending_ocr_review` không sống qua restart.** Vẫn như trước — nó trỏ vào
   checkpointer in-memory của graph, nên lưu nó là lưu một con trỏ treo.
4. **Cache RAM của store không có giới hạn.** Mỗi hội thoại từng chạm để lại một
   bản ghi nhỏ trong tiến trình. Đã nhỏ hơn trước (DB là nguồn sự thật, bản ghi
   chỉ giữ hai trường transient) nhưng vẫn chỉ lớn lên. Chưa phải vấn đề ở quy
   mô này; ghi lại để không ai ngạc nhiên.
5. **Bác sĩ chat thì không được lưu gì.** Có chủ ý ở V1, nhưng nghĩa là màn
   `/doctor` mất transcript khi F5.

## RISKS

**Một lỗi thật đã xảy ra trong lúc làm task này, và tôi ghi lại nguyên vẹn.**

Khi context chuyển sang gắn theo hội thoại, route `onboarding/acknowledge` vẫn
ghi vào bản ghi in-memory khoá theo `patient:{uid}`, còn lượt chat sau đó đọc
hàng `conv:{id}`. Kết quả: **mọi bệnh nhân kẹt ở màn onboarding đúng một bước
sau khi vừa bấm "Tôi đã hiểu"**.

Đáng chú ý là bộ test CP của tôi **không** bắt được — chúng stub phần lõi
orchestrator, nên không đi qua onboarding gate. Bộ `tip006` sẵn có mới bắt được.
Bài học: test do người sửa viết có xu hướng đi đúng con đường người đó đang nghĩ
tới. Đã thêm hai test hồi quy đi qua HTTP thật.

Rủi ro còn lại:

- **Store giờ đọc DB mỗi lượt.** Thêm truy vấn trên đường chat. Đo bằng
  `db_query_count` trong log `request_timing` trước khi lo; hàng hội thoại
  thường đã nằm trong session của request.
- **`get_or_create_latest` tạo hàng khi bệnh nhân chat mà chưa có hội thoại
  nào.** Nghĩa là một bệnh nhân gửi một câu rồi bỏ đi vẫn để lại một hàng. Chấp
  nhận được — không có hàng thì không lưu được câu đó.
- **Không có rate limiting** (nợ sẵn có của repo): `POST /conversations` cho phép
  tạo hàng loạt. Cùng loại với `/auth/register`, không nặng hơn.

## HARD_EVAL

```
python scripts/run_response_quality_eval.py     --report-out <ngoài repo> --json-out <ngoài repo>
-> Overall Result: 125/125 passed (100.0%) | 0 Failed
```

**HARD = 125/125.** Kiểm sau khi chạy: `git status --short eval/ data/` → sạch,
không file track nào bị ghi đè.

**Phải truyền `--report-out` / `--json-out` ra ngoài repo.** Mặc định script ghi
vào `eval/manual/response_quality_baseline.json` và `_report.md`, mà **cả hai đều
là file được git track**. Chạy mặc định là âm thầm ghi đè baseline bằng kết quả
của lần chạy hiện tại — tức là tự phong lại chính mình, đúng loại lỗi đã xảy ra
với `data/reference/medical_kb_manifest.json` (một test gọi `ingest()` thật và ghi
đè file pin, làm cái pin không bao giờ phát hiện được thay đổi nữa).

Tôi đã lỡ chạy mặc định một lần, dừng lại trước khi nó ghi (script ghi ở cuối
run), và kiểm `git status --short eval/` → sạch. Đề bài cấm sửa golden để làm
test xanh; ghi đè baseline bằng output của chính mình là dạng nguy hiểm nhất của
việc đó vì nó không hiện ra trong diff nếu ai đó vô tình commit kèm.

Lưu ý về harness này: nó chạy qua `TestClient(app)`, tức **đi qua route thật**,
nên thay đổi của task này có tác dụng ở đó. Đã kiểm phần quan trọng nhất: mỗi
case **đăng ký một bệnh nhân mới** (`rq_a_<uuid>`), nên `get_or_create_latest`
tạo một hội thoại mới với context rỗng cho từng case — không có nguy cơ context
của case trước rớt sang case sau.

## F. Regression gate

| Hạng mục | Kết quả |
| --- | --- |
| targeted conversation tests | **PASS** — 25/25 |
| orchestrator suite | **PASS** — 398 passed; 1 failed + 1 error đỏ sẵn trên main |
| full backend suite | **PASS** — 1473 passed; 1 failed + 3 errors đỏ sẵn trên main |
| HARD | **125/125** |
| ruff | 104 lỗi, **bằng đúng main**; 0 lỗi trong file tôi đụng |
| frontend lint | **PASS** — 0 problem |
| frontend build | **PASS** |
| frontend tests | **PASS** — 68/68 (`node --test src/lib/*.test.mjs` từ `frontend/`) |

Bốn test đỏ đã được xác nhận là đỏ sẵn trên main bằng `git stash`, không phải
báo gộp cho qua:

```
git stash -u && pytest <4 test đó> -q   -> 1 failed, 3 errors, 2 passed
git stash pop
```

Hai test `tip006` trong danh sách đỏ ban đầu **là lỗi của tôi** — đã nêu ở RISKS
và đã sửa; giờ 14/14 xanh.

## READY_FOR_REVIEW

`YES` cho phần backend — mọi cổng đề bài yêu cầu đều đạt, CP-05/07/08 có bằng
chứng runtime kèm vế đối chứng.

Một việc còn treo, nêu rõ chứ không giấu: **chưa bấm thử trên trình duyệt.**
Giao diện mới qua `tsc`, `eslint`, `next build` và 10 test logic thuần. Ai review
nên mở app bấm thử trước khi merge — repo này đã có tiền lệ ba lỗi giao diện lọt
qua một bộ 387 test xanh.
