from __future__ import annotations

import datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.main import app
from src.models import db as db_module
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, SaveReportRequest
from src.services.auth import create_access_token
from src.services.lab_history_service import save_analyzed_report, save_report_snapshot
from src.services.demo_patient_data import seed_demo_patient_reports


@pytest_asyncio.fixture
async def isolated_client(tmp_path, monkeypatch):
    db_path = tmp_path / "patient_history.db"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(test_engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    test_session_local = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_session_local)
    db_module.init_db()

    def override_db():
        db = test_session_local()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[db_module.get_db] = override_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, test_session_local
    app.dependency_overrides.pop(db_module.get_db, None)
    test_engine.dispose()


async def _auth_headers(client: AsyncClient, username="benhnhan", password="benhnhan123"):
    response = await client.post("/api/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _token_headers(username: str, role: str = "patient"):
    token = create_access_token(username=username, role=role)
    return {"Authorization": f"Bearer {token}"}


def _analysis(rows, *, summary=""):
    return AnalyzeResponse(
        indicators=[
            {
                "name": row["name"],
                "value": row["value"],
                "unit": row["unit"],
                "reference_low": row.get("reference_low"),
                "reference_high": row.get("reference_high"),
                "status": row.get("status", "normal"),
                "is_abnormal": row.get("is_abnormal", False),
                "is_critical": row.get("is_critical", False),
                "explanation": row.get("explanation", ""),
                "sources": [],
            }
            for row in rows
        ],
        critical_alerts=[],
        has_critical_values=any(row.get("is_critical", False) for row in rows),
        summary=summary,
        guardrail_passed=True,
    )


def _request(test_date: str, rows):
    return AnalyzeRequest(
        patient_age=35,
        patient_gender="male",
        test_date=datetime.date.fromisoformat(test_date),
        language="vi",
        indicators=[{"name": row["name"], "value": row["value"], "unit": row["unit"]} for row in rows],
    )


def _save(session_local, username: str, test_date: str, rows):
    with session_local() as session:
        return save_analyzed_report(
            session,
            username=username,
            request=_request(test_date, rows),
            analysis=_analysis(rows),
        )


@pytest.mark.asyncio
async def test_demo_seed_creates_five_reports_with_nine_approved_results(isolated_client):
    _, session_local = isolated_client
    with session_local() as session:
        saved = seed_demo_patient_reports(session)
        assert saved == 5
        patient = session.query(db_module.User).filter_by(username="benhnhan").one()
        reports = session.query(db_module.LabReport).filter_by(patient_id=patient.id).all()
        assert len(reports) == 5
        assert all(len(report.indicators) == 9 for report in reports)
        assert {report.status for report in reports} >= {"NORMAL", "ABNORMAL", "CRITICAL"}


@pytest.mark.asyncio
async def test_patient_profile_get_update_invalid_and_not_found(isolated_client):
    client, _ = isolated_client
    headers = await _auth_headers(client)

    response = await client.get("/api/v1/patient/me/profile", headers=headers)
    assert response.status_code == 200
    assert response.json()["username"] == "benhnhan"

    response = await client.patch(
        "/api/v1/patient/me/profile",
        headers=headers,
        json={
            "full_name": "Nguyen Van A",
            "date_of_birth": "1990-01-02",
            "sex": "male",
            "email": "a@example.test",
        },
    )
    assert response.status_code == 200
    assert response.json()["full_name"] == "Nguyen Van A"

    response = await client.patch(
        "/api/v1/patient/me/profile",
        headers=headers,
        json={"full_name": "Invalid", "email": "khong-hop-le"},
    )
    assert response.status_code == 400

    response = await client.get("/api/v1/patient/me/profile", headers=_token_headers("ghost"))
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_report_count_counts_reports_not_results(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    rows = [
        {"name": "WBC", "value": 7.0, "unit": "10^9/L"},
        {"name": "RBC", "value": 4.8, "unit": "10^12/L"},
        {"name": "HGB", "value": 150, "unit": "g/L"},
        {"name": "Glucose", "value": 5.1, "unit": "mmol/L"},
        {"name": "HbA1c", "value": 5.4, "unit": "%"},
        {"name": "LDL-C", "value": 2.2, "unit": "mmol/L"},
        {"name": "HDL-C", "value": 1.2, "unit": "mmol/L"},
        {"name": "Creatinine", "value": 80, "unit": "umol/L"},
        {"name": "Potassium", "value": 4.2, "unit": "mmol/L"},
    ]
    _save(session_local, "benhnhan", "2026-08-10", rows)

    response = await client.get("/api/v1/patient/me/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_reports"] == 1
    assert response.json()["recent_reports"][0]["result_count"] == 9


@pytest.mark.asyncio
async def test_history_orders_by_test_date_desc(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    row = [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}]
    _save(session_local, "benhnhan", "2026-06-10", row)
    _save(session_local, "benhnhan", "2026-08-10", row)
    _save(session_local, "benhnhan", "2026-07-10", row)

    response = await client.get("/api/v1/patient/me/lab-reports", headers=headers)
    assert response.status_code == 200
    assert [item["test_date"] for item in response.json()["reports"]] == [
        "2026-08-10",
        "2026-07-10",
        "2026-06-10",
    ]


@pytest.mark.asyncio
async def test_missing_date_requires_confirmation(isolated_client):
    _, session_local = isolated_client
    analysis = _analysis([{"name": "WBC", "value": 7.0, "unit": "10^9/L"}])
    with session_local() as session:
        result = save_report_snapshot(
            session,
            username="benhnhan",
            request=SaveReportRequest(test_date=None, analysis=analysis),
        )
    assert result.saved is False
    assert result.requires_date_confirmation is True


@pytest.mark.asyncio
async def test_canonical_analyte_aliases_are_saved(isolated_client):
    _, session_local = isolated_client
    row = [{"name": "Glucose", "value": 5.2, "unit": "mmol/L"}]
    result = _save(session_local, "benhnhan", "2026-08-10", row)
    with session_local() as session:
        report = session.get(db_module.LabReport, result.report_id)
        assert report.indicators[0].analyte_raw == "Glucose"
        assert report.indicators[0].analyte_canonical == "Fasting plasma glucose"


@pytest.mark.asyncio
async def test_duplicate_detection_cases(isolated_client):
    _, session_local = isolated_client
    rows = [
        {"name": "WBC", "value": 7.0, "unit": "10^9/L"},
        {"name": "RBC", "value": 4.8, "unit": "10^12/L"},
    ]
    first = _save(session_local, "benhnhan", "2026-08-10", rows)
    same = _save(session_local, "benhnhan", "2026-08-10", rows)
    reordered = _save(session_local, "benhnhan", "2026-08-10", list(reversed(rows)))
    changed_value = _save(
        session_local,
        "benhnhan",
        "2026-08-10",
        [{"name": "WBC", "value": 7.1, "unit": "10^9/L"}, rows[1]],
    )
    changed_date = _save(session_local, "benhnhan", "2026-08-11", rows)

    with session_local() as session:
        session.add(db_module.User(username="patient2", password_hash="x", role="patient"))
        session.commit()
    other_patient = _save(session_local, "patient2", "2026-08-10", rows)

    assert first.saved is True
    assert same.duplicate is True
    assert same.existing_report_id == first.report_id
    assert reordered.duplicate is True
    assert changed_value.saved is True
    assert changed_date.saved is True
    assert other_patient.saved is True


@pytest.mark.asyncio
async def test_report_status_priority(isolated_client):
    _, session_local = isolated_client
    normal = _save(session_local, "benhnhan", "2026-08-10", [{"name": "WBC", "value": 7, "unit": "10^9/L"}])
    abnormal = _save(
        session_local,
        "benhnhan",
        "2026-08-11",
        [{"name": "WBC", "value": 12, "unit": "10^9/L", "status": "high", "is_abnormal": True}],
    )
    critical = _save(
        session_local,
        "benhnhan",
        "2026-08-12",
        [
            {"name": "WBC", "value": 12, "unit": "10^9/L", "status": "high", "is_abnormal": True},
            {"name": "Potassium", "value": 7, "unit": "mmol/L", "status": "critical_high", "is_abnormal": True, "is_critical": True},
        ],
    )
    with session_local() as session:
        assert session.get(db_module.LabReport, normal.report_id).status == "NORMAL"
        assert session.get(db_module.LabReport, abnormal.report_id).status == "ABNORMAL"
        assert session.get(db_module.LabReport, critical.report_id).status == "CRITICAL"


@pytest.mark.asyncio
async def test_delete_removes_report_and_decreases_count(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    report = _save(session_local, "benhnhan", "2026-08-10", [{"name": "WBC", "value": 7, "unit": "10^9/L"}])

    response = await client.delete(f"/api/v1/patient/me/lab-reports/{report.report_id}", headers=headers)
    assert response.status_code == 204

    response = await client.get("/api/v1/patient/me/dashboard", headers=headers)
    assert response.status_code == 200
    assert response.json()["total_reports"] == 0
    response = await client.get("/api/v1/patient/me/lab-reports", headers=headers)
    assert response.json()["reports"] == []
