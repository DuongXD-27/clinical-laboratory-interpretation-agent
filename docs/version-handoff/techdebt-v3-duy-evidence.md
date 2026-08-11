# TechDebt V3 — Bàn giao phần của Duy

Người thực hiện: Duy · Ngày: 12/08/2026 · Nhánh: `feature/v3-techdebt-auth-history`
Người nghiệm thu: Dương

Ba nhiệm vụ: (1) thay authentication mock bằng persistence thật, (2) hoàn thiện
Guest flow, (3) lưu + truy xuất lịch sử xét nghiệm bệnh nhân.

## 0. Lược đồ DB đã triển khai — CẦN VŨ/DƯƠNG DUYỆT

Tại thời điểm làm việc này, thiết kế DB của Vũ chưa có trong repo (`docs/` không
có file nào). Để không chặn tiến độ, phần dưới là lược đồ tôi đã triển khai theo
đúng bảng tiêu chí nghiệm thu. **Nếu thiết kế của Vũ khác, phần này phải sửa
theo Vũ** — chỗ có khả năng lệch nhất là việc tách bảng `patients` riêng khỏi
`users` (tôi chưa tách, xem "Điểm cần quyết định" bên dưới).

```
users (1) ──< (n) lab_reports (1) ──< (n) lab_report_indicators
```

| Bảng | PK | FK | Field chính |
| --- | --- | --- | --- |
| `users` | `id` | — | `username` (UNIQUE), `password_hash`, `role`, `created_at` |
| `lab_reports` | `id` | `patient_user_id` → `users.id` (CASCADE) | `test_date`, `created_at`, `patient_age`, `patient_gender`, `language`, `has_critical_values`, `guardrail_passed`, `summary`, `source` |
| `lab_report_indicators` | `id` | `report_id` → `lab_reports.id` (CASCADE) | `name`, `value`, `unit`, `reference_low/high`, `status`, `is_abnormal`, `is_critical`, `explanation`, `sources` |

Index kép `(patient_user_id, test_date)` phục vụ đúng truy vấn chủ đạo của màn
lịch sử.

Trả lời 5 câu hỏi trong tiêu chí đạt của Vũ, theo đúng code hiện tại:

| Câu hỏi | Trả lời |
| --- | --- |
| User đăng ký xong lưu ở đâu? | Bảng `users`, một dòng, `role="patient"` |
| Password lưu dạng gì? | Hash bcrypt (`bcrypt.hashpw` + salt ngẫu nhiên), không lưu bản thô |
| Phân biệt doctor/patient thế nào? | Cột `users.role`; token do server ký mang theo role, client không tự khai được |
| Phiếu xét nghiệm liên kết với patient bằng gì? | `lab_reports.patient_user_id` → `users.id`, gán từ `uid` trong JWT |
| Truy vấn lịch sử patient_id=X từ ngày A→B bằng dữ liệu nào? | `WHERE patient_user_id = X AND test_date >= A AND test_date <= B`, sắp xếp theo `test_date DESC` |
| Guest xử lý thế nào? | **Không có dòng nào trong DB.** Phiên khách chỉ tồn tại trong JWT (`role="guest"`, `sid` ngẫu nhiên, TTL 120 phút) |

## 1. Những gì đã thay đổi

| Thay đổi | File |
| --- | --- |
| `POST /api/v1/auth/register` (chỉ tạo được role `patient`) | `src/api/auth_routes.py` |
| `POST /api/v1/auth/guest` — mở phiên khách, không tạo user | `src/api/auth_routes.py` |
| JWT mang `uid` (khoá chính thật) thay vì chỉ username | `src/services/auth.py`, `src/api/deps.py` |
| `require_roles()` — phân quyền theo role, tách khỏi xác thực | `src/api/deps.py` |
| Bảng `lab_reports` + `lab_report_indicators` | `src/models/db.py` |
| `GET /api/v1/history`, `GET /api/v1/history/{id}` | `src/api/history_routes.py` |
| Lưu phiếu tự động sau mỗi lần phân tích của bệnh nhân | `src/api/routes.py`, `src/services/history_repository.py` |
| Script admin cấp tài khoản bác sĩ | `src/scripts/create_doctor.py` |
| DB test cô lập trên file tạm + `restart()` mô phỏng restart backend | `tests/conftest.py` |

Tài khoản bác sĩ theo đúng ma trận "được cấp sẵn bởi admin":

```bash
python -m src.scripts.create_doctor --username bs.nam --random-password
```

