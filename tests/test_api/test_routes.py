from unittest.mock import AsyncMock

import pytest

from src.api import routes


def graph_result(**overrides):
    result = {
        "indicators": [
            {
                "name": "WBC",
                "value": 7.0,
                "unit": "10^9/L",
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
    }
    result.update(overrides)
    return result


async def post_analyze_with_graph_result(client, monkeypatch, final_state):
    mock_ainvoke = AsyncMock(return_value=final_state)
    monkeypatch.setattr(routes.agent, "ainvoke", mock_ainvoke)
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-07-30",
            "indicators": [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}],
        },
    )
    mock_ainvoke.assert_awaited_once()
    return response


async def _auth_headers(client, username="benhnhan", password="benhnhan123"):
    response = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert response.status_code == 200, response.text
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_login_valid_demo_account(client):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "bacsi", "password": "bacsi123"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["role"] == "doctor"
    assert data["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password(client):
    response = await client.post(
        "/api/v1/auth/login", json={"username": "benhnhan", "password": "sai-mat-khau"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_analyze_requires_auth(client):
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-07-30",
        "indicators": [{"name": "WBC", "value": 7.2, "unit": "10^3/uL"}],
    }
    response = await client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_analyze_valid_report(client):
    headers = await _auth_headers(client)
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-07-30",
        "indicators": [
            {"name": "WBC", "value": 7.2, "unit": "10^3/uL"},
            {"name": "Glucose", "value": 95, "unit": "mg/dL"},
        ],
    }
    response = await client.post("/api/v1/analyze", json=payload, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert len(data["indicators"]) == 2
    assert data["indicators"][0]["name"] == "WBC"
    assert data["indicators"][0]["status"] == "normal"
    assert "disclaimer" in data and data["disclaimer"]
    assert data["is_placeholder"] is False


@pytest.mark.asyncio
async def test_analyze_requires_at_least_one_indicator(client):
    headers = await _auth_headers(client)
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-07-30",
        "indicators": [],
    }
    response = await client.post("/api/v1/analyze", json=payload, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_analyze_rejects_invalid_date_format(client):
    headers = await _auth_headers(client)
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "30/07/2026",
        "indicators": [{"name": "WBC", "value": 7.2, "unit": "10^3/uL"}],
    }
    response = await client.post("/api/v1/analyze", json=payload, headers=headers)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_api_01_source_serialization(client, monkeypatch):
    final_state = graph_result(
        indicators=[
            {
                "name": "WBC",
                "value": 7.0,
                "unit": "10^9/L",
                "reference_low": 4.72,
                "reference_high": 11.3,
                "status": "normal",
                "is_abnormal": False,
                "is_critical": False,
                "explanation": "source test",
                "sources": ["https://example.test/source"],
            }
        ]
    )

    response = await post_analyze_with_graph_result(client, monkeypatch, final_state)

    assert response.status_code == 200
    assert response.json()["indicators"][0]["sources"] == ["https://example.test/source"]


@pytest.mark.asyncio
async def test_api_02_disclaimer_serialization(client, monkeypatch):
    response = await post_analyze_with_graph_result(
        client,
        monkeypatch,
        graph_result(disclaimer="Custom disclaimer for contract test"),
    )

    assert response.status_code == 200
    assert response.json()["disclaimer"] == "Custom disclaimer for contract test"


@pytest.mark.asyncio
async def test_api_03_critical_serialization(client, monkeypatch):
    response = await post_analyze_with_graph_result(
        client,
        monkeypatch,
        graph_result(
            indicators=[
                {
                    "name": "Potassium",
                    "value": 6.5,
                    "unit": "mmol/L",
                    "reference_low": None,
                    "reference_high": None,
                    "status": "critical_high",
                    "is_abnormal": True,
                    "is_critical": True,
                    "explanation": "",
                    "sources": [],
                }
            ],
            has_critical_values=True,
            critical_alerts=[
                {
                    "indicator_name": "Potassium",
                    "value": 6.5,
                    "unit": "mmol/L",
                    "message": "critical high",
                }
            ],
        ),
    )

    data = response.json()
    assert response.status_code == 200
    assert data["has_critical_values"] is True
    assert data["indicators"][0]["status"] == "critical_high"
    assert data["critical_alerts"][0]["indicator_name"] == "Potassium"


@pytest.mark.asyncio
async def test_api_04_unknown_indicator_serialization(client, monkeypatch):
    response = await post_analyze_with_graph_result(
        client,
        monkeypatch,
        graph_result(
            indicators=[
                {
                    "name": "HGB",
                    "value": 140,
                    "unit": "g/L",
                    "reference_low": None,
                    "reference_high": None,
                    "status": "unknown",
                    "is_abnormal": False,
                    "is_critical": False,
                    "explanation": "",
                    "sources": [],
                }
            ]
        ),
    )

    indicator = response.json()["indicators"][0]
    assert response.status_code == 200
    assert indicator["status"] == "unknown"
    assert indicator["reference_low"] is None
    assert indicator["reference_high"] is None


@pytest.mark.asyncio
async def test_api_05_internal_reason_not_serialized(client, monkeypatch):
    response = await post_analyze_with_graph_result(
        client,
        monkeypatch,
        graph_result(
            indicators=[
                {
                    "name": "HGB",
                    "value": 140,
                    "unit": "g/L",
                    "reference_low": None,
                    "reference_high": None,
                    "status": "unknown",
                    "is_abnormal": False,
                    "is_critical": False,
                    "explanation": "",
                    "sources": [],
                    "reason": "unit_data_conflict",
                }
            ]
        ),
    )

    assert response.status_code == 200
    assert "reason" not in response.json()["indicators"][0]
