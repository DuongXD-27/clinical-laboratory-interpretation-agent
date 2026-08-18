from unittest.mock import AsyncMock

import pytest

from src.api import routes
from src.models.db import LabReport
from src.services.doctor_review_service import backfill_review_flags, refresh_review_flags

GRAPH_RESULT = {
    "indicators": [
        {
            "name": "Potassium",
            "value": 6.5,
            "unit": "mmol/L",
            "reference_low": 3.5,
            "reference_high": 5.3,
            "status": "high",
            "critical_status": "critical_high",
            "is_abnormal": True,
            "is_critical": True,
            "explanation": "Kali ở mức cần được chú ý ngay.",
            "sources": [],
        },
        {
            "name": "LDL-C",
            "value": 3.4,
            "unit": "mmol/L",
            "reference_low": 0,
            "reference_high": 2.59,
            "status": "high",
            "critical_status": None,
            "is_abnormal": True,
            "is_critical": False,
            "explanation": "LDL-C cao hơn khoảng tham chiếu.",
            "sources": [],
        },
    ],
    "has_critical_values": True,
    "critical_alerts": [],
    "guardrail_passed": True,
    "disclaimer": "Test disclaimer",
    "questions_for_doctor": [
        "Tôi nên hỏi gì về Kali?",
        "Tôi nên hỏi gì về LDL-C?",
    ],
    "doctor_question_meta": [
        {"priority": "critical", "display_order": 0, "indicator_name": "Potassium"},
        {"priority": "abnormal", "display_order": 1, "indicator_name": "LDL-C"},
    ],
    "out_of_scope_indicators": [],
}


@pytest.fixture
def stub_graph(monkeypatch):
    monkeypatch.setattr(routes.agent, "ainvoke", AsyncMock(return_value=GRAPH_RESULT))


async def login_headers(client, username: str, password: str):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def register_and_login(client, username: str):
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": "matkhau123"},
    )
    assert response.status_code == 201, response.text
    return await login_headers(client, username, "matkhau123")


async def doctor_headers(client):
    return await login_headers(client, "bacsi", "bacsi123")


async def make_report(client, username: str = "queue_patient"):
    headers = await register_and_login(client, username)
    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 40,
            "patient_gender": "female",
            "test_date": "2026-08-13",
            "indicators": [
                {"name": "Potassium", "value": 6.5, "unit": "mmol/L"},
                {"name": "LDL-C", "value": 3.4, "unit": "mmol/L"},
            ],
        },
    )
    assert response.status_code == 200, response.text
    return headers, response.json()["saved_report_id"]


@pytest.mark.asyncio
async def test_critical_report_enters_doctor_queue(client, stub_graph):
    _, report_id = await make_report(client)
    doctor = await doctor_headers(client)

    response = await client.get("/api/v1/doctor/queue", headers=doctor)

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["pending"] == 1
    assert body["counts"]["critical"] == 1
    assert body["items"][0]["report_id"] == report_id
    assert body["items"][0]["severity_level"] == "critical"
    assert body["items"][0]["flags"][0]["code"] == "CRITICAL_VALUE"


@pytest.mark.asyncio
async def test_queue_counts_ocr_and_patient_questions(client, test_db, stub_graph):
    patient_headers, report_id = await make_report(client, "queue_patient_ocr")
    detail = (await client.get(f"/api/v1/history/{report_id}", headers=patient_headers)).json()
    question_id = detail["questions"][0]["id"]
    await client.post(
        f"/api/v1/history/{report_id}/questions/selection",
        headers=patient_headers,
        json={"question_ids": [question_id]},
    )

    with test_db.session() as db:
        report = db.get(LabReport, report_id)
        report.ocr_source_filename = "sample.png"
        report.indicators[0].ocr_confidence = 0.62
        refresh_review_flags(db, report)

    response = await client.get("/api/v1/doctor/queue?tab=ocr", headers=await doctor_headers(client))

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["counts"]["ocr"] == 1
    assert body["counts"]["questions"] == 1
    assert any(flag["code"] == "LOW_OCR_CONFIDENCE" for flag in body["items"][0]["flags"])
    assert any(flag["code"] == "PATIENT_HAS_QUESTIONS" for flag in body["items"][0]["flags"])


@pytest.mark.asyncio
async def test_backfill_generates_flags_for_existing_reports(client, test_db, stub_graph):
    _, report_id = await make_report(client, "old_report_patient")
    with test_db.session() as db:
        report = db.get(LabReport, report_id)
        for flag in list(report.review_flags):
            db.delete(flag)
        report.verification_status = "unverified"
        report.queued_at = None
        db.commit()

        assert backfill_review_flags(db) == 1

        refreshed = db.get(LabReport, report_id)
        assert refreshed.verification_status == "pending_review"
        assert any(flag.code == "CRITICAL_VALUE" for flag in refreshed.review_flags)


@pytest.mark.asyncio
async def test_review_finding_persists_and_complete_requires_no_pending(client, stub_graph):
    _, report_id = await make_report(client, "review_patient")
    doctor = await doctor_headers(client)
    detail = (await client.get(f"/api/v1/doctor/reports/{report_id}", headers=doctor)).json()
    first_finding = detail["findings"][0]["id"]
    second_finding = detail["findings"][1]["id"]

    reviewed = await client.patch(
        f"/api/v1/doctor/findings/{first_finding}/review",
        headers=doctor,
        json={"outcome": "agreed"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert reviewed.json()["report_progress"] == {"reviewed": 1, "total": 2}

    blocked = await client.post(f"/api/v1/doctor/reports/{report_id}/complete", headers=doctor)
    assert blocked.status_code == 409

    corrected = await client.patch(
        f"/api/v1/doctor/findings/{second_finding}/review",
        headers=doctor,
        json={"outcome": "corrected", "doctor_note": "Cần đọc lại LDL-C theo bối cảnh khám."},
    )
    assert corrected.status_code == 200, corrected.text
    assert corrected.json()["finding"]["doctor_note"] == "Cần đọc lại LDL-C theo bối cảnh khám."

    completed = await client.post(f"/api/v1/doctor/reports/{report_id}/complete", headers=doctor)
    assert completed.status_code == 200, completed.text
    assert completed.json()["report"]["verification_status"] == "verified"

    queue = (await client.get("/api/v1/doctor/queue", headers=doctor)).json()
    assert queue["counts"]["pending"] == 0
    assert queue["counts"]["verified"] == 1
