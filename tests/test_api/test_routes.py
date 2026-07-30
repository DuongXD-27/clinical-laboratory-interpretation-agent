import pytest


@pytest.mark.asyncio
async def test_health(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_analyze_valid_report(client):
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-07-30",
        "indicators": [
            {"name": "WBC", "value": 7.2, "unit": "10^3/uL"},
            {"name": "Glucose", "value": 95, "unit": "mg/dL"},
        ],
    }
    response = await client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["indicators"]) == 2
    assert data["indicators"][0]["name"] == "WBC"
    assert "disclaimer" in data and data["disclaimer"]


@pytest.mark.asyncio
async def test_analyze_requires_at_least_one_indicator(client):
    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-07-30",
        "indicators": [],
    }
    response = await client.post("/api/v1/analyze", json=payload)
    assert response.status_code == 422
