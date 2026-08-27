import pytest

from src.agents.nodes import analyzer_node as analyzer_module
from src.agents.nodes import input_integrity_node as integrity_module
from src.api.deps import CurrentUser
from src.models.db import User
from src.models.ocr_schemas import OCRIndicatorDraft
from src.services.input_integrity import InputIntegrityEvaluator, PlausibilityRepository
from src.services.ocr_review_gate import create_review_lifecycle, prepare_review, review_token_expires_at


async def _auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _active_fixture_evaluator() -> InputIntegrityEvaluator:
    return InputIntegrityEvaluator(
        PlausibilityRepository.from_dict(
            {
                "rules": [
                    {
                        "rule_id": "TEST-ONLY-POTASSIUM-BOUND",
                        "analyte": "Potassium",
                        "canonical_unit": "mmol/L",
                        "lower_bound": 0,
                        "lower_operator": ">=",
                        "upper_bound": 10,
                        "upper_operator": "<=",
                        "source_id": "TEST-FIXTURE-NON-MEDICAL",
                        "source": "Synthetic test fixture",
                        "source_section": "test-only",
                        "reason": "Exercise endpoint enforcement only",
                        "status": "ACTIVE",
                    }
                ]
            }
        )
    )


@pytest.fixture
def active_integrity_fixture(monkeypatch):
    monkeypatch.setattr(
        integrity_module,
        "get_input_integrity_evaluator",
        _active_fixture_evaluator,
    )
    monkeypatch.setattr(
        analyzer_module,
        "get_llm",
        lambda: (_ for _ in ()).throw(AssertionError("analyzer LLM must not run")),
    )


def _assert_review_response(payload):
    indicator = payload["indicators"][0]
    assert indicator["value"] == 500
    assert indicator["canonical_value"] == 500
    assert indicator["input_integrity_status"] == "NEED_REVIEW"
    assert indicator["input_integrity_reason_code"] == "VALUE_OUTSIDE_VALIDATED_BOUND"
    assert indicator["input_integrity_rule_id"] == "TEST-ONLY-POTASSIUM-BOUND"
    assert indicator["status"] == "unknown"
    assert indicator["critical_status"] is None
    assert indicator["is_abnormal"] is False
    assert indicator["is_critical"] is False
    assert "kiểm tra lại" in indicator["input_integrity_message"]
    assert payload["critical_alerts"] == []
    assert payload["has_critical_values"] is False


@pytest.mark.asyncio
async def test_manual_analyze_endpoint_enforces_integrity_gate(
    client,
    active_integrity_fixture,
):
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/analyze",
        headers=headers,
        json={
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-08-27",
            "language": "vi",
            "indicators": [{"name": "Potassium", "value": 500, "unit": "mmol/L"}],
        },
    )

    assert response.status_code == 200, response.text
    _assert_review_response(response.json())


@pytest.mark.asyncio
async def test_ocr_confirm_endpoint_enforces_same_gate_after_hitl(
    client,
    test_db,
    active_integrity_fixture,
):
    expires_at = review_token_expires_at()
    with test_db.session() as db:
        user = db.query(User).filter(User.username == "benhnhan").one()
        lifecycle = create_review_lifecycle(
            db,
            current_user=CurrentUser(user.username, user.role, user_id=user.id),
            expires_at=expires_at,
        )
    drafts, token = prepare_review(
        [
            OCRIndicatorDraft(
                name="Potassium",
                value=500,
                unit="mmol/L",
                confidence=0.95,
                raw_text="Potassium 500 mmol/L",
            )
        ],
        username="benhnhan",
        review_id=lifecycle.review_id,
        expires_at=expires_at,
    )
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/confirm",
        headers=headers,
        json={
            "review_token": token,
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-08-27",
            "language": "vi",
            "indicators": [
                {
                    "draft_id": drafts[0].draft_id,
                    "name": "Potassium",
                    "value": 500,
                    "unit": "mmol/L",
                    "included": True,
                    "reviewed": True,
                    "low_confidence_acknowledged": False,
                }
            ],
        },
    )

    assert response.status_code == 200, response.text
    _assert_review_response(response.json())
