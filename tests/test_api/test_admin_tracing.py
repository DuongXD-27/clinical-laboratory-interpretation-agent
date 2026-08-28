"""Trace vận hành cho vai trò admin — phân quyền, dữ liệu, và cách ly test.

Ba nhóm câu hỏi bộ test này trả lời:

1. Ai vào được, ai không. Admin là role thứ tư và mỗi role mới là một cơ hội mở
   nhầm cửa; ma trận ở đây kiểm cả hai chiều — admin không vào được bệnh án,
   patient/doctor/guest không vào được trace.
2. Bảng trace có rò dữ liệu bệnh nhân không. Đây là điều kiện đã hứa khi chọn
   phương án "che, chỉ gửi metadata".
3. Ghi trace có bao giờ làm hỏng request đang phục vụ người dùng không.
"""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.models.db import ROLE_ADMIN, User
from src.services.auth import hash_password

ADMIN_USERNAME = "admin.test"
ADMIN_PASSWORD = "admin-test-123"


@pytest.fixture
def admin_account(test_db):
    """Một tài khoản admin, tạo trực tiếp trong DB.

    Cố ý không đi qua endpoint nào: không có endpoint public nào tạo được admin,
    và đó chính là điều `test_register_cannot_create_an_admin` chốt lại.
    """

    with test_db.session() as session:
        session.add(
            User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=ROLE_ADMIN,
            )
        )
        session.commit()
    return ADMIN_USERNAME


async def _token(client, username: str, password: str) -> str:
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


async def _admin_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {await _token(client, ADMIN_USERNAME, ADMIN_PASSWORD)}"}


# --- Đăng nhập và phân quyền -------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_log_in_and_role_survives_the_response_model(client, admin_account):
    """`SessionRole` thiếu "admin" thì login đúng mật khẩu vẫn trả 500.

    Triệu chứng ("đăng nhập thất bại") không hề chỉ về một Literal thiếu giá
    trị, nên bắt bằng test thay vì để ai đó gỡ bằng tay.
    """

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )

    assert response.status_code == 200, response.text
    assert response.json()["role"] == "admin"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/admin/traces",
        "/api/v1/admin/traces/summary",
        "/api/v1/admin/tracing/status",
    ],
)
async def test_admin_endpoints_reject_anonymous_callers(client, path):
    assert (await client.get(path)).status_code == 401


