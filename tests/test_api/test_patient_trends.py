from __future__ import annotations

import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import quote

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.api import routes
from src.main import app
from src.models import db as db_module
from src.models.orchestrator_schemas import TrendDataPayload
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, TrendResponse
from src.services import trend_service
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
async def test_wbc_trend_available_after_three_saved_reports(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text, value in [("2026-08-01", 7.0), ("2026-08-02", 12.0), ("2026-08-03", 10.5)]:
        _save(session_local, "benhnhan", date_text, [{"name": "WBC", "value": value, "unit": "10^9/L"}])

    catalog = await client.get("/api/v1/patient/me/trends/analytes", headers=headers)
    trend = await client.get(_trend_url("WBC"), headers=headers)

    assert catalog.status_code == 200, catalog.text
    analytes = {item["analyte_canonical"]: item for item in catalog.json()["analytes"]}
    assert analytes["WBC"]["result_count"] == 3
    assert analytes["WBC"]["trend_available"] is True
    assert trend.status_code == 200, trend.text
    assert trend.json()["trend_available"] is True
    assert [point["value"] for point in trend.json()["points"]] == [7.0, 12.0, 10.5]


@pytest.mark.asyncio
async def test_analyze_persistence_writes_canonical_fields_for_wbc_trends(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)

    async def fake_ainvoke(initial_state, config):
        raw = initial_state["raw_indicators"][0]
        return {
            "indicators": [
                {
                    "name": raw["name"],
                    "value": raw["value"],
                    "unit": raw["unit"],
                    "reference_low": 4.72,
                    "reference_high": 11.3,
                    "status": "normal",
                    "is_abnormal": False,
                    "is_critical": False,
                    "explanation": "",
                    "sources": [],
                }
            ],
            "has_critical_values": False,
            "critical_alerts": [],
            "guardrail_passed": True,
            "disclaimer": "Test disclaimer",
            "questions_for_doctor": [],
            "out_of_scope_indicators": [],
            "summary": "",
        }

    monkeypatch.setattr(routes.agent, "ainvoke", fake_ainvoke)

    for date_text, value in [("2026-08-01", 7.0), ("2026-08-02", 12.0), ("2026-08-03", 10.5)]:
        response = await client.post(
            "/api/v1/analyze",
            headers=headers,
            json={
                "patient_age": 35,
                "patient_gender": "male",
                "test_date": date_text,
                "indicators": [{"name": "WBC", "value": value, "unit": "10^9/L"}],
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["saved_report_id"] is not None

    with session_local() as session:
        indicators = (
            session.query(db_module.ReportIndicator)
            .join(db_module.LabReport)
            .filter(db_module.LabReport.patient_id == 1)
            .filter(db_module.ReportIndicator.name == "WBC")
            .order_by(db_module.LabReport.test_date)
            .all()
        )
        assert [item.analyte_canonical for item in indicators] == ["WBC", "WBC", "WBC"]
        assert [item.canonical_value for item in indicators] == [7.0, 12.0, 10.5]
        assert [item.canonical_unit for item in indicators] == ["10^9/L", "10^9/L", "10^9/L"]
        assert [item.indicator_catalog_id is not None for item in indicators] == [True, True, True]
        assert session.query(db_module.IndicatorCatalog).filter_by(canonical_name="WBC").count() == 1

    catalog = await client.get("/api/v1/patient/me/trends/analytes", headers=headers)
    trend = await client.get(_trend_url("WBC"), headers=headers)

    assert catalog.status_code == 200, catalog.text
    analytes = {item["analyte_canonical"]: item for item in catalog.json()["analytes"]}
    assert analytes["WBC"]["result_count"] == 3
    assert analytes["WBC"]["trend_available"] is True
    assert trend.status_code == 200, trend.text
    assert trend.json()["trend_available"] is True
    assert [point["value"] for point in trend.json()["points"]] == [7.0, 12.0, 10.5]


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
    assert response.json()["observed_direction"] is None


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
async def test_trend_explanation_extracts_text_from_block_content(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(
            return_value=SimpleNamespace(
                content=[
                    {
                        "type": "text",
                        "text": "Giá trị gần nhất cao hơn lần trước.",
                        "extras": {
                            "signature": (
                                "EnEKbwERTTIPtkzEixgfv0guRZpI1YymyuUYByuozm87IH0FJ4"
                                "immgHx4A75+8uIMw683NNMmSqV0wAa3viuo/CrPZSSmFv+NKcT+Tj4"
                            )
                        },
                    }
                ]
            )
        )
    )
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is False
    assert response.json()["explanation"] == "Giá trị gần nhất cao hơn lần trước."


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


def _save_glucose_series(session_local, values: list[float]):
    for index, value in enumerate(values):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index + 1:02d}",
            [{"name": "Fasting plasma glucose", "value": value, "unit": "mmol/L"}],
        )


@pytest.mark.asyncio
async def test_trend_sets_critical_status_for_glucose_below_low_threshold(isolated_client):
    """ADR-010 CRIT-TREND-03: điểm mới nhất vượt ngưỡng nguy kịch (< 55 mg/dL, tức
    khoảng < 3.05 mmol/L) phải set critical_status trên TrendResponse — kết nối trực
    tiếp với module ngưỡng nguy kịch dùng chung, không còn là điểm mù an toàn."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [5.0, 4.8, 2.0])

    response = await client.get(_trend_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] == "critical_low"
    assert payload["approaching_critical"] is False


@pytest.mark.asyncio
async def test_trend_sets_approaching_critical_when_moving_toward_high_threshold(isolated_client):
    """Ngưỡng cao FPG = 450 mg/dL (~24.98 mmol/L); biên 10% => ~[22.48, 27.47]
    mmol/L. 24.0 mmol/L nằm trong biên, chưa critical, và đang tăng từ 20.0."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [5.0, 20.0, 24.0])

    response = await client.get(_trend_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] is None
    assert payload["approaching_critical"] is True


@pytest.mark.asyncio
async def test_trend_has_no_critical_wiring_for_analyte_without_active_threshold(isolated_client):
    """LDL-C không có threshold active (ADR-009) — không được tự bịa ra cảnh báo nào."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] is None
    assert payload["approaching_critical"] is False


@pytest.mark.asyncio
async def test_trend_explanation_prepends_fixed_notice_when_critical(isolated_client, monkeypatch):
    """ADR-010 CRIT-TREND-03.4: thông báo liên hệ bác sĩ là văn bản cố định, không
    qua LLM — phải xuất hiện dù LLM trả lời bình thường."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [5.0, 4.8, 2.0])
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Giá trị gần nhất giảm mạnh so với lần trước."))
    )
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fallback"] is False
    assert payload["explanation"].startswith("Chỉ số này đang ở mức cần chú ý đặc biệt — vui lòng liên hệ bác sĩ sớm")
    assert "Giá trị gần nhất giảm mạnh so với lần trước." in payload["explanation"]


