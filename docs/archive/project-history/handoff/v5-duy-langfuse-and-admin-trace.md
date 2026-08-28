# Trace sang Langfuse + màn hình trace cho vai trò admin — bàn giao

Người thực hiện: Duy · Ngày: 21/08/2026 · Nhánh: `feature/v5-langfuse-admin-trace`
Người nghiệm thu: Dương

Hai việc trong một: chuyển phần trace LLM sang Langfuse, và biến màn hình trace
thành một chức năng của vai trò `admin` — vai trò thứ tư của hệ thống.

## 0. Ba điểm chốt trước khi viết code

Ba câu hỏi dưới đây dẫn tới code khác nhau hẳn, nên chốt trước.

| Điểm | Chốt | Hệ quả |
| --- | --- | --- |
| Langfuse **thay** hay **chạy song song** với structured log JSON | Song song | Giữ `Server-Timing`, `X-Request-ID`, và 16 test trace hiện có. Langfuse chết hoặc chưa cấu hình thì vẫn đọc log Railway bằng `jq` như cũ |
| Dữ liệu xét nghiệm có được rời hệ thống sang Langfuse | **Che**, chỉ gửi metadata | Xem được độ trễ, token, mã lỗi. Không xem được nội dung prompt. `LANGFUSE_MASK_PAYLOADS=true` là mặc định |
| Màn admin đọc trace từ đâu | DB của mình (`request_traces`) | Admin xem được kể cả khi Langfuse chưa cấu hình. Ai cần soi sâu prompt thì vào UI Langfuse |

Lý do chọn "song song" chứ không "thay hẳn": hai lớp trả lời hai câu hỏi khác
nhau và không thay nhau được. `request_timing` trả lời "request nào chậm, hỏng ở
đâu" và cấp `X-Request-ID` để nối lời than phiền của người dùng về đúng dòng log
— thứ đó phải sống kể cả khi mạng ra ngoài chết. Langfuse trả lời "lần gọi LLM
đó tốn bao nhiêu token, hết bao nhiêu tiền", điều `llm_ms` (một số cộng dồn)
không nói được.

## 1. Ranh giới quyền của admin, và tại sao nó hẹp

Admin xem **dữ liệu vận hành**, không xem bệnh án. `/history` vẫn chỉ nhận
`patient` và `doctor`; `require_roles(ROLE_ADMIN)` không mở thêm gì sang phía đó.
Người lo hạ tầng không cần, và không nên, đọc được kết quả xét nghiệm của bệnh
nhân.

Chiều ngược lại cũng chặn: bác sĩ không vào được `/admin/*`. Không phải vì nghi
ngờ bác sĩ, mà để ma trận phân quyền chỉ có một cách đọc.

Admin **không seed sẵn** trong `DEMO_USERS`. Mật khẩu demo là công khai với cả
cohort; một tài khoản admin seed sẵn là cửa hậu ai cũng đăng nhập được. Cấp bằng:

```bash
python -m src.scripts.create_admin --username admin.duy --random-password
```

## 2. Bảng `request_traces` — những gì cố tình KHÔNG có trong đó

Bảng giữ: `request_id`, `created_at`, `method`, `path`, `status_code`,
`duration_ms`, `db_query_count`, `db_ms`, `llm_call_count`, `llm_ms`,
`llm_error_count`, `user_role`, `server_timing`.

Bảng **không** giữ: tên chỉ số, giá trị, đơn vị, tuổi, giới tính, username,
`user_id`, nội dung prompt, nội dung câu trả lời của LLM. Cùng nguyên tắc đã
khiến listener SQLAlchemy không bao giờ log `statement`/`parameters`.

`user_role` lưu vai trò chứ không lưu người: đủ để biết "màn bác sĩ đang chậm",
không đủ để lần ra ai đã khám gì.

`path` có thể lộ một id (`/history/12`). Id đó vô nghĩa nếu không có token của
đúng chủ nhân, và bỏ nó đi thì không phân biệt được request chậm thuộc màn hình
nào.

## 3. Bảng nghiệm thu

