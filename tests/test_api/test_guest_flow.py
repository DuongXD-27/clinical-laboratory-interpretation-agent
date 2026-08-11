"""Nghiệm thu TechDebt V3 — Duy, nhiệm vụ 2: Guest flow.

Quyết định họp: khách không cần bảng riêng, hoạt động trong phiên; hết phiên là
mất dữ liệu. Bộ test này chứng minh đúng 5 tiêu chí đã chốt.
"""

from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.models.db import LabReport, User

GRAPH_RESULT = {
    "indicators": [
        {
            "name": "Glucose",
            "value": 5.2,
            "unit": "mmol/L",
            "reference_low": 3.9,
            "reference_high": 6.4,
            "status": "normal",
            "is_abnormal": False,
            "is_critical": False,
            "explanation": "Đường huyết trong khoảng bình thường.",
            "sources": [],
        }
    ],
    "has_critical_values": False,
    "critical_alerts": [],
    "guardrail_passed": True,
    "disclaimer": "Test disclaimer",
    "questions_for_doctor": [],
    "out_of_scope_indicators": [],
}

ANALYZE_PAYLOAD = {
    "patient_age": 35,
    "patient_gender": "male",
    "test_date": "2026-08-11",
    "indicators": [{"name": "Glucose", "value": 5.2, "unit": "mmol/L"}],
}


async def open_guest_session(client):
    response = await client.post("/api/v1/auth/guest")
    assert response.status_code == 200, response.text
    body = response.json()
    return body, {"Authorization": f"Bearer {body['access_token']}"}


@pytest.fixture
def stub_graph(monkeypatch):
    monkeypatch.setattr(routes.agent, "ainvoke", AsyncMock(return_value=GRAPH_RESULT))


@pytest.mark.asyncio
async def test_guest_can_enter_flow_without_registering(client, stub_graph):
    body, headers = await open_guest_session(client)

    assert body["role"] == "guest"
    assert body["can_save_history"] is False
    assert body["expires_in_seconds"] > 0

    response = await client.post("/api/v1/analyze", headers=headers, json=ANALYZE_PAYLOAD)
    assert response.status_code == 200, response.text
    assert response.json()["indicators"][0]["name"] == "Glucose"


@pytest.mark.asyncio
async def test_guest_creates_no_user_row(client, test_db, stub_graph):
    _, headers = await open_guest_session(client)
    await client.post("/api/v1/analyze", headers=headers, json=ANALYZE_PAYLOAD)

    with test_db.session() as db:
        usernames = {u.username for u in db.query(User).all()}

    # Chỉ còn đúng 2 tài khoản demo được seed sẵn — không có user giả nào sinh ra.
    assert usernames == {"benhnhan", "bacsi"}


@pytest.mark.asyncio
async def test_guest_analysis_is_not_persisted(client, test_db, stub_graph):
    _, headers = await open_guest_session(client)

    response = await client.post("/api/v1/analyze", headers=headers, json=ANALYZE_PAYLOAD)

    assert response.json()["saved_report_id"] is None
    with test_db.session() as db:
        assert db.query(LabReport).count() == 0


@pytest.mark.asyncio
async def test_guest_cannot_use_patient_memory(client):
    _, headers = await open_guest_session(client)

    listing = await client.get("/api/v1/history", headers=headers)
    detail = await client.get("/api/v1/history/1", headers=headers)

    assert listing.status_code == 403
    assert detail.status_code == 403
    assert "khách" in listing.json()["detail"].lower()


@pytest.mark.asyncio
async def test_new_guest_session_cannot_reach_previous_session_data(client, stub_graph):
    first, first_headers = await open_guest_session(client)
    await client.post("/api/v1/analyze", headers=first_headers, json=ANALYZE_PAYLOAD)

    second, second_headers = await open_guest_session(client)

    assert second["session_id"] != first["session_id"]
    # Không có endpoint nào trả lại dữ liệu phiên cũ: lịch sử đóng với khách,
    # và phiên trước cũng không để lại bản ghi nào để lấy.
    assert (await client.get("/api/v1/history", headers=second_headers)).status_code == 403


@pytest.mark.asyncio
async def test_guest_identity_is_reported_as_guest(client):
    _, headers = await open_guest_session(client)

    me = await client.get("/api/v1/auth/me", headers=headers)

    assert me.status_code == 200
    assert me.json()["role"] == "guest"
    assert me.json()["is_guest"] is True


@pytest.mark.asyncio
async def test_analyze_still_requires_a_session_token(client, stub_graph):
    """Bỏ auth hoàn toàn là lựa chọn đã loại: gọi trần vẫn phải 401."""
    response = await client.post("/api/v1/analyze", json=ANALYZE_PAYLOAD)

    assert response.status_code == 401
