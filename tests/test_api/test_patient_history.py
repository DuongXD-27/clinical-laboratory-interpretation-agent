"""Nghiệm thu TechDebt V3 — Duy, nhiệm vụ 3: lưu và truy xuất lịch sử bệnh nhân.

Mã test bám đúng bảng nghiệm thu (TC-01..TC-05).
"""

from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.models.db import LabReport

BASE_GRAPH_RESULT = {
    "indicators": [
        {
            "name": "LDL-Cholesterol",
            "value": 4.2,
            "unit": "mmol/L",
            "reference_low": 0.0,
            "reference_high": 3.4,
            "status": "high",
            "is_abnormal": True,
            "is_critical": False,
            "explanation": "Chỉ số cao hơn khoảng tham chiếu.",
            "sources": ["https://example.org/ldl"],
        }
    ],
    "has_critical_values": False,
    "critical_alerts": [],
    "guardrail_passed": True,
    "disclaimer": "Test disclaimer",
    "questions_for_doctor": [],
    "out_of_scope_indicators": [],
}


@pytest.fixture
def stub_graph(monkeypatch):
    monkeypatch.setattr(routes.agent, "ainvoke", AsyncMock(return_value=BASE_GRAPH_RESULT))


async def login_headers(client, username: str, password: str):
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def register_and_login(client, username: str, password: str = "matkhau123"):
    response = await client.post("/api/v1/auth/register", json={"username": username, "password": password})
    assert response.status_code == 201, response.text
    return await login_headers(client, username, password)


async def submit_analysis(client, headers, *, test_date: str = "2026-08-11"):
    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 40,
            "patient_gender": "female",
            "test_date": test_date,
            "indicators": [{"name": "LDL-Cholesterol", "value": 4.2, "unit": "mmol/L"}],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


# --- TC-01: nhập xét nghiệm -> lưu -> xem history ----------------------------


@pytest.mark.asyncio
async def test_tc01_saved_record_appears_in_history(client, stub_graph):
    headers = await register_and_login(client, "benhnhan_a")

    saved = await submit_analysis(client, headers, test_date="2026-08-05")
    assert saved["saved_report_id"] is not None

    listing = await client.get("/api/v1/history", headers=headers)

    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    item = body["items"][0]
    assert item["id"] == saved["saved_report_id"]
    assert item["test_date"] == "2026-08-05"
    assert item["indicator_count"] == 1
    assert item["abnormal_count"] == 1
    assert item["patient_username"] == "benhnhan_a"


@pytest.mark.asyncio
async def test_tc01_detail_returns_full_explanation(client, stub_graph):
    headers = await register_and_login(client, "benhnhan_a")
    saved = await submit_analysis(client, headers)

    detail = await client.get(f"/api/v1/history/{saved['saved_report_id']}", headers=headers)

    assert detail.status_code == 200, detail.text
    body = detail.json()
    assert body["indicators"][0]["name"] == "LDL-Cholesterol"
    assert body["indicators"][0]["explanation"] == "Chỉ số cao hơn khoảng tham chiếu."
    assert body["indicators"][0]["sources"] == ["https://example.org/ldl"]


# --- TC-02: dữ liệu sống sót qua restart backend -----------------------------


@pytest.mark.asyncio
async def test_tc02_record_survives_restart_and_relogin(client, test_db, stub_graph):
    headers = await register_and_login(client, "benhnhan_a")
    saved = await submit_analysis(client, headers)

    test_db.restart()

    headers_after = await login_headers(client, "benhnhan_a", "matkhau123")
    listing = await client.get("/api/v1/history", headers=headers_after)

    assert listing.status_code == 200
    assert [i["id"] for i in listing.json()["items"]] == [saved["saved_report_id"]]


# --- TC-03: lọc theo khoảng ngày ---------------------------------------------


@pytest.mark.asyncio
async def test_tc03_date_range_query_returns_only_records_inside_range(client, stub_graph):
    headers = await register_and_login(client, "benhnhan_a")
    for day in ("2026-08-01", "2026-08-05", "2026-08-10"):
        await submit_analysis(client, headers, test_date=day)

    listing = await client.get("/api/v1/history", headers=headers, params={"from": "2026-08-04", "to": "2026-08-07"})

    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["total"] == 1
    assert [i["test_date"] for i in body["items"]] == ["2026-08-05"]


