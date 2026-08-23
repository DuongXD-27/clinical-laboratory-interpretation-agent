from __future__ import annotations

import datetime
from urllib.parse import quote

import pytest

from src.models.schemas import AnalyzeRequest, AnalyzeResponse
from src.services.lab_history_service import save_analyzed_report


async def _login_headers(client, username: str, password: str):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


async def _patient_headers(client):
    return await _login_headers(client, "benhnhan", "benhnhan123")


async def _doctor_headers(client):
    return await _login_headers(client, "bacsi", "bacsi123")


def _review_url(analyte: str, suffix: str = "") -> str:
    return f"/api/v1/patient/me/trends/{quote(analyte, safe='')}/review{suffix}"


def _analysis(rows):
    return AnalyzeResponse(
        indicators=[
            {
                "name": row["name"],
                "value": row["value"],
                "unit": row["unit"],
                "reference_low": row.get("reference_low", 0),
                "reference_high": row.get("reference_high", 2.59),
                "status": row.get("status", "normal"),
                "is_abnormal": row.get("status") in {"low", "high", "critical_low", "critical_high"},
                "is_critical": row.get("status") in {"critical_low", "critical_high"},
                "explanation": row.get("explanation", ""),
                "sources": [],
            }
            for row in rows
        ],
        critical_alerts=[],
        has_critical_values=any(row.get("status") in {"critical_low", "critical_high"} for row in rows),
        summary="",
        guardrail_passed=True,
    )


def _request(test_date: str, rows):
    return AnalyzeRequest(
        patient_age=40,
        patient_gender="female",
        test_date=datetime.date.fromisoformat(test_date),
        language="vi",
        indicators=[{"name": row["name"], "value": row["value"], "unit": row["unit"]} for row in rows],
    )


def _save_report(session_factory, username: str, test_date: str, value: float):
    rows = [{"name": "LDL-C", "value": value, "unit": "mmol/L", "status": "high"}]
    with session_factory() as session:
        return save_analyzed_report(
            session,
            username=username,
            request=_request(test_date, rows),
            analysis=_analysis(rows),
        )


def _save_ldl_series(session_factory, username: str = "benhnhan", values=(2.8, 3.0, 3.2)):
    for index, value in enumerate(values, start=1):
        _save_report(session_factory, username, f"2026-08-{index:02d}", value)


async def _create_review_request(client, headers, llm_text="AI nhận xét LDL-C tăng qua các lần xét nghiệm."):
    return await client.post(
        _review_url("LDL-C", "-requests"),
        headers=headers,
        json={"trend_filter": "latest5", "llm_explanation": llm_text},
    )


async def _submit_review(client, doctor_headers, request_id: int):
    return await client.post(
        f"/api/v1/doctor/trend-reviews/{request_id}/review",
        headers=doctor_headers,
        json={
            "doctor_assessment": "corrected",
            "doctor_comment": "LDL-C tăng nhẹ, cần đối chiếu mục tiêu điều trị và yếu tố nguy cơ.",
        },
    )


@pytest.mark.asyncio
async def test_patient_creates_trend_review_request_and_duplicate_pending_is_blocked(client, test_db):
    patient = await _patient_headers(client)
    _save_ldl_series(test_db.session)

    created = await _create_review_request(client, patient)

    assert created.status_code == 201, created.text
    review = created.json()["review"]
    assert review["status"] == "PENDING"
    assert review["patient_id"] == 1
    assert review["analyte_canonical"] == "LDL-C"
    assert review["llm_explanation_snapshot"] == "AI nhận xét LDL-C tăng qua các lần xét nghiệm."
    assert len(review["trend_snapshot"]["points"]) == 3
    assert review["requested_at"]

    duplicate = await _create_review_request(client, patient)

    assert duplicate.status_code == 409


