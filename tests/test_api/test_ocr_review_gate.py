from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.api import ocr_routes, routes
from src.config import get_settings
from src.models.ocr_schemas import OCRIndicatorDraft, OCRReviewedIndicator
from src.models.schemas import IndicatorInputSchema
from src.services.ocr_review_gate import prepare_review


async def _auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def _review_payload(*, acknowledged: bool, reviewed: bool = True):
    drafts, token = prepare_review(
        [
            OCRIndicatorDraft(
                name="Fasting Blood Glucose",
                value=5.2,
                unit="mmol/L",
                confidence=0.4,
                raw_text="Fasting Blood Glucose 5.2 mmol/L",
            )
        ],
        username="benhnhan",
    )
    assert drafts[0].needs_review is True
    return {
        "review_token": token,
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-07",
        "indicators": [
            {
                "draft_id": drafts[0].draft_id,
                "name": "Fasting Blood Glucose",
                "value": 5.2,
                "unit": "mmol/L",
                "included": True,
                "reviewed": reviewed,
                "low_confidence_acknowledged": acknowledged,
            }
        ],
    }


@pytest.mark.parametrize("invalid_value", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize(
    "schema, payload",
    [
        (
            OCRIndicatorDraft,
            {"name": "Glucose", "unit": "mmol/L", "confidence": 0.9},
        ),
        (
            OCRReviewedIndicator,
            {
                "draft_id": "draft-1",
                "name": "Glucose",
                "unit": "mmol/L",
                "reviewed": True,
            },
        ),
        (IndicatorInputSchema, {"name": "Glucose", "unit": "mmol/L"}),
    ],
)
def test_non_finite_lab_values_are_rejected(schema, payload, invalid_value):
    with pytest.raises(ValidationError):
        schema(**payload, value=invalid_value)


def test_fix2_ocr_generic_glucose_is_unsupported_but_explicit_fasting_is_supported():
    drafts, _token = prepare_review(
        [
            OCRIndicatorDraft(
                name="Glucose",
                value=5.2,
                unit="mmol/L",
                confidence=0.95,
            ),
            OCRIndicatorDraft(
                name="Fasting Blood Glucose",
                value=5.2,
                unit="mmol/L",
                confidence=0.95,
            ),
        ],
        username="benhnhan",
    )

    generic, explicit_fasting = drafts
    assert generic.supported is False
    assert generic.unsupported_reason
    assert explicit_fasting.supported is True
    assert explicit_fasting.unsupported_reason == ""


@pytest.mark.asyncio
async def test_ocr_confirm_requires_auth(client):
    response = await client.post(
        "/api/v1/ocr/confirm",
        json=_review_payload(acknowledged=True),
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ocr_upload_requires_auth(client):
    response = await client.post(
        "/api/v1/ocr/upload",
        files={"file": ("report.png", b"image", "image/png")},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_ocr_upload_reports_missing_provider_config_with_cors(client, monkeypatch):
    def missing_provider():
        raise ocr_routes.VisionAdapterError(
            "OCR chưa được cấu hình: thiếu GOOGLE_API_KEY trên backend."
        )

    monkeypatch.setattr(ocr_routes, "_get_dependencies", missing_provider)
    monkeypatch.setattr(get_settings(), "ocr_upload_mode", "open_with_consent")
    headers = await _auth_headers(client)
    headers["Origin"] = "http://localhost:3000"
    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("report.png", b"image", "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 503
    assert "GOOGLE_API_KEY" in response.json()["detail"]
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


@pytest.mark.asyncio
async def test_ocr_upload_rejects_empty_extraction(client, monkeypatch):
    class FakeProcessor:
        def process(self, _raw, *, filename):
            return SimpleNamespace(bytes=b"processed", mime_type="image/jpeg")

    class EmptyAdapter:
        model = "test-vision"

        async def extract(self, _image_bytes, _mime_type):
            return []

    monkeypatch.setattr(
        ocr_routes,
        "_get_dependencies",
        lambda: (FakeProcessor(), EmptyAdapter()),
    )
    monkeypatch.setattr(get_settings(), "ocr_upload_mode", "open_with_consent")
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("not-a-lab-report.png", b"image", "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 422
    assert "Không tìm thấy chỉ số xét nghiệm" in response.json()["detail"]


@pytest.mark.asyncio
async def test_ocr_upload_marks_low_confidence_and_issues_token(client, monkeypatch):
    class FakeProcessor:
        def process(self, _raw, *, filename):
            assert filename == "report.png"
            return SimpleNamespace(bytes=b"processed", mime_type="image/jpeg")

    class FakeAdapter:
        model = "test-vision"

        async def extract(self, _image_bytes, _mime_type):
            return [
                OCRIndicatorDraft(
                    name="Fasting Blood Glucose",
                    value=5.2,
                    unit="mmol/L",
                    confidence=0.4,
                )
            ]

    monkeypatch.setattr(
        ocr_routes,
        "_get_dependencies",
        lambda: (FakeProcessor(), FakeAdapter()),
    )
    # Test này kiểm tra riêng cơ chế confidence/review token, nên mở chế độ
    # nhận ảnh tuỳ ý và tick sẵn consent — hai cổng đó có bộ test riêng ở
    # tests/test_api/test_ocr_public_safeguards.py.
    monkeypatch.setattr(get_settings(), "ocr_upload_mode", "open_with_consent")
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("report.png", b"image", "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["review_token"]
    assert payload["indicators"][0]["needs_review"] is True
    server_timing = response.headers["server-timing"]
    assert "ocr-file-read;dur=" in server_timing
    assert "ocr-preprocess;dur=" in server_timing
    # Direct Gemini receives inline bytes; base64 belongs only to the fallback.
    assert "ocr-base64;dur=" not in server_timing
    assert "ocr-review-prepare;dur=" in server_timing


@pytest.mark.asyncio
async def test_ocr_upload_marks_unsupported_rows(client, monkeypatch):
    class FakeProcessor:
        def process(self, _raw, *, filename):
            return SimpleNamespace(bytes=b"processed", mime_type="image/jpeg")

    class FakeAdapter:
        model = "test-vision"

        async def extract(self, _image_bytes, _mime_type):
            return [
                OCRIndicatorDraft(
                    name="WBC",
                    value=7.2,
                    unit="10^9/L",
                    confidence=0.95,
                ),
                OCRIndicatorDraft(
                    name="AST",
                    value=48,
                    unit="U/L",
                    confidence=0.95,
                ),
            ]

    monkeypatch.setattr(
        ocr_routes,
        "_get_dependencies",
        lambda: (FakeProcessor(), FakeAdapter()),
    )
    monkeypatch.setattr(get_settings(), "ocr_upload_mode", "open_with_consent")
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("report.png", b"image", "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 200, response.text
    indicators = response.json()["indicators"]
    assert indicators[0]["supported"] is True
    assert indicators[1]["name"] == "AST"
    assert indicators[1]["supported"] is False
    assert "chưa được hỗ trợ" in indicators[1]["unsupported_reason"]


@pytest.mark.asyncio
async def test_low_confidence_cannot_bypass_explicit_acknowledgement(client):
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/ocr/confirm",
        json=_review_payload(acknowledged=False),
        headers=headers,
    )
    assert response.status_code == 400
    assert "độ tin cậy thấp" in response.json()["detail"]


@pytest.mark.asyncio
async def test_every_ocr_row_requires_manual_review(client):
    headers = await _auth_headers(client)
    response = await client.post(
        "/api/v1/ocr/confirm",
        json=_review_payload(acknowledged=True, reviewed=False),
        headers=headers,
    )
    assert response.status_code == 400
    assert "chưa được đối chiếu" in response.json()["detail"]


@pytest.mark.asyncio
async def test_confirmed_ocr_enters_graph_as_reviewed(client, monkeypatch):
    final_state = {
        "indicators": [
            {
                "name": "Fasting Blood Glucose",
                "value": 5.2,
                "unit": "mmol/L",
                "reference_low": 3.9,
                "reference_high": 5.6,
                "status": "normal",
                "is_abnormal": False,
                "is_critical": False,
                "explanation": "",
                "sources": [],
            }
        ],
        "critical_alerts": [],
        "has_critical_values": False,
        "guardrail_passed": True,
        "disclaimer": "Thông tin giáo dục, vui lòng trao đổi với bác sĩ.",
    }
    mock_ainvoke = AsyncMock(return_value=final_state)
    monkeypatch.setattr(routes.agent, "ainvoke", mock_ainvoke)
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/confirm",
        json=_review_payload(acknowledged=True),
        headers=headers,
    )

    assert response.status_code == 200, response.text
    initial_state = mock_ainvoke.await_args.args[0]
    assert initial_state["is_ocr_reviewed"] is True
    assert initial_state["ocr_drafts"][0].confidence == 0.4
    assert initial_state["raw_indicators"][0]["value"] == 5.2


@pytest.mark.asyncio
async def test_ocr_confirm_filters_unsupported_rows_and_reports_them(client, monkeypatch):
    drafts, token = prepare_review(
        [
            OCRIndicatorDraft(name="WBC", value=7.2, unit="10^9/L", confidence=0.95),
            OCRIndicatorDraft(name="AST", value=48, unit="U/L", confidence=0.95),
        ],
        username="benhnhan",
    )
    final_state = {
        "indicators": [
            {
                "name": "WBC",
                "value": 7.2,
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
        "critical_alerts": [],
        "has_critical_values": False,
        "guardrail_passed": True,
        "disclaimer": "Thông tin giáo dục, vui lòng trao đổi với bác sĩ.",
    }
    mock_ainvoke = AsyncMock(return_value=final_state)
    monkeypatch.setattr(routes.agent, "ainvoke", mock_ainvoke)
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/confirm",
        json={
            "review_token": token,
            "patient_age": 35,
            "patient_gender": "male",
            "test_date": "2026-08-07",
            "indicators": [
                {
                    "draft_id": drafts[0].draft_id,
                    "name": "WBC",
                    "value": 7.2,
                    "unit": "10^9/L",
                    "included": True,
                    "reviewed": True,
                    "low_confidence_acknowledged": False,
                },
                {
                    "draft_id": drafts[1].draft_id,
                    "name": "AST",
                    "value": 48,
                    "unit": "U/L",
                    "included": True,
                    "reviewed": True,
                    "low_confidence_acknowledged": False,
                },
            ],
        },
        headers=headers,
    )

    assert response.status_code == 200, response.text
    initial_state = mock_ainvoke.await_args.args[0]
    assert [item["name"] for item in initial_state["raw_indicators"]] == ["WBC"]
    assert response.json()["out_of_scope_indicators"] == ["AST"]