@pytest.mark.asyncio
async def test_tc03_range_boundaries_are_inclusive(client, stub_graph):
    headers = await register_and_login(client, "benhnhan_a")
    for day in ("2026-08-01", "2026-08-05", "2026-08-10"):
        await submit_analysis(client, headers, test_date=day)

    listing = await client.get("/api/v1/history", headers=headers, params={"from": "2026-08-01", "to": "2026-08-10"})

    assert [i["test_date"] for i in listing.json()["items"]] == [
        "2026-08-10",
        "2026-08-05",
        "2026-08-01",
    ]


@pytest.mark.asyncio
async def test_tc03_reversed_range_is_rejected(client):
    headers = await register_and_login(client, "benhnhan_a")

    listing = await client.get("/api/v1/history", headers=headers, params={"from": "2026-08-10", "to": "2026-08-01"})

    assert listing.status_code == 422


# --- TC-04: cách ly giữa hai bệnh nhân ---------------------------------------


@pytest.mark.asyncio
async def test_tc04_patient_cannot_see_another_patients_history(client, stub_graph):
    headers_a = await register_and_login(client, "benhnhan_a")
    headers_b = await register_and_login(client, "benhnhan_b")
    saved_a = await submit_analysis(client, headers_a)

    listing_b = await client.get("/api/v1/history", headers=headers_b)
    detail_b = await client.get(f"/api/v1/history/{saved_a['saved_report_id']}", headers=headers_b)

    assert listing_b.json()["total"] == 0
    # 404 chứ không 403: 403 sẽ gián tiếp xác nhận phiếu đó có tồn tại.
    assert detail_b.status_code == 404


@pytest.mark.asyncio
async def test_tc04_patient_cannot_widen_scope_via_query_param(client, stub_graph):
    headers_a = await register_and_login(client, "benhnhan_a")
    headers_b = await register_and_login(client, "benhnhan_b")
    await submit_analysis(client, headers_a)

    listing = await client.get("/api/v1/history", headers=headers_b, params={"patient_username": "benhnhan_a"})

    assert listing.status_code == 200
    assert listing.json()["total"] == 0


@pytest.mark.asyncio
async def test_doctor_can_read_all_patients_history(client, stub_graph):
    headers_a = await register_and_login(client, "benhnhan_a")
    headers_b = await register_and_login(client, "benhnhan_b")
    await submit_analysis(client, headers_a, test_date="2026-08-05")
    await submit_analysis(client, headers_b, test_date="2026-08-06")

    doctor = await login_headers(client, "bacsi", "bacsi123")
    all_reports = await client.get("/api/v1/history", headers=doctor)
    only_a = await client.get("/api/v1/history", headers=doctor, params={"patient_username": "benhnhan_a"})

    assert all_reports.json()["total"] == 2
    assert only_a.json()["total"] == 1
    assert only_a.json()["items"][0]["patient_username"] == "benhnhan_a"


@pytest.mark.asyncio
async def test_doctor_analysis_is_not_stored_as_patient_history(client, test_db, stub_graph):
    """Bác sĩ chạy thử phân tích không sinh phiếu mang tên bệnh nhân nào."""
    doctor = await login_headers(client, "bacsi", "bacsi123")

    result = await submit_analysis(client, doctor)

    assert result["saved_report_id"] is None
    with test_db.session() as db:
        assert db.query(LabReport).count() == 0


@pytest.mark.asyncio
async def test_doctor_query_for_unknown_patient_returns_404(client):
    doctor = await login_headers(client, "bacsi", "bacsi123")

    listing = await client.get("/api/v1/history", headers=doctor, params={"patient_username": "khong-ton-tai"})

    assert listing.status_code == 404


# --- TC-05: khách không có persistence ---------------------------------------


@pytest.mark.asyncio
async def test_tc05_guest_has_no_patient_history_persistence(client, test_db, stub_graph):
    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    await submit_analysis(client, headers)

    with test_db.session() as db:
        assert db.query(LabReport).count() == 0
    assert (await client.get("/api/v1/history", headers=headers)).status_code == 403


@pytest.mark.asyncio
async def test_history_requires_authentication(client):
    assert (await client.get("/api/v1/history")).status_code == 401