@pytest.mark.asyncio
@pytest.mark.parametrize("username,password", [("benhnhan", "benhnhan123"), ("bacsi", "bacsi123")])
async def test_patient_and_doctor_cannot_read_traces(client, username, password):
    """Bác sĩ bị chặn cũng có chủ ý.

    Không phải vì nghi ngờ bác sĩ, mà để ma trận phân quyền chỉ có một cách đọc:
    dữ liệu vận hành thuộc về admin, dữ liệu lâm sàng thuộc về bác sĩ.
    """

    headers = {"Authorization": f"Bearer {await _token(client, username, password)}"}

    assert (await client.get("/api/v1/admin/traces", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_guest_cannot_read_traces(client):
    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    assert (await client.get("/api/v1/admin/traces", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_admin_cannot_read_patient_history(client, admin_account):
    """Quyền của admin dừng ở dữ liệu vận hành.

    Người lo hạ tầng không cần, và không nên, đọc được kết quả xét nghiệm. Nếu
    ai đó thêm ROLE_ADMIN vào `require_roles` của `/history` cho tiện thì test
    này đỏ.
    """

    headers = await _admin_headers(client)

    assert (await client.get("/api/v1/history", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_register_cannot_create_an_admin(client):
    """`/auth/register` bỏ qua `role` do client gửi — kể cả "admin".

    Cùng bảo đảm đã có với "doctor". Để role client đặt được thì bất kỳ ai cũng
    tự cấp cho mình quyền xem toàn bộ trace hệ thống.
    """

    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "ke.gia.mao", "password": "matkhau123", "role": "admin"},
    )

    assert response.status_code in (200, 201), response.text
    assert response.json()["role"] == "patient"


# --- Nội dung trace ----------------------------------------------------------


@pytest.mark.asyncio
async def test_requests_are_recorded_and_readable_by_admin(client, admin_account):
    headers = await _admin_headers(client)

    await client.post("/api/v1/auth/guest")

    response = await client.get("/api/v1/admin/traces", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 1
    assert any(item["path"] == "/api/v1/auth/guest" for item in payload["items"])


@pytest.mark.asyncio
async def test_trace_row_carries_no_patient_data(client, admin_account):
    """Điều kiện đã hứa khi chọn phương án che: bảng này không giữ gì của bệnh nhân.

    Kiểm bằng danh sách khoá CHO PHÉP chứ không phải quét từ cấm. Danh sách cấm
    sẽ lọt ngay lần đầu ai đó thêm một cột mới, còn danh sách cho phép thì cột
    mới nào cũng làm test đỏ cho tới khi có người nhìn vào nó.
    """

    headers = await _admin_headers(client)
    await client.post("/api/v1/auth/guest")

    items = (await client.get("/api/v1/admin/traces", headers=headers)).json()["items"]
    assert items

    allowed = {
        "request_id",
        "created_at",
        "method",
        "path",
        "status_code",
        "duration_ms",
        "db_query_count",
        "db_ms",
        "llm_call_count",
        "llm_ms",
        "llm_error_count",
        "user_role",
        "server_timing",
    }
    for item in items:
        unexpected = set(item) - allowed
        assert not unexpected, f"khoá lạ trong trace: {sorted(unexpected)}"
        # Vai trò thì được, danh tính thì không.
        assert "username" not in item
        assert "user_id" not in item


@pytest.mark.asyncio
async def test_health_and_ready_are_not_recorded(client, admin_account):
    """Uptime checker gọi `/health` liên tục.

    Lưu chúng thì bảng toàn nhiễu và mỗi lần probe tốn thêm một INSERT ra Neon —
    DB nằm ngoài mạng nên đó là chi phí thật.
    """

    headers = await _admin_headers(client)

    await client.get("/health")
    await client.get("/ready")

    items = (await client.get("/api/v1/admin/traces", headers=headers)).json()["items"]

    assert not [item for item in items if item["path"] in {"/health", "/ready"}]


@pytest.mark.asyncio
async def test_user_role_is_recorded_without_identity(client, admin_account):
    headers = await _admin_headers(client)

    await client.get("/api/v1/admin/tracing/status", headers=headers)

    items = (await client.get("/api/v1/admin/traces", headers=headers)).json()["items"]
    matched = [item for item in items if item["path"] == "/api/v1/admin/tracing/status"]

    assert matched
    assert matched[0]["user_role"] == "admin"


@pytest.mark.asyncio
async def test_trace_can_be_looked_up_by_request_id(client, admin_account):
    """Đường đi từ lời than phiền về đúng một dòng.

    Người dùng gặp 500 đọc được `request_id` trên màn hình lỗi; admin dán vào
    đây. Không có nó thì "tôi bấm bị lỗi" không ánh xạ được sang dòng nào.
    """

    headers = await _admin_headers(client)

    guest = await client.post("/api/v1/auth/guest")
    request_id = guest.headers["X-Request-ID"]

    response = await client.get(f"/api/v1/admin/traces/{request_id}", headers=headers)

    assert response.status_code == 200
    assert response.json()["request_id"] == request_id
    assert response.json()["path"] == "/api/v1/auth/guest"


@pytest.mark.asyncio
async def test_unknown_request_id_is_404(client, admin_account):
    headers = await _admin_headers(client)

    response = await client.get("/api/v1/admin/traces/khong-ton-tai", headers=headers)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_summary_route_is_not_shadowed_by_the_request_id_route(client, admin_account):
    """`/traces/summary` phải khai báo TRƯỚC `/traces/{request_id}`.

    Đảo thứ tự thì "summary" bị đọc thành một request_id và endpoint tổng hợp
    trả 404 — hỏng theo kiểu trông như dữ liệu chưa có chứ không như lỗi định
    tuyến.
    """

    headers = await _admin_headers(client)

    response = await client.get("/api/v1/admin/traces/summary", headers=headers)

    assert response.status_code == 200
    assert "request_count" in response.json()


# --- Bộ lọc ------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filters_narrow_the_result_set(client, admin_account):
    headers = await _admin_headers(client)

    await client.post("/api/v1/auth/guest")
    await client.get("/api/v1/admin/tracing/status", headers=headers)

    by_path = await client.get("/api/v1/admin/traces?path=/auth/guest", headers=headers)
    assert by_path.status_code == 200
    assert all("/auth/guest" in item["path"] for item in by_path.json()["items"])

    # Không request nào trong test gọi LLM, nên bộ lọc này phải trả rỗng chứ
    # không phải trả tất cả.
    llm_errors = await client.get("/api/v1/admin/traces?only_llm_errors=true", headers=headers)
    assert llm_errors.json()["items"] == []

    huge = await client.get("/api/v1/admin/traces?min_duration_ms=999999", headers=headers)
    assert huge.json()["items"] == []


@pytest.mark.asyncio
async def test_total_counts_all_matches_not_just_the_page(client, admin_account):
    """`total` là số dòng khớp bộ lọc, không phải số dòng trả về.

    Lẫn hai thứ này thì phân trang ở UI hiện sai và không ai lần ra vì trang đầu
    trông vẫn đúng.
    """

    headers = await _admin_headers(client)
    for _ in range(4):
        await client.post("/api/v1/auth/guest")

    response = await client.get("/api/v1/admin/traces?limit=2", headers=headers)
    payload = response.json()

    assert len(payload["items"]) == 2
    assert payload["total"] > 2


# --- Trạng thái Langfuse -----------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("configured", [False, True])
async def test_tracing_status_reports_configuration_without_leaking_keys(
    client, admin_account, monkeypatch, configured
):
    """\"Không thấy trace nào" có hai nguyên nhân khác hẳn nhau.

    Chưa cấu hình key, hay đã cấu hình mà chưa có traffic. Endpoint này phân
    biệt hai trường hợp đó mà không phải vào đọc biến môi trường trên Railway.

    Cấu hình được đặt tường minh trong chính test, KHÔNG đọc từ `.env` của máy
    dev. Bản trước khẳng định `langfuse_configured is False` và xanh cho tới
    đúng lúc có người cắm key thật vào `.env` — test đỏ vì môi trường chứ không
    vì code, đúng loại hỏng khó lần nhất.
    """

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test" if configured else "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test" if configured else "")
    get_settings.cache_clear()

    try:
        headers = await _admin_headers(client)
        response = await client.get("/api/v1/admin/tracing/status", headers=headers)
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["langfuse_configured"] is configured
    assert payload["masked"] is True  # che là mặc định

    # Điều quan trọng nhất, đúng ở cả hai trường hợp: không key nào lọt ra body.
    body = response.text.lower()
    assert "secret" not in body
    assert "sk-" not in body
    assert "pk-" not in body


# --- Ghi trace không được làm hỏng request ------------------------------------


@pytest.mark.asyncio
async def test_request_still_succeeds_when_trace_write_fails(client, admin_account, monkeypatch):
    """Đường phụ hỏng thì đường chính vẫn phải đi.

    Một dòng đo lường mất đi là chuyện nhỏ; một request 500 vì log không ghi
    được là chuyện lớn.
    """

    from src.services import trace_repository

    def _explode(*args, **kwargs):
        raise RuntimeError("DB trace sập")

    monkeypatch.setattr(trace_repository, "record_trace", _explode)

    response = await client.post("/api/v1/auth/guest")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")


@pytest.mark.asyncio
async def test_traces_never_reach_the_developer_database(client, admin_account, test_db):
    """Trace của test phải nằm trong SQLite tạm, không phải data/app.db.

    Middleware chạy NGOÀI hệ thống dependency nên nó không tự đi theo
    `app.dependency_overrides` — gọi thẳng `SessionLocal()` là mỗi lần chạy suite
    lại đổ trace vào DB thật của máy dev. Cùng loại lỗi với việc một test ghi đè
    file được track, và cùng cách phát hiện: đếm ở nơi đáng ra phải có.
    """

    from sqlalchemy import func, select

    from src.models.db import RequestTrace

    await client.post("/api/v1/auth/guest")

    with test_db.session() as session:
        in_temp_db = session.execute(select(func.count(RequestTrace.id))).scalar_one()

    assert in_temp_db >= 1, "trace không rơi vào DB tạm của test — nhiều khả năng middleware đang ghi vào data/app.db"
