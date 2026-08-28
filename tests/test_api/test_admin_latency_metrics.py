"""`GET /admin/traces/latency` — phân vị tách nhóm, và phân quyền của nó.

Endpoint này thay thế trung bình toàn hệ thống ở đầu màn admin. Trên dữ liệu
production thật, `avg_duration_ms` ra 85ms trong khi request AI mất 4–7 giây,
vì ~1200 request API thường đè con số đó xuống. Bộ test ở đây dựng lại đúng
hình dạng đó qua HTTP.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from src.models.db import ROLE_ADMIN, RequestTrace, User
from src.services.auth import hash_password

ADMIN_USERNAME = "admin.latency"
ADMIN_PASSWORD = "admin-latency-123"
LATENCY_URL = "/api/v1/admin/traces/latency"


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


@pytest.fixture
def admin_headers_factory(test_db):
    with test_db.session() as session:
        session.add(
            User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=ROLE_ADMIN,
            )
        )
        session.commit()

    async def _make(client):
        response = await client.post(
            "/api/v1/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}

    return _make


def _seed(test_db, rows):
    with test_db.session() as session:
        for i, (path, method, duration, status, llm) in enumerate(rows):
            session.add(
                RequestTrace(
                    request_id=f"req{i:05d}",
                    created_at=_utcnow() - timedelta(minutes=1),
                    method=method,
                    path=path,
                    status_code=status,
                    duration_ms=duration,
                    db_query_count=1,
                    db_ms=1.0,
                    llm_call_count=llm,
                    llm_ms=duration if llm else 0.0,
                    llm_error_count=0,
                    user_role="patient",
                )
            )
        session.commit()


@pytest.mark.asyncio
async def test_percentiles_expose_the_ai_latency_that_average_hides(client, test_db, admin_headers_factory):
    """Đúng hình dạng dữ liệu production: 1200 API nhanh + 27 AI chậm."""

    rows = [("/api/v1/history", "GET", 50.0, 200, 0) for _ in range(1200)]
    rows += [("/api/v1/analyze", "POST", 4000.0 + i * 100, 200, 1) for i in range(27)]
    _seed(test_db, rows)

    headers = await admin_headers_factory(client)
    response = await client.get(LATENCY_URL, headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    # `>= 1200`, khong phai `== 1200`: chinh request dang nhap cua test nay
    # cung duoc middleware ghi trace, va no thuoc nhom API. Endpoint do ca chinh
    # no — dung nhu tren production, noi moi lan admin mo man hinh la them mot
    # dong vao mau.
    assert body["api"]["count"] >= 1200
    assert body["api"]["p50_ms"] == 50.0

    assert body["ai"]["count"] == 27
    assert body["ai"]["p50_ms"] >= 5000
    assert body["ai"]["p95_ms"] >= 6000
    assert body["ai"]["llm_call_count"] == 27

    # Đối chứng: endpoint cũ vẫn trả trung bình rất đẹp trên CÙNG dữ liệu đó.
    # Không có vế này thì "P95 cao" chỉ là một con số, không phải một phát hiện.
    old = await client.get("/api/v1/admin/traces/summary", headers=headers)
    assert old.json()["avg_duration_ms"] < 200
    assert body["ai"]["p95_ms"] > old.json()["avg_duration_ms"] * 30


@pytest.mark.asyncio
async def test_preflight_requests_do_not_dilute_the_percentiles(client, test_db, admin_headers_factory):
    rows = [("/api/v1/analyze", "POST", 4000.0 + i, 200, 1) for i in range(20)]
    rows += [("/api/v1/analyze", "OPTIONS", 0.0, 200, 0) for _ in range(500)]
    _seed(test_db, rows)

    headers = await admin_headers_factory(client)
    ai = (await client.get(LATENCY_URL, headers=headers)).json()["ai"]

    assert ai["count"] == 20, "preflight phải bị loại hoàn toàn khỏi mẫu"
    assert ai["p50_ms"] >= 4000


@pytest.mark.asyncio
async def test_empty_window_reports_none_not_zero(client, test_db, admin_headers_factory):
    """Chưa có dữ liệu thì trả `null`, không phải 0.

    `0ms` trên màn hình vận hành đọc như "nhanh tuyệt đối". Nhầm nó với "chưa
    đo được" là loại nhầm dẫn tới kết luận sai về một hệ thống đang chết.
    """

    headers = await admin_headers_factory(client)
    body = (await client.get(LATENCY_URL, headers=headers)).json()

    # Chi kiem nhom AI: nhom API khong bao gio rong that, vi chinh request dang
    # nhap va request goi endpoint nay deu duoc ghi trace.
    assert body["ai"]["count"] == 0
    assert body["ai"]["p50_ms"] is None
    assert body["ai"]["p95_ms"] is None
    assert body["ai"]["p99_ms"] is None
    assert body["ai"]["max_ms"] is None
    assert body["ai"]["error_rate_pct"] is None
    assert body["ai"]["requests_per_min"] == 0.0


@pytest.mark.asyncio
async def test_error_rate_counts_only_5xx(client, test_db, admin_headers_factory):
    rows = [
        ("/api/v1/analyze", "POST", 100.0, 200, 1),
        ("/api/v1/analyze", "POST", 100.0, 404, 0),
        ("/api/v1/analyze", "POST", 100.0, 422, 0),
        ("/api/v1/analyze", "POST", 100.0, 500, 0),
    ]
    _seed(test_db, rows)
    headers = await admin_headers_factory(client)
    ai = (await client.get(LATENCY_URL, headers=headers)).json()["ai"]
    assert ai["error_count"] == 1
    assert ai["error_rate_pct"] == 25.0


@pytest.mark.asyncio
async def test_window_hours_narrows_the_sample(client, test_db, admin_headers_factory):
    with test_db.session() as session:
        for i, age_hours in enumerate((0, 48)):
            session.add(
                RequestTrace(
                    request_id=f"old{i}",
                    created_at=_utcnow() - timedelta(hours=age_hours),
                    method="POST",
                    path="/api/v1/analyze",
                    status_code=200,
                    duration_ms=1000.0,
                    db_query_count=0,
                    db_ms=0.0,
                    llm_call_count=1,
                    llm_ms=1000.0,
                    llm_error_count=0,
                )
            )
        session.commit()

    headers = await admin_headers_factory(client)
    day = (await client.get(f"{LATENCY_URL}?window_hours=24", headers=headers)).json()
    week = (await client.get(f"{LATENCY_URL}?window_hours=168", headers=headers)).json()
    assert day["ai"]["count"] == 1
    assert week["ai"]["count"] == 2


@pytest.mark.asyncio
async def test_response_never_exposes_an_average(client, test_db, admin_headers_factory):
    _seed(test_db, [("/api/v1/analyze", "POST", 100.0, 200, 1)])
    headers = await admin_headers_factory(client)
    body = (await client.get(LATENCY_URL, headers=headers)).json()
    for group in ("ai", "api"):
        assert "avg" not in body[group]
        assert "avg_duration_ms" not in body[group]


# --- phân quyền: mỗi endpoint mới là một cơ hội mở nhầm cửa -----------------


@pytest.mark.asyncio
async def test_patient_cannot_read_operational_latency(client):
    await client.post(
        "/api/v1/auth/register",
        json={"username": "benh.latency", "password": "matkhau123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benh.latency", "password": "matkhau123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(LATENCY_URL, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_doctor_cannot_read_operational_latency(client):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "bacsi", "password": "bacsi123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(LATENCY_URL, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_guest_cannot_read_operational_latency(client):
    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}
    assert (await client.get(LATENCY_URL, headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_operational_latency(client):
    assert (await client.get(LATENCY_URL)).status_code in (401, 403)


@pytest.mark.asyncio
async def test_latency_is_not_swallowed_by_the_request_id_route(client, test_db, admin_headers_factory):
    """`/traces/latency` không được bị khớp thành `/traces/{request_id}`.

    FastAPI khớp route theo thứ tự khai báo. Đặt sai thứ tự thì "latency" trở
    thành một request_id và endpoint trả 404 — cùng cái bẫy đã gặp với
    `/traces/summary`.
    """

    headers = await admin_headers_factory(client)
    response = await client.get(LATENCY_URL, headers=headers)
    assert response.status_code == 200
    assert "ai" in response.json()