`/auth/register` không nhận trường `role`; gửi kèm `role=doctor` cũng bị bỏ qua
(có test chứng minh).

## 2. Bằng chứng nghiệm thu

Chạy lại: `pytest tests/test_api/test_auth_persistence.py tests/test_api/test_guest_flow.py tests/test_api/test_patient_history.py -v`
Kết quả: **33 passed** (12/08/2026).

### Nhiệm vụ 1 — Authentication thật

| TC | Input | Expected | Actual | Test |
| --- | --- | --- | --- | --- |
| TC-01 | `POST /auth/register {username: "benhnhan_moi", password: "matkhau123"}` | 201; DB có đúng 1 user; role = `patient`; password không lưu thô | Đúng như expected | `test_tc01_register_creates_exactly_one_user_with_correct_role` |
| TC-01b | User vừa đăng ký đăng nhập ngay | 200, role `patient` | Đúng như expected | `test_tc01_registered_user_can_login_immediately` |
| TC-02 | Đăng ký → đóng toàn bộ connection, mở lại từ file DB (≡ restart backend) → login | 200, đúng username | Đúng như expected | `test_tc02_user_survives_backend_restart` |
| TC-03 | Đăng ký `trung_ten` hai lần | Lần 2 bị từ chối 409; DB vẫn 1 dòng | Đúng như expected | `test_tc03_duplicate_username_rejected_without_creating_duplicate_row` |
| TC-03b | Đăng ký trùng tên với mật khẩu khác | Mật khẩu gốc vẫn đúng, mật khẩu mới sai → không chiếm được tài khoản | Đúng như expected | `test_tc03_duplicate_does_not_overwrite_existing_password` |
| TC-03c | Đăng ký trùng tên tài khoản demo `benhnhan` | 409, tài khoản demo nguyên vẹn | Đúng như expected | `test_tc03_cannot_hijack_seeded_demo_account` |
| TC-04 | Login đúng tên, sai mật khẩu | 401, response không có `access_token` | Đúng như expected | `test_tc04_wrong_password_returns_no_token` |
| TC-04b | Login username không tồn tại | Cùng status + cùng thông điệp với trường hợp sai mật khẩu (không lộ tên nào có thật) | Đúng như expected | `test_tc04_unknown_username_returns_same_error` |
| TC-05 | `benhnhan` và `bacsi` login rồi gọi `/auth/me` | role đọc từ DB: `patient` / `doctor`; `is_guest=false` | Đúng như expected | `test_tc05_patient_and_doctor_roles_come_from_database` |
| TC-05b | `POST /auth/register` kèm `role: "doctor"` | Bị bỏ qua, user tạo ra vẫn là `patient` | Đúng như expected | `test_tc05_register_cannot_self_assign_doctor_role` |
| TC-05c | Sửa tay payload JWT rồi gọi `/auth/me` | 401 (chữ ký không khớp) | Đúng như expected | `test_tc05_tampered_token_is_rejected` |
| TC-05d | `python -m src.scripts.create_doctor --username bs.nam` rồi login | 200, role `doctor` | Đúng như expected | `test_create_doctor_script_provisions_doctor_account` |

### Nhiệm vụ 2 — Guest flow

| Tiêu chí | Input | Expected | Actual | Test |
| --- | --- | --- | --- | --- |
| Vào flow không cần đăng ký | `POST /auth/guest` → `POST /analyze` | 200, có kết quả phân tích | Đúng như expected | `test_guest_can_enter_flow_without_registering` |
| Không tạo user giả trong DB | Mở phiên khách + phân tích 1 phiếu | Bảng `users` vẫn chỉ có 2 tài khoản demo | Đúng như expected | `test_guest_creates_no_user_row` |
| Dùng được chức năng được cho phép | Khách gọi `/analyze` | 200, `saved_report_id = null` | Đúng như expected | `test_guest_analysis_is_not_persisted` |
| Không dùng được patient memory | Khách gọi `/history` và `/history/1` | 403 kèm thông điệp mời đăng ký | Đúng như expected | `test_guest_cannot_use_patient_memory` |
| Hết session → session mới không lấy lại được history cũ | Phiên 1 phân tích → mở phiên 2 | `session_id` khác nhau; phiên 2 không truy được gì (403, và phiên 1 cũng không để lại bản ghi nào) | Đúng như expected | `test_new_guest_session_cannot_reach_previous_session_data` |

### Nhiệm vụ 3 — Patient memory