@pytest.mark.asyncio
async def test_trend_explanation_prepends_fixed_notice_even_when_llm_fails(isolated_client, monkeypatch):
    """Thông báo an toàn không được phụ thuộc vào LLM có khả dụng hay không —
    nếu không, đúng điểm mù mà nhóm trưởng đã cảnh báo vẫn còn tồn tại khi LLM lỗi."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [5.0, 4.8, 2.0])
    mock_llm = SimpleNamespace(ainvoke=AsyncMock(side_effect=RuntimeError("quota")))
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fallback"] is True
    assert payload["explanation"].startswith("Chỉ số này đang ở mức cần chú ý đặc biệt — vui lòng liên hệ bác sĩ sớm")


@pytest.mark.asyncio
async def test_trend_explanation_prompt_carries_matched_reference_range(isolated_client, monkeypatch):
    """ADR-010 CRIT-TREND-02: prompt phải mang cận khoảng tham chiếu đã khớp theo
    sex/age tại lần đo gần nhất — không chỉ giá trị điểm dữ liệu như trước đây."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    captured_prompt = {}

    async def fake_ainvoke(messages):
        captured_prompt["text"] = messages[0].content
        return SimpleNamespace(content="Giá trị gần nhất cao hơn lần trước.")

    mock_llm = SimpleNamespace(ainvoke=fake_ainvoke)
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_explain_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    assert "Khoảng tham chiếu đã khớp" in captured_prompt["text"]