| TC | Điều kiện | Kỳ vọng | Thực tế | Test |
| --- | --- | --- | --- | --- |
| TC-01 | Admin đăng nhập | 200, `role="admin"` | Đúng | `test_admin_can_log_in_and_role_survives_the_response_model` |
| TC-02 | Gọi `/admin/*` không token | 401 | Đúng, cả 3 endpoint | `test_admin_endpoints_reject_anonymous_callers` |
| TC-03 | Bệnh nhân gọi `/admin/traces` | 403 | Đúng | `test_patient_and_doctor_cannot_read_traces` |
| TC-04 | Bác sĩ gọi `/admin/traces` | 403 | Đúng | `test_patient_and_doctor_cannot_read_traces` |
| TC-05 | Khách gọi `/admin/traces` | 403 | Đúng | `test_guest_cannot_read_traces` |
| TC-06 | Admin gọi `/history` | 403 | Đúng | `test_admin_cannot_read_patient_history` |
| TC-07 | `/auth/register` gửi `role="admin"` | Bị bỏ qua, tạo ra `patient` | Đúng | `test_register_cannot_create_an_admin` |
| TC-08 | Request thật xong, admin mở danh sách | Thấy dòng của request đó | Đúng | `test_requests_are_recorded_and_readable_by_admin` |
| TC-09 | Soi khoá của một dòng trace | Chỉ có khoá trong danh sách cho phép | Đúng | `test_trace_row_carries_no_patient_data` |
| TC-10 | Gọi `/health`, `/ready` | Không sinh dòng trace nào | Đúng | `test_health_and_ready_are_not_recorded` |
| TC-11 | Admin gọi một endpoint | `user_role="admin"`, không có username | Đúng | `test_user_role_is_recorded_without_identity` |
| TC-12 | Tra theo `request_id` lấy từ header | 200, đúng path | Đúng | `test_trace_can_be_looked_up_by_request_id` |
| TC-13 | Tra `request_id` không tồn tại | 404 | Đúng | `test_unknown_request_id_is_404` |
| TC-14 | Gọi `/traces/summary` | 200, không bị đọc thành `request_id` | Đúng | `test_summary_route_is_not_shadowed_by_the_request_id_route` |
| TC-15 | Lọc theo path / LLM lỗi / độ trễ | Thu hẹp đúng, không trả tất cả | Đúng | `test_filters_narrow_the_result_set` |
| TC-16 | Lấy 2 dòng trong 5 dòng khớp | `total` là 5, `items` là 2 | Đúng | `test_total_counts_all_matches_not_just_the_page` |
| TC-17 | Đọc trạng thái tracing | Có trạng thái, không có key | Đúng, body không chứa `secret`/`sk-` | `test_tracing_status_reports_configuration_without_leaking_keys` |
| TC-18 | `record_trace` ném lỗi | Request vẫn 200 | Đúng | `test_request_still_succeeds_when_trace_write_fails` |
| TC-19 | Chạy test, kiểm nơi trace rơi vào | Vào SQLite tạm, không vào `data/app.db` | Đúng | `test_traces_never_reach_the_developer_database` |
| TC-20 | Che: prompt tự do | Bị thay hoàn toàn | Đúng | `test_free_text_is_replaced_entirely` |
| TC-21 | Che: dict chứa giá trị xét nghiệm | Không còn `9.8`, `54`, tên chỉ số | Đúng | `test_lab_values_inside_a_dict_do_not_survive` |
| TC-22 | Che: khoá đo lường | `node`, `duration_ms`, `model` đi qua | Đúng | `test_measurement_keys_pass_through_so_the_trace_stays_useful` |
| TC-23 | Che: khoá lạ chưa ai khai báo | Bị che theo mặc định | Đúng | `test_masking_is_an_allowlist_not_a_blocklist` |
| TC-24 | Che: danh sách lồng nhau | Bị che từng phần tử | Đúng | `test_nested_lists_are_masked_too` |
| TC-25 | Thiếu cả hai key | Tắt hẳn, không raise | Đúng | `test_disabled_without_keys` |
| TC-26 | Chỉ có một nửa cặp key | Tính là tắt | Đúng | `test_half_a_key_pair_counts_as_disabled` |
| TC-27 | Gọi `get_client()` nhiều lần | Chỉ dựng client một lần | Đúng | `test_client_is_built_once_and_reused` |
| TC-28 | Bật che | Hàm `mask` được đưa cho SDK | Đúng | `test_mask_function_is_handed_to_the_sdk_when_masking_is_on` |
| TC-29 | Tắt che có chủ ý | `mask=None` | Đúng | `test_masking_can_be_turned_off_deliberately` |
| TC-30 | SDK Langfuse ném lỗi lúc dựng | `get_llm()` vẫn dựng được model | Đúng | `test_broken_sdk_does_not_stop_the_llm_from_being_built` |
| TC-31 | Langfuse tắt | `get_llm()` không có callback nào | Đúng | `test_get_llm_works_with_langfuse_switched_off` |
| TC-32 | `flush()` khi Langfuse tắt | Không ném gì | Đúng | `test_flush_is_safe_when_langfuse_is_off` |
| TC-33 | `flush()` khi mất mạng | Không ném gì | Đúng | `test_flush_swallows_sdk_errors` |
| TC-34 | Bật che, bắt gói THẬT trên đường truyền | Không chuỗi nào trong 6 chuỗi dữ liệu bệnh nhân xuất hiện | Đúng, 0/6 | `test_no_patient_data_leaves_the_process_when_masking_is_on` |
| TC-35 | Tắt che, cùng lời gọi đó | Cả 6 chuỗi đều xuất hiện (đối chứng) | Đúng, 6/6 | `test_the_same_call_does_leak_when_masking_is_off` |
| TC-36 | Gọi `/orchestrator/message` | `orchestrator_turn` và `request_timing` cùng một `request_id`, khớp header | Đúng | `test_orchestrator_log_shares_the_request_id_with_the_http_log` |
| TC-37 | Thông báo lỗi 401 của provider | Giữ `Error code: 401`, bỏ thân JSON | Đúng | `test_provider_error_body_is_dropped_but_the_code_survives` |
| TC-38 | Lỗi không có thân JSON nhưng nhắc key | Token dạng key bị thay `[redacted]` | Đúng, 3/3 dạng | `test_key_shaped_tokens_are_redacted_even_without_a_json_body` |
| TC-39 | Lỗi thường (timeout) | Đi qua nguyên vẹn | Đúng | `test_ordinary_error_messages_pass_through_unharmed` |
| TC-40 | Thông báo rỗng | Không thành field rỗng | Đúng | `test_empty_message_never_becomes_an_empty_span_field` |
| TC-41 | Thông báo rất dài | Bị cắt | Đúng | `test_very_long_message_is_capped` |
| TC-42 | Tắt che | `mask_otel_spans` vẫn được gắn | Đúng | `test_scrubbing_runs_even_when_masking_is_switched_off` |
| TC-43 | SDK đổi tên method private | Lui về handler gốc, không nổ | Đúng | `test_scrubbing_handler_falls_back_when_sdk_changes` |

