from __future__ import annotations

import datetime
from types import SimpleNamespace
from urllib.parse import quote
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.main import app
from src.models import db as db_module
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, TrendResponse
from src.services.auth import create_access_token
from src.services.lab_history_service import save_analyzed_report
from src.services.trend_explanation_service import validate_trend_explanation


@pytest_asyncio.fixture
async def isolated_client(tmp_path, monkeypatch):
    db_path = tmp_path / "patient_trends.db"
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


def _token_headers(
    username: str,
    role: str = "patient",
    user_id: int = 999999,
):
    token = create_access_token(
        username=username,
        role=role,
        user_id=user_id,
    )
    return {"Authorization": f"Bearer {token}"}


def _analysis(rows):
    return AnalyzeResponse(
        indicators=[
            {
                "name": row["name"],
                "value": row["value"],
                "unit": row["unit"],
                "canonical_value": row.get("canonical_value"),
                "canonical_unit": row.get("canonical_unit"),
                "reference_low": row.get("reference_low"),
                "reference_high": row.get("reference_high"),
                "status": row.get("status", "normal"),
                "is_abnormal": row.get("status") in {"low", "high", "critical_low", "critical_high"},
                "is_critical": row.get("status") in {"critical_low", "critical_high"},
                "explanation": "",
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


def _trend_url(analyte: str, trend_filter: str = "latest5") -> str:
    return f"/api/v1/patient/me/trends/{quote(analyte, safe='')}?filter={trend_filter}"


def _explain_url(analyte: str, trend_filter: str = "latest5") -> str:
    return f"/api/v1/patient/me/trends/{quote(analyte, safe='')}/explain?filter={trend_filter}"


def _save_ldl_series(session_local, count: int = 3):
    for index in range(count):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index + 1:02d}",
            [{"name": "LDL-C", "value": 2.1 + index / 10, "unit": "mmol/L"}],
        )


@pytest.mark.asyncio
async def test_trend_analyte_catalog_counts_valid_points_and_aliases(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text, glucose_name in [
        ("2026-08-01", "Glucose"),
        ("2026-08-02", "Fasting Blood Glucose"),
        ("2026-08-03", "Fasting plasma glucose"),
    ]:
        _save(
            session_local,
            "benhnhan",
            date_text,
            [
                {"name": "LDL-C", "value": 2.1, "unit": "mmol/L"},
                {"name": glucose_name, "value": 5.1, "unit": "mmol/L"},
            ],
        )
    for date_text in ["2026-08-04", "2026-08-05"]:
        _save(session_local, "benhnhan", date_text, [{"name": "Creatinine", "value": 80, "unit": "umol/L"}])

    response = await client.get("/api/v1/patient/me/trends/analytes", headers=headers)

    assert response.status_code == 200, response.text
    analytes = {item["analyte_canonical"]: item for item in response.json()["analytes"]}
    assert analytes["LDL-C"]["result_count"] == 3
    assert analytes["LDL-C"]["trend_available"] is True
    assert analytes["Fasting plasma glucose"]["result_count"] == 3
    assert analytes["Fasting plasma glucose"]["trend_available"] is True
    assert analytes["Creatinine"]["result_count"] == 2
    assert analytes["Creatinine"]["trend_available"] is False


@pytest.mark.asyncio
async def test_latest5_returns_five_newest_analyte_results_oldest_to_newest(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, date_text in enumerate(
        ["2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-01", "2026-08-10", "2026-08-12"]
    ):
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": 2.0 + index / 10, "unit": "mmol/L"}])
    _save(session_local, "benhnhan", "2026-08-13", [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}])

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["trend_available"] is True
    assert payload["result_count"] == 5
    assert [point["test_date"] for point in payload["points"]] == [
        "2026-06-10",
        "2026-07-10",
        "2026-08-01",
        "2026-08-10",
        "2026-08-12",
    ]
    assert [point["value"] for point in payload["points"]] == [2.2, 2.3, 2.4, 2.5, 2.6]


@pytest.mark.asyncio
async def test_three_months_uses_test_date_and_minimum_three_after_filter(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text in ["2026-02-01", "2026-03-01", "2026-04-01", "2026-05-01"]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": 2.1, "unit": "mmol/L"}])
    for date_text, value in [("2026-06-01", 2.6), ("2026-08-01", 2.8)]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": value, "unit": "mmol/L"}])

    response = await client.get(_trend_url("LDL-C", "three_months"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["trend_available"] is False
    assert payload["reason"] == "INSUFFICIENT_DATA"
    assert payload["result_count"] == 2
    assert payload["points"] == []


@pytest.mark.asyncio
async def test_deleted_report_no_longer_contributes_to_trend(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    reports = [
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": value, "unit": "mmol/L"}])
        for date_text, value in [("2026-08-01", 2.1), ("2026-08-02", 2.2), ("2026-08-03", 2.3)]
    ]

    response = await client.get(_trend_url("LDL-C"), headers=headers)
    assert response.json()["trend_available"] is True

    response = await client.delete(f"/api/v1/patient/me/lab-reports/{reports[0].report_id}", headers=headers)
    assert response.status_code == 204
    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200
    assert response.json()["trend_available"] is False
    assert response.json()["result_count"] == 2


@pytest.mark.asyncio
async def test_duplicate_upload_attempt_does_not_create_extra_trend_point(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    rows = [{"name": "LDL-C", "value": 2.1, "unit": "mmol/L"}]
    for date_text in ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04", "2026-08-05"]:
        _save(session_local, "benhnhan", date_text, rows)
    duplicate = _save(session_local, "benhnhan", "2026-08-05", rows)
    assert duplicate.duplicate is True

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200
    assert response.json()["result_count"] == 5


@pytest.mark.asyncio
async def test_trend_is_patient_isolated(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    with session_local() as session:
        session.add(db_module.User(username="patient2", password_hash="x", role="patient"))
        session.commit()
    _save(session_local, "patient2", "2026-08-01", [{"name": "LDL-C", "value": 9.9, "unit": "mmol/L"}])
    _save(session_local, "patient2", "2026-08-02", [{"name": "LDL-C", "value": 9.8, "unit": "mmol/L"}])
    _save(session_local, "patient2", "2026-08-03", [{"name": "LDL-C", "value": 9.7, "unit": "mmol/L"}])

    response = await client.get("/api/v1/patient/me/trends/analytes", headers=headers)

    assert response.status_code == 200
    assert response.json()["analytes"] == []


@pytest.mark.asyncio
async def test_doctor_cannot_access_patient_trends(isolated_client):
    client, _ = isolated_client
    response = await client.get(
        "/api/v1/patient/me/trends/analytes",
        headers=_token_headers("bacsi", "doctor"),
    )

    assert response.status_code == 403


@pytest.mark.asyncio
async def test_unit_inconsistency_fails_safe_without_chart_points(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text in ["2026-08-01", "2026-08-02", "2026-08-03"]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": 2.1, "unit": "mmol/L"}])
    with session_local() as session:
        patient = session.query(db_module.User).filter_by(username="benhnhan").one()
        report = db_module.LabReport(patient_id=patient.id, test_date=datetime.date(2026, 8, 4))
        report.indicators.append(
            db_module.ReportIndicator(
                analyte_raw="LDL-C",
                analyte_canonical="LDL-C",
                raw_value=120,
                raw_unit="mg/dL",
                canonical_value=120,
                canonical_unit="mg/dL",
                name="LDL-C",
                value=120,
                unit="mg/dL",
                status="high",
            )
        )
        session.add(report)
        session.commit()

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200
    assert response.json()["trend_available"] is False
    assert response.json()["reason"] == "DATA_QUALITY_ERROR"
    assert response.json()["points"] == []


@pytest.mark.asyncio
async def test_trend_explanation_generated_with_mocked_llm(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Giá trị gần nhất cao hơn lần trước."))
    )
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is False
    assert response.json()["explanation"] == "Giá trị gần nhất cao hơn lần trước."
    assert mock_llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_trend_explanation_not_called_for_insufficient_points(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 2)
    mock_llm = SimpleNamespace(ainvoke=AsyncMock())
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 400
    assert mock_llm.ainvoke.await_count == 0


@pytest.mark.asyncio
async def test_trend_explanation_provider_error_returns_fallback(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("quota")))
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert response.json()["reason"] == "PROVIDER_ERROR"


@pytest.mark.asyncio
async def test_trend_explanation_guardrail_violation_returns_fallback(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Bạn mắc bệnh và lần tới giá trị có thể là 9.9."))
    )
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 200
    assert response.json()["fallback"] is True
    assert response.json()["reason"] == "GUARDRAIL_BLOCKED"


@pytest.mark.asyncio
async def test_trend_guardrail_blocks_restricted_language(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    response = await client.get(_trend_url("LDL-C"), headers=headers)
    trend = TrendResponse.model_validate(response.json())

    assert validate_trend_explanation("Bạn mắc bệnh.", trend)
    assert validate_trend_explanation("Nguyên nhân là do ăn nhiều chất béo.", trend)
    assert validate_trend_explanation("Bạn nên dùng thuốc.", trend)
    assert validate_trend_explanation("Lần tới giá trị có thể là 3.9.", trend)
    assert not validate_trend_explanation("Giá trị gần nhất cao hơn lần trước.", trend)


@pytest.mark.asyncio
async def test_trend_guardrail_allows_grounded_trailing_zero_value(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text, value in [("2026-08-01", 2.1), ("2026-08-02", 3.2), ("2026-08-03", 4.0)]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": value, "unit": "mmol/L"}])
    response = await client.get(_trend_url("LDL-C"), headers=headers)
    trend = TrendResponse.model_validate(response.json())

    assert not validate_trend_explanation("Giá trị gần nhất là 4.0 mmol/L.", trend)