@pytest.mark.asyncio
async def test_doctor_reviews_trend_request_and_patient_sees_latest_review(client, test_db):
    patient = await _patient_headers(client)
    doctor = await _doctor_headers(client)
    _save_ldl_series(test_db.session)
    created = await _create_review_request(client, patient)
    request_id = created.json()["review"]["id"]

    queue = await client.get("/api/v1/doctor/trend-reviews", headers=doctor)
    detail = await client.get(f"/api/v1/doctor/trend-reviews/{request_id}", headers=doctor)

    assert queue.status_code == 200, queue.text
    assert queue.json()["total"] == 1
    assert queue.json()["items"][0]["id"] == request_id
    assert queue.json()["items"][0]["display_name"] == "LDL-C"
    assert detail.status_code == 200, detail.text
    assert detail.json()["patient"]["name"] == "benhnhan"
    assert detail.json()["review"]["llm_explanation_snapshot"] == "AI nhận xét LDL-C tăng qua các lần xét nghiệm."

    reviewed = await _submit_review(client, doctor, request_id)

    assert reviewed.status_code == 200, reviewed.text
    reviewed_payload = reviewed.json()
    assert reviewed_payload["status"] == "REVIEWED"
    assert reviewed_payload["doctor_assessment"] == "corrected"
    assert reviewed_payload["doctor_comment"] == "LDL-C tăng nhẹ, cần đối chiếu mục tiêu điều trị và yếu tố nguy cơ."
    assert reviewed_payload["reviewed_by_username"] == "bacsi"
    assert reviewed_payload["reviewed_at"]

    patient_state = await client.get(_review_url("LDL-C"), headers=patient)

    assert patient_state.status_code == 200, patient_state.text
    state = patient_state.json()
    assert state["pending_request"] is None
    assert state["latest_review"]["id"] == request_id
    assert state["latest_review"]["doctor_comment"] == reviewed_payload["doctor_comment"]
    assert state["can_request_review"] is False
    assert state["reason"] == "LATEST_REVIEW_STILL_CURRENT"


@pytest.mark.asyncio
async def test_reviewed_trend_moves_to_history_when_current_chart_changes(client, test_db):
    patient = await _patient_headers(client)
    doctor = await _doctor_headers(client)
    _save_ldl_series(test_db.session)
    created = await _create_review_request(client, patient, "AI nhận xét cho biểu đồ P1.")
    request_id = created.json()["review"]["id"]
    reviewed = await _submit_review(client, doctor, request_id)
    assert reviewed.status_code == 200, reviewed.text

    _save_report(test_db.session, "benhnhan", "2026-08-04", 3.4)

    state_response = await client.get(_review_url("LDL-C"), headers=patient)

    assert state_response.status_code == 200, state_response.text
    state = state_response.json()
    assert state["latest_review"] is None
    assert state["latest_historical_review"]["id"] == request_id
    assert state["can_request_review"] is True
    assert state["reason"] == "CURRENT_TREND_CHANGED"
    assert state["history_count"] == 1

    history_response = await client.get(_review_url("LDL-C", "-history"), headers=patient)

    assert history_response.status_code == 200, history_response.text
    history = history_response.json()
    assert history["total"] == 1
    assert history["items"][0]["id"] == request_id
    assert history["items"][0]["llm_explanation_snapshot"] == "AI nhận xét cho biểu đồ P1."
    assert len(history["items"][0]["trend_snapshot"]["points"]) == 3

    repeated = await _create_review_request(client, patient, "AI nhận xét cho biểu đồ P2.")

    assert repeated.status_code == 201, repeated.text
    assert repeated.json()["review"]["trend_snapshot_hash"] != reviewed.json()["trend_snapshot_hash"]


@pytest.mark.asyncio
async def test_trend_review_permissions_and_patient_isolation(client, test_db):
    patient = await _patient_headers(client)
    doctor = await _doctor_headers(client)
    _save_ldl_series(test_db.session)
    created = await _create_review_request(client, patient)
    assert created.status_code == 201, created.text

    patient_forbidden = await client.get("/api/v1/doctor/trend-reviews", headers=patient)
    doctor_forbidden = await client.post(
        _review_url("LDL-C", "-requests"),
        headers=doctor,
        json={"trend_filter": "latest5", "llm_explanation": "Không được phép."},
    )

    assert patient_forbidden.status_code == 403
    assert doctor_forbidden.status_code == 403

    register = await client.post(
        "/api/v1/auth/register",
        json={"username": "patient2", "password": "patient2pass"},
    )
    assert register.status_code == 201, register.text
    patient2 = await _login_headers(client, "patient2", "patient2pass")
    _save_ldl_series(test_db.session, username="patient2", values=(2.1, 2.2, 2.3))

    state = await client.get(_review_url("LDL-C"), headers=patient2)

    assert state.status_code == 200, state.text
    assert state.json()["pending_request"] is None
    assert state.json()["latest_review"] is None
    assert state.json()["can_request_review"] is True

    history = await client.get(_review_url("LDL-C", "-history"), headers=patient2)

    assert history.status_code == 200, history.text
    assert history.json()["total"] == 0