45 test mới, chia bốn file: `tests/test_api/test_admin_tracing.py` (21),
`tests/test_services/test_langfuse_tracing.py` (21),
`tests/test_services/test_langfuse_wire_masking.py` (2) và một test bổ sung
vào `tests/test_api/test_request_tracing.py` (1).

## 3b. TC-34/35 kiểm che trên đường truyền, không kiểm hàm

Đây là cặp test đáng giá nhất trong cả lô, nên tách ra nói riêng.

Test đơn vị chỉ kiểm `_mask()` trả về đúng. Nó **không** kiểm được câu hỏi thật
sự quan trọng: SDK có thực sự gọi hàm đó trước khi gửi hay không. Một thay đổi
trong Langfuse SDK, một tham số truyền sai, một đường đi mà `mask` không được áp
— cả ba đều làm test đơn vị vẫn xanh trong khi giá trị xét nghiệm của bệnh nhân
đi thẳng ra máy chủ bên thứ ba.

Nên TC-34/35 dựng một máy chủ HTTP thật, trỏ `LANGFUSE_HOST` vào đó, chạy một
lời gọi LLM với đúng hình dạng prompt của analyzer, rồi quét toàn bộ byte đã gửi:

```
che BAT : 0/6 chuỗi lọt, có placeholder, 1655 byte
che TAT : 6/6 chuỗi lọt, không placeholder, 1247 byte
```

Hai test phải đi cùng nhau. Một mình TC-34 vô nghĩa: nó cũng xanh khi callback
không gửi gì cả. TC-35 chứng minh dữ liệu THẬT SỰ đi qua đường đó, và chính việc
che mới là thứ chặn lại.