@pytest.mark.asyncio
async def test_trend_guardrail_blocks_risk_inference_and_referral_language(isolated_client):
    """ADR-010 CRIT-TREND-01: từ vựng suy diễn nguy cơ / khuyến nghị thăm khám thêm
    phải bị chặn dù không phải chẩn đoán hay dự đoán tương lai trực tiếp."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    response = await client.get(_trend_url("LDL-C"), headers=headers)
    trend = TrendResponse.model_validate(response.json())

    assert validate_trend_explanation("Điều này cho thấy nguy cơ về sau.", trend)
    assert validate_trend_explanation("Bạn nên đi khám thêm để chắc chắn.", trend)
    assert not validate_trend_explanation("Giá trị gần nhất cao hơn lần trước.", trend)


@pytest.mark.asyncio
async def test_patient_report_detail_groups_indicators_by_section(isolated_client):
    """ADR-010 CRIT-TREND-06: trang kết quả một phiếu (bệnh nhân tự xem, không phải
    qua /history/{id} của bác sĩ) cũng phải có section — trước đây hai endpoint dùng
    hai code path khác nhau và chỉ một bên có section."""

    client, session_local = isolated_client
    headers = await _auth_headers(client)
    saved = _save(
        session_local,
        "benhnhan",
        "2026-08-01",
        [
            {"name": "LDL-C", "value": 2.1, "unit": "mmol/L"},
            {"name": "WBC", "value": 7.0, "unit": "10^9/L"},
        ],
    )

    response = await client.get(f"/api/v1/patient/me/lab-reports/{saved.report_id}", headers=headers)

    assert response.status_code == 200, response.text
    indicators = {item["analyte_canonical"]: item for item in response.json()["indicators"]}
    assert indicators["LDL-C"]["section"] == "lipids"
    assert indicators["LDL-C"]["section_label"] == "Mỡ máu & đường huyết"
    assert indicators["WBC"]["section"] == "hematology"
    assert indicators["WBC"]["section_label"] == "Huyết học"


@pytest.mark.asyncio
async def test_configured_max_gap_keeps_only_the_newest_contiguous_series(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    monkeypatch.setattr(trend_service, "_max_gap_days_for", lambda _: 10)
    for date_text, value in [
        ("2026-01-01", 2.0),
        ("2026-01-05", 2.1),
        ("2026-04-01", 2.2),
        ("2026-04-05", 2.3),
    ]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": value, "unit": "mmol/L"}])

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["trend_available"] is False
    assert payload["reason"] == "GAP_TOO_LARGE"
    assert payload["result_count"] == 2
    assert payload["points"] == []


@pytest.mark.asyncio
async def test_trend_guardrail_allows_grounded_trailing_zero_value(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text, value in [("2026-08-01", 2.1), ("2026-08-02", 3.2), ("2026-08-03", 4.0)]:
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": value, "unit": "mmol/L"}])
    response = await client.get(_trend_url("LDL-C"), headers=headers)
    trend = TrendResponse.model_validate(response.json())

    assert not validate_trend_explanation("Giá trị gần nhất là 4.0 mmol/L.", trend)


def _section_explain_url(section: str, trend_filter: str = "latest5") -> str:
    return f"/api/v1/patient/me/trends/sections/{section}/explain?filter={trend_filter}"


def _section_heatmap_url(section: str, trend_filter: str = "latest5") -> str:
    return f"/api/v1/patient/me/trends/sections/{section}/heatmap?filter={trend_filter}"


@pytest.mark.asyncio
async def test_section_heatmap_marks_missing_cell_instead_of_interpolating(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    # Phiếu giữa (2026-08-02) cố tình thiếu LDL-C — đúng kịch bản "dữ liệu thưa" cần xử lý.
    _save(session_local, "benhnhan", "2026-08-01", [{"name": "LDL-C", "value": 2.1, "unit": "mmol/L"}])
    _save(session_local, "benhnhan", "2026-08-02", [{"name": "Fasting plasma glucose", "value": 5.0, "unit": "mmol/L"}])
    _save(session_local, "benhnhan", "2026-08-03", [{"name": "LDL-C", "value": 2.3, "unit": "mmol/L"}])

    response = await client.get(_section_heatmap_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [c["test_date"] for c in payload["columns"]] == ["2026-08-01", "2026-08-02", "2026-08-03"]
    rows = {row["analyte_canonical"]: row["cells"] for row in payload["rows"]}
    assert [cell["value"] if cell else None for cell in rows["LDL-C"]] == [2.1, None, 2.3]


@pytest.mark.asyncio
async def test_section_heatmap_shows_analyte_with_only_one_result(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    # Chỉ 1 kết quả — line-chart (MIN_TREND_POINTS=3) sẽ không hiển thị, heatmap thì có.
    _save(session_local, "benhnhan", "2026-08-01", [{"name": "LDL-C", "value": 2.1, "unit": "mmol/L"}])

    response = await client.get(_section_heatmap_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    rows = {row["analyte_canonical"]: row["cells"] for row in payload["rows"]}
    assert rows["LDL-C"][0]["value"] == 2.1


@pytest.mark.asyncio
async def test_section_heatmap_latest5_scopes_by_report_not_per_analyte(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, date_text in enumerate(
        ["2026-04-10", "2026-05-10", "2026-06-10", "2026-07-10", "2026-08-01", "2026-08-10"]
    ):
        _save(session_local, "benhnhan", date_text, [{"name": "LDL-C", "value": 2.0 + index / 10, "unit": "mmol/L"}])

    response = await client.get(_section_heatmap_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [c["test_date"] for c in payload["columns"]] == [
        "2026-05-10",
        "2026-06-10",
        "2026-07-10",
        "2026-08-01",
        "2026-08-10",
    ]


@pytest.mark.asyncio
async def test_section_heatmap_invalid_section_returns_400(isolated_client):
    client, _ = isolated_client
    headers = await _auth_headers(client)

    response = await client.get(_section_heatmap_url("not-a-real-section"), headers=headers)

    assert response.status_code == 400, response.text


def _save_ldl_and_fpg_series(session_local):
    for index in range(3):
        date_text = f"2026-08-{index + 1:02d}"
        _save(
            session_local,
            "benhnhan",
            date_text,
            [
                {"name": "LDL-C", "value": 2.1 + index / 10, "unit": "mmol/L"},
                {"name": "Fasting plasma glucose", "value": 5.0 + index / 10, "unit": "mmol/L"},
            ],
        )


@pytest.mark.asyncio
async def test_section_trend_explanation_covers_multiple_analytes(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_and_fpg_series(session_local)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="LDL-C và FPG cùng tăng qua các lần đo."))
    )
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is False
    assert response.json()["explanation"] == "LDL-C và FPG cùng tăng qua các lần đo."
    assert mock_llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_section_trend_explanation_blocks_group_diagnosis(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_and_fpg_series(session_local)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Sự kết hợp này cho thấy nguy cơ tim mạch."))
    )
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is True
    assert response.json()["reason"] == "GUARDRAIL_BLOCKED"


@pytest.mark.asyncio
async def test_section_trend_explanation_single_eligible_delegates_to_single_analyte(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Giá trị gần nhất cao hơn lần trước."))
    )
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)
    monkeypatch.setattr("src.services.trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("lipids"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is False
    assert response.json()["explanation"] == "Giá trị gần nhất cao hơn lần trước."
    assert mock_llm.ainvoke.await_count == 1


@pytest.mark.asyncio
async def test_section_trend_explanation_no_eligible_returns_fallback(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_ldl_series(session_local, 3)
    mock_llm = SimpleNamespace(ainvoke=AsyncMock())
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("hematology"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["fallback"] is True
    assert response.json()["reason"] == "INSUFFICIENT_DATA"
    assert mock_llm.ainvoke.await_count == 0


@pytest.mark.asyncio
async def test_section_trend_explanation_invalid_section_returns_400(isolated_client, monkeypatch):
    client, _ = isolated_client
    headers = await _auth_headers(client)
    mock_llm = SimpleNamespace(ainvoke=AsyncMock())
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("unknown"), headers=headers)

    assert response.status_code == 400
    assert mock_llm.ainvoke.await_count == 0


@pytest.mark.asyncio
async def test_section_trend_explanation_escalates_with_fixed_notice(isolated_client, monkeypatch):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, (name, value) in enumerate(
        [
            ("Creatinine", 80),
            ("Potassium", 3.4),
            ("Creatinine", 82),
            ("Potassium", 3.1),
            ("Creatinine", 85),
            ("Potassium", 2.8),
        ],
        start=1,
    ):
        date_text = f"2026-08-{index:02d}"
        _save(session_local, "benhnhan", date_text, [{"name": name, "value": value, "unit": "umol/L" if name == "Creatinine" else "mmol/L"}])
    mock_llm = SimpleNamespace(
        ainvoke=AsyncMock(return_value=SimpleNamespace(content="Creatinine và Potassium cùng tăng qua các lần đo."))
    )
    monkeypatch.setattr("src.services.section_trend_explanation_service.get_llm", lambda: mock_llm)

    response = await client.post(_section_explain_url("chemistry"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["fallback"] is False
    assert payload["explanation"].startswith("Chỉ số này đang ở mức cần chú ý đặc biệt")
    assert payload["explanation"].endswith("Creatinine và Potassium cùng tăng qua các lần đo.")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("values", "expected_direction"),
    [
        ([6.5, 8.1, 12.0], "increasing"),
        ([7.4, 7.1, 6.8], "decreasing"),
        ([82.0, 88.0, 84.0], None),
        ([82.0, 82.0, 82.0], None),
        ([82.0, 83.0, 83.0], None),
    ],
)
async def test_observed_direction_uses_strict_whole_series_monotonicity(
    isolated_client,
    values,
    expected_direction,
):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate(values, start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "LDL-C", "value": value, "unit": "mmol/L"}],
        )

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["observed_direction"] == expected_direction


@pytest.mark.asyncio
async def test_observed_direction_is_none_when_two_points_are_insufficient(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate([6.5, 8.1], start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "LDL-C", "value": value, "unit": "mmol/L"}],
        )

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    assert response.json()["trend_available"] is False
    assert response.json()["reason"] == "INSUFFICIENT_DATA"
    assert response.json()["observed_direction"] is None
    assert trend_service.MIN_TREND_POINTS == 3


@pytest.mark.asyncio
async def test_observed_direction_uses_returned_chronological_order_not_insertion_order(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for date_text, value in [
        ("2026-08-03", 12.0),
        ("2026-08-01", 6.5),
        ("2026-08-02", 8.1),
    ]:
        _save(
            session_local,
            "benhnhan",
            date_text,
            [{"name": "LDL-C", "value": value, "unit": "mmol/L"}],
        )

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [point["value"] for point in payload["points"]] == [6.5, 8.1, 12.0]
    assert payload["observed_direction"] == "increasing"


@pytest.mark.asyncio
async def test_observed_direction_uses_only_returned_latest5_series(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate([100.0, 50.0, 1.0, 2.0, 3.0, 4.0, 5.0], start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "LDL-C", "value": value, "unit": "mmol/L"}],
        )

    response = await client.get(_trend_url("LDL-C"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert [point["value"] for point in payload["points"]] == [1.0, 2.0, 3.0, 4.0, 5.0]
    assert payload["observed_direction"] == "increasing"


@pytest.mark.asyncio
async def test_unknown_assessment_does_not_change_numeric_observed_direction(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate([75.0, 80.0, 85.0], start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "Creatinine", "value": value, "unit": "umol/L", "status": "unknown"}],
        )

    response = await client.get(_trend_url("Creatinine"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["observed_direction"] == "increasing"
    assert payload["points"][-1]["assessment"] == "unknown"


@pytest.mark.asyncio
async def test_trend_runtime_critical_authority_uses_current_detector_not_persisted_snapshot(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [5.0, 4.8, 2.0])

    response = await client.get(_trend_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] == "critical_low"
    assert payload["critical_alert"]["indicator_name"] == "Fasting plasma glucose"
    assert payload["critical_alert"]["value"] == 2.0
    assert payload["critical_alert"]["unit"] == "mmol/L"
    current_evaluation = trend_service.evaluate_critical("Fasting plasma glucose", 2.0, "mmol/L")
    assert payload["critical_alert"]["message"] == current_evaluation.alert_message


@pytest.mark.asyncio
async def test_persisted_critical_snapshot_cannot_promote_current_noncritical_trend(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate([4.0, 4.1], start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "Potassium", "value": value, "unit": "mmol/L"}],
        )
    latest = _save(
        session_local,
        "benhnhan",
        "2026-08-03",
        [{"name": "Potassium", "value": 4.2, "unit": "mmol/L"}],
    )
    with session_local() as session:
        report = session.get(db_module.LabReport, latest.report_id)
        report.critical_alerts.append(
            db_module.ReportCriticalAlert(
                indicator_name="Potassium",
                value=4.2,
                unit="mmol/L",
                message="Historical snapshot only.",
            )
        )
        session.commit()

    response = await client.get(_trend_url("Potassium"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] is None
    assert payload["approaching_critical"] is False
    assert payload["critical_alert"] is None


@pytest.mark.asyncio
async def test_high_assessment_does_not_imply_current_critical_alert(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    for index, value in enumerate([4.5, 5.0, 5.5], start=1):
        _save(
            session_local,
            "benhnhan",
            f"2026-08-{index:02d}",
            [{"name": "Potassium", "value": value, "unit": "mmol/L", "status": "high"}],
        )

    response = await client.get(_trend_url("Potassium"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["points"][-1]["assessment"] == "high"
    assert payload["critical_status"] is None
    assert payload["critical_alert"] is None


@pytest.mark.asyncio
async def test_current_critical_evaluation_applies_only_to_latest_returned_point(isolated_client):
    client, session_local = isolated_client
    headers = await _auth_headers(client)
    _save_glucose_series(session_local, [2.0, 4.8, 5.0])

    response = await client.get(_trend_url("Fasting plasma glucose"), headers=headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["critical_status"] is None
    assert payload["critical_alert"] is None


def _minimal_trend_response(**updates):
    payload = {
        "analyte_canonical": "WBC",
        "display_name": "WBC",
        "canonical_unit": "G/L",
        "filter": "latest5",
        "result_count": 3,
        "trend_available": True,
        "points": [
            {"report_id": 1, "test_date": "2026-08-01", "value": 6.5, "assessment": "normal"},
            {"report_id": 2, "test_date": "2026-08-02", "value": 8.1, "assessment": "normal"},
            {"report_id": 3, "test_date": "2026-08-03", "value": 12.0, "assessment": "high"},
        ],
    }
    payload.update(updates)
    return payload


@pytest.mark.parametrize("direction", ["increasing", "decreasing", None])
def test_trend_response_accepts_only_approved_observed_directions(direction):
    trend = TrendResponse.model_validate(_minimal_trend_response(observed_direction=direction))

    assert trend.observed_direction == direction


@pytest.mark.parametrize("direction", ["stable", "improving", "worsening", "up", "down"])
def test_trend_response_rejects_unapproved_observed_directions(direction):
    with pytest.raises(ValidationError):
        TrendResponse.model_validate(_minimal_trend_response(observed_direction=direction))


def test_trend_data_payload_serializes_current_detector_facts_unchanged():
    trend = TrendResponse.model_validate(
        _minimal_trend_response(
            observed_direction="increasing",
            critical_status="critical_high",
            critical_alert={
                "indicator_name": "WBC",
                "value": 12.0,
                "unit": "G/L",
                "message": "Approved deterministic warning.",
            },
        )
    )

    payload = TrendDataPayload(trend=trend).model_dump(mode="json")

    assert payload["trend"]["observed_direction"] == "increasing"
    assert payload["trend"]["critical_alert"] == {
        "indicator_name": "WBC",
        "value": 12.0,
        "unit": "G/L",
        "message": "Approved deterministic warning.",
    }