| TC | Input | Expected | Actual | Test |
| --- | --- | --- | --- | --- |
| TC-01 | Patient A nhập xét nghiệm (`test_date=2026-08-05`) → `GET /history` | Bản ghi vừa tạo xuất hiện, đúng ngày, đúng số chỉ số bất thường | Đúng như expected | `test_tc01_saved_record_appears_in_history` |
| TC-01b | `GET /history/{id}` | Trả đủ chỉ số + giải thích + nguồn | Đúng như expected | `test_tc01_detail_returns_full_explanation` |
| TC-02 | Patient A nhập xét nghiệm → restart backend → login lại | Bản ghi vẫn còn, đúng ID | Đúng như expected | `test_tc02_record_survives_restart_and_relogin` |
| TC-03 | Patient A có phiếu ngày 01, 05, 10/08; query `from=2026-08-04&to=2026-08-07` | Chỉ trả về phiếu ngày 05 | `total=1`, `test_date=2026-08-05` | `test_tc03_date_range_query_returns_only_records_inside_range` |
| TC-03b | Query `from=2026-08-01&to=2026-08-10` | Cả 3 phiếu (hai đầu mút tính vào khoảng) | Đúng như expected | `test_tc03_range_boundaries_are_inclusive` |
| TC-04 | Patient B gọi `/history` và `/history/{id_của_A}` | Danh sách rỗng; chi tiết 404 | Đúng như expected | `test_tc04_patient_cannot_see_another_patients_history` |
| TC-04b | Patient B gọi `/history?patient_username=benhnhan_a` | Tham số bị bỏ qua, vẫn rỗng | Đúng như expected | `test_tc04_patient_cannot_widen_scope_via_query_param` |
| TC-04c | Bác sĩ gọi `/history` và `/history?patient_username=benhnhan_a` | Thấy toàn bộ (2 phiếu) / lọc đúng 1 phiếu | Đúng như expected | `test_doctor_can_read_all_patients_history` |
| TC-05 | Khách phân tích 1 phiếu | Bảng `lab_reports` trống; `/history` trả 403 | Đúng như expected | `test_tc05_guest_has_no_patient_history_persistence` |

Ghi chú TC-04: truy cập phiếu của người khác trả **404 chứ không 403** — 403 sẽ
gián tiếp xác nhận "phiếu ID này có tồn tại", đủ để dò ID phiếu của người khác.

### Toàn bộ bộ test

`pytest tests/ -q` → **347 passed, 7 failed**.

7 test đỏ là lỗi có sẵn trên `main`, không do thay đổi này: toàn bộ nằm trong bộ
RAGAS eval, cùng một nguyên nhân (dataset tăng từ 12 lên 27 case ở PR #30 nhưng
test vẫn assert đúng 12) — thuộc phần của Tuấn.

`ruff check src/ tests/` → All checks passed.

## 3. Điểm cần quyết định / rủi ro đã ghi nhận

1. **SQLite trên Railway không có Volume.** Trước V3 mất DB chỉ mất tài khoản
   demo (seed lại được). Từ nay mất DB là **mất tài khoản người dùng tự đăng ký
   và toàn bộ lịch sử bệnh nhân**. Local pass TC-02, production thì không. Phải
   chuyển sang Postgres trước khi có người dùng thật — đề xuất đưa vào V4.
2. **Chưa tách bảng `patients` khỏi `users`.** Hiện một bệnh nhân = một tài
   khoản. Nếu thiết kế của Vũ có bảng `patients` riêng (một bác sĩ quản nhiều hồ
   sơ bệnh nhân không có tài khoản), `lab_reports.patient_user_id` phải đổi
   thành `patient_id`. Cần Vũ xác nhận trước khi có dữ liệu thật để khỏi phải
   migrate.
3. **Ma trận phân quyền mới enforce một phần.** `/history` đã chặn đúng theo
   role. Phần "doctor KHÔNG được nhập chỉ số / upload xét nghiệm" chưa chặn —
   làm ngay sẽ đổi hành vi API đang chạy public và cần sửa frontend `/doctor`.
   Cần Dương chốt thời điểm.
4. **Chưa có giao diện.** Phần này mới là backend: chưa có form đăng ký, nút
   "Dùng thử với tư cách khách", màn xem lịch sử. Frontend vẫn đang dùng luồng
   đăng nhập cũ (vẫn chạy bình thường vì `/auth/login` giữ nguyên hợp đồng).
5. **Vẫn chưa có rate limiting.** `/auth/register` là endpoint public mới —
   không giới hạn, ai cũng tạo được hàng loạt tài khoản. Chưa chặn trong version
   này, ghi nhận là nợ.
