import pytest


@pytest.mark.asyncio
async def test_liveness_does_not_depend_on_optional_rag(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readiness_reports_rag_as_an_independent_optional_component(client):
    response = await client.get("/ready")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in {"ok", "degraded"}
    assert payload["components"]["api"]["status"] == "ready"
    assert payload["components"]["rag"]["required"] is False