**Phát hiện kèm theo, có hệ quả ở production:** Langfuse gắn hàm `mask` vào trạng
thái OpenTelemetry **toàn cục** ngay lần dựng client đầu tiên. Chạy hai trường
hợp trong cùng một tiến trình thì trường hợp thứ hai vẫn dùng cấu hình che của
lần đầu — TC-35 đỏ vì lý do không liên quan gì tới điều đang kiểm, nên mỗi trường
hợp phải chạy ở tiến trình riêng. Ở production nghĩa là: **không đổi được
`LANGFUSE_MASK_PAYLOADS` lúc đang chạy**, và nếu có đoạn code nào dựng client
trước khi settings hoàn chỉnh thì che có thể sai. Hiện `get_client()` dựng lười
ở lời gọi LLM đầu tiên nên không sao; ai chuyển nó sang khởi tạo lúc import cần
biết chuyện này.

## 3c. Một lỗ trong chính lớp trace, vá luôn

`orchestrator_turn` (PR #66, Vũ) tự sinh `uuid.uuid4().hex` làm `request_id`.
Hệ quả: một lượt gọi HTTP đẻ ra hai dòng log mang hai id khác nhau và không cách
nào nối lại — đúng thứ mà cả lớp trace tồn tại để làm.

Điểm tích cực là Vũ đã ghi log bằng `extra={...}` với field phẳng, khớp hẳn với
`JsonLogFormatter`, nên vá chỉ là đổi nguồn của một biến: đọc
`get_current_timing().request_id` thay vì sinh mới. Vẫn giữ fallback sang uuid
mới cho trường hợp gọi `handle_message()` ngoài vòng đời request (test gọi thẳng
service), lúc đó không có timing nào trong context.

Đo lại trên một request thật, ba chỗ giờ cùng một id:

```
orchestrator_turn   request_id=11dfc6db326244d7a2a35e1595130b81
request_timing      request_id=11dfc6db326244d7a2a35e1595130b81
X-Request-ID        11dfc6db326244d7a2a35e1595130b81
```

Cùng id đó cũng là khoá của `request_traces`, nên admin dán một id vào
`/admin/traces/{request_id}` là thấy cả chuỗi.

## 3d. Một vụ rò thật, tìm ra khi chạy app chứ không khi chạy test

Sau khi cắm key Langfuse thật và bắn một lượt `/analyze`, tôi đọc ngược
observation từ Langfuse cloud về và thấy:

```
level          : ERROR
statusMessage  : Error code: 401 - {'error': {'message':
                 'Incorrect API key provided: AIzaSyBD***...
```

Thông báo lỗi của provider đã lên máy chủ bên thứ ba, mang theo một phần API
key. `_mask()` không chặn được vì nó chỉ chạy trên input/output — đây là một
đường khác hẳn.

Vá mất hai vòng, và vòng đầu chưa đủ:

**Vòng 1** dùng `mask_otel_spans` để dọn attribute
`langfuse.observation.status_message`. Đo lại: payload giảm 251 byte nhưng chuỗi
key **vẫn còn**. Lý do là thông báo được ghi vào HAI chỗ — attribute đó và trường
Status của span OTel — mà `OtelSpanPatch` chỉ sửa được attribute.

**Vòng 2** chặn tại nguồn chung của cả hai bản sao:
`CallbackHandler._get_error_level_and_status_message()`. Sau đó `AIzaSy` 0 lần,
`Incorrect API key` 0 lần, payload 2575 → 2074 byte.

Phần đáng xem vẫn còn nguyên, kiểm trên chính payload đó: `Error code: 401`,
`gpt-4o-mini`, `cost_details`, `level=ERROR`. Chỉ mất thân JSON của provider — mà
đó đúng là chỗ nguy hiểm theo hai hướng: nó nhắc lại một phần API key, và với lỗi
kiểm duyệt nội dung thì nó nhắc lại cả prompt, tức là cả giá trị xét nghiệm.

Việc làm sạch này chạy **bất kể `LANGFUSE_MASK_PAYLOADS`**. Tắt che nghĩa là "cho
tôi xem prompt lúc dev", không bao giờ có nghĩa là "cho phép lộ credential".

Điểm cần biết khi nâng cấp: `_get_error_level_and_status_message` là method
private của SDK. Nếu Langfuse đổi tên nó thì code lui về handler gốc thay vì nổ —
mất một lớp làm sạch còn hơn mất toàn bộ trace. TC-43 giữ đúng hành vi đó.

Đáng ghi lại vì đây là lỗi **không bộ test nào bắt được**: nó chỉ lộ ra khi cắm
key thật, gọi LLM thật, rồi đọc ngược dữ liệu từ máy chủ Langfuse về xem.

## 4. Ba lỗi bộ test tự bắt được trong lúc làm

Ghi lại vì cả ba đều là lỗi im lặng — không cái nào có triệu chứng chỉ về đúng
nguyên nhân.

**`SessionRole` thiếu `"admin"`.** Admin đăng nhập đúng mật khẩu vẫn nhận 500 ở
bước dựng response, vì `LoginResponse.role` là `Literal["patient","doctor","guest"]`.
Triệu chứng là "đăng nhập thất bại", không hề chỉ về một Literal thiếu giá trị.

**Nuốt lỗi ở ruột thì không đủ, phải nuốt ở biên.** `record_trace` tự bọc
try/except, nhưng chỗ gọi nó trong middleware thì không. Nếu hàm đó hỏng *trước*
khi vào `try` — mở session thất bại, import lỗi, ai đó đổi chữ ký — thì exception
bay lên middleware và biến request của người dùng thành 500. Đúng thứ mà cả thiết
kế này tồn tại để tránh. `test_request_still_succeeds_when_trace_write_fails` bắt
được.

**Middleware nằm ngoài hệ thống dependency.** Gọi thẳng `SessionLocal()` để ghi
trace thì mỗi lần chạy suite là trace đổ vào `data/app.db` thật của máy dev, vì
`app.dependency_overrides` chỉ ảnh hưởng tới route. Sửa bằng cách đọc session
factory qua chính bảng override đó. Cùng loại lỗi với một test ghi đè file được
track — và cùng cách phát hiện: đếm ở nơi đáng ra phải có.

## 5. Chi phí đã cân, và cách tắt

Mỗi request tốn thêm **một INSERT**. DB nằm ngoài mạng (Neon Frankfurt) nên đó là
chi phí thật, không phải chi phí giấy. Ba thứ giảm nó:

- `/health`, `/ready`, `/docs`, `/openapi.json` không ghi. Uptime checker gọi
  `/health` liên tục; ghi chúng thì bảng toàn nhiễu.
- INSERT chạy trong `run_in_threadpool`, không chặn event loop.
- `TRACE_PERSISTENCE_ENABLED=false` tắt hẳn, không cần sửa code.

Dọn trace cũ chạy **lúc khởi động**, không theo lịch và không trong middleware:
không request nào phải gánh chi phí dọn dẹp. Mặc định giữ 14 ngày
(`TRACE_RETENTION_DAYS`), vì không ai đi soi độ trễ của hai tuần trước.

## 6. Ngưỡng cảnh báo vẫn chưa đặt, có chủ ý

Màn hình tô màu theo **mã trạng thái** (5xx đỏ, 4xx cam) chứ không theo độ trễ.
Ngưỡng độ trễ phải chọn từ số đo thật; đặt bừa một con số rồi tô đỏ theo nó chỉ
dạy người xem bỏ qua màu đỏ. Giờ đã có bảng để lấy số thật — chọn ngưỡng là việc
sau khi có vài ngày dữ liệu production.

Một chỗ màn hình *có* chủ động nhắc: khi `llm_error_count > 0` trong khoảng đang
xem. Con số đó đáng nhắc vì LLM hỏng thì analyzer âm thầm rơi về nội dung dựng
sẵn, response vẫn 200, và chỉ bệnh nhân nhận ra chất lượng đi xuống.

## 7. Cần làm trước khi lên production

| Việc | Ai |
| --- | --- |
| Tạo project Langfuse, set `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` trên Railway qua `--stdin` | Duy |
| Giữ `LANGFUSE_MASK_PAYLOADS=true` ở production | — (mặc định) |
| Cấp tài khoản admin bằng `create_admin`, không seed | Duy |
| Sync `P-056` → `P-056-Deploy` (đang thiếu 59 commit) | Dương |
| Chọn ngưỡng `duration_ms` / `db_query_count` sau vài ngày có số thật | Cả nhóm |

## 8. Một chỗ chưa sửa và lý do

Khách gọi `/admin/traces` nhận 403 kèm thông điệp *"Chế độ khách không lưu và
không xem được lịch sử. Vui lòng đăng ký tài khoản."* — câu này nói về lịch sử,
đọc lên hơi lệch với endpoint trace. Nó nằm cứng trong `require_roles()` và đang
được test hiện có assert nguyên văn, nên sửa là chạm vào thông điệp dùng chung
của cả tầng auth. Ghi lại làm nợ, không tự sửa.
