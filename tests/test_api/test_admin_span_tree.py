"""`GET /admin/traces/{request_id}/spans` — cây span qua HTTP, và phân quyền.

Dữ liệu mốc là chuỗi `server_timing` THẬT của một request `/analyze` trên
production. Nó chứng minh điều mà bảng đối chiếu ghi là "chưa chứng minh": dữ
liệu span đã được đo và đã lưu cho từng request, chỉ chưa ai hiện ra.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.models.db import ROLE_ADMIN, RequestTrace, User
from src.services.auth import hash_password

ADMIN_USERNAME = "admin.spans"
ADMIN_PASSWORD = "admin-spans-123"
REQUEST_ID = "17890f099ad844ab8e30443bbe8d056a"

# Nguyên văn từ production, không phải số bịa.
PRODUCTION_ANALYZE = (
    "analysis-reference-range;dur=3.981, analysis-critical-detector;dur=0.049, "
    "analysis-analyzer;dur=4635.545, analysis-generate-questions;dur=0.953, "
    "analysis-guardrail;dur=1.233, analysis-graph-total;dur=4651.840, "
    "analysis-response-map;dur=0.044, db-query;dur=239.935, http-total;dur=4991.885"
)


@pytest.fixture
def seeded_admin(test_db):
    with test_db.session() as session:
        session.add(
            User(
                username=ADMIN_USERNAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role=ROLE_ADMIN,
            )
        )
        session.add(
            RequestTrace(
                request_id=REQUEST_ID,
                created_at=datetime.now(UTC).replace(tzinfo=None),
                method="POST",
                path="/api/v1/analyze",
                status_code=200,
                duration_ms=4991.885,
                db_query_count=12,
                db_ms=239.935,
                llm_call_count=1,
                llm_ms=4226.26,
                llm_error_count=0,
                user_role="patient",
                server_timing=PRODUCTION_ANALYZE,
            )
        )
        session.commit()


async def _admin_headers(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _url(request_id: str = REQUEST_ID) -> str:
    return f"/api/v1/admin/traces/{request_id}/spans"


@pytest.mark.asyncio
async def test_span_tree_answers_why_the_request_was_slow(client, seeded_admin):
    """Câu hỏi thật của admin: 4.99 giây chậm vì đâu."""

    headers = await _admin_headers(client)
    response = await client.get(_url(), headers=headers)
    assert response.status_code == 200, response.text
    body = response.json()

    rows = {row["name"]: row for row in body["rows"]}
    assert body["total_ms"] == 4991.885

    # Cấu trúc: request -> graph -> từng node.
    assert rows["http-total"]["depth"] == 0
    assert rows["analysis-graph-total"]["depth"] == 1
    assert rows["analysis-analyzer"]["depth"] == 2

    # Và câu trả lời: LLM chiếm ~93% thời gian.
    assert rows["analysis-analyzer"]["share_pct"] == pytest.approx(92.9, abs=0.2)
    assert rows["analysis-guardrail"]["share_pct"] < 1


@pytest.mark.asyncio
async def test_children_are_ordered_slowest_first(client, seeded_admin):
    headers = await _admin_headers(client)
    body = (await client.get(_url(), headers=headers)).json()
    graph_children = [r["name"] for r in body["rows"] if r["depth"] == 2]
    assert graph_children[0] == "analysis-analyzer"


@pytest.mark.asyncio
async def test_unaccounted_time_is_reported_not_hidden(client, seeded_admin):
    """339.9ms không nằm trong span nào — phải hiện ra.

    Không hiện thì người đọc kết luận "LLM chiếm 93%, hết chuyện" và bỏ qua
    một phần ba giây không ai biết đi đâu.
    """

    headers = await _admin_headers(client)
    body = (await client.get(_url(), headers=headers)).json()
    rows = {row["name"]: row for row in body["rows"]}

    assert rows["http-total"]["unaccounted_ms"] == pytest.approx(340.0, abs=0.1)
    # Lá thì `None`, không phải 0.0 — lá không có gì để khẳng định.
    assert rows["analysis-analyzer"]["unaccounted_ms"] is None


@pytest.mark.asyncio
async def test_db_query_is_reported_separately_from_the_tree(client, seeded_admin):
    headers = await _admin_headers(client)
    body = (await client.get(_url(), headers=headers)).json()

    assert all(row["name"] != "db-query" for row in body["rows"])
    assert body["aggregates"] == [{"name": "db-query", "duration_ms": 239.935}]


@pytest.mark.asyncio
async def test_trace_without_server_timing_returns_an_empty_tree_not_500(
    client, test_db, seeded_admin
):
    """Trace từ bản cũ không có `server_timing` — trả cây rỗng, không nổ."""

    with test_db.session() as session:
        session.add(
            RequestTrace(
                request_id="khong-co-timing",
                created_at=datetime.now(UTC).replace(tzinfo=None),
                method="GET",
                path="/health",
                status_code=200,
                duration_ms=1.0,
                db_query_count=0,
                db_ms=0.0,
                llm_call_count=0,
                llm_ms=0.0,
                llm_error_count=0,
                server_timing=None,
            )
        )
        session.commit()

    headers = await _admin_headers(client)
    response = await client.get(_url("khong-co-timing"), headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["rows"] == []
    assert response.json()["total_ms"] is None


@pytest.mark.asyncio
async def test_unknown_request_id_is_404(client, seeded_admin):
    headers = await _admin_headers(client)
    assert (await client.get(_url("khong-ton-tai"), headers=headers)).status_code == 404


@pytest.mark.asyncio
async def test_span_route_does_not_shadow_the_trace_detail_route(client, seeded_admin):
    """Hai route cùng tồn tại: `/traces/{id}` và `/traces/{id}/spans`."""

    headers = await _admin_headers(client)
    detail = await client.get(f"/api/v1/admin/traces/{REQUEST_ID}", headers=headers)
    spans = await client.get(_url(), headers=headers)
    assert detail.status_code == 200
    assert spans.status_code == 200
    assert detail.json()["request_id"] == spans.json()["request_id"]


@pytest.mark.asyncio
async def test_span_payload_carries_no_patient_data(client, seeded_admin):
    """Cây span chỉ có tên bước và số milli giây.

    Đây là điều kiện đã hứa khi chọn phương án "che, chỉ gửi metadata": mở rộng
    quan sát hệ thống không được mở thêm đường rò dữ liệu bệnh nhân.
    """

    headers = await _admin_headers(client)
    raw = (await client.get(_url(), headers=headers)).text

    for forbidden in ("WBC", "benhnhan", "mmol", "10^9", "Bạch cầu", "patient_id"):
        assert forbidden not in raw, f"payload cây span chứa {forbidden!r}"


# --- phân quyền -------------------------------------------------------------


@pytest.mark.asyncio
async def test_patient_cannot_read_span_tree(client, seeded_admin):
    await client.post(
        "/api/v1/auth/register",
        json={"username": "benh.spans", "password": "matkhau123"},
    )
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benh.spans", "password": "matkhau123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(_url(), headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_doctor_cannot_read_span_tree(client, seeded_admin):
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "bacsi", "password": "bacsi123"},
    )
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    assert (await client.get(_url(), headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_guest_cannot_read_span_tree(client, seeded_admin):
    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}
    assert (await client.get(_url(), headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_unauthenticated_cannot_read_span_tree(client, seeded_admin):
    assert (await client.get(_url())).status_code in (401, 403)
