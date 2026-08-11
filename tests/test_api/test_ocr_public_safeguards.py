"""4 lớp bảo vệ cho bản OCR công khai (V3).

Trọng tâm của bộ test này: chứng minh các lớp bảo vệ nằm ở BACKEND, không phải
chỉ ở giao diện. Mọi test dưới đây gọi thẳng API, bỏ qua hoàn toàn UI — đúng
cách một người dùng có ý đồ xấu sẽ làm.
"""

from pathlib import Path

import pytest

from src.api import ocr_routes
from src.config import get_settings
from src.services.ocr_sample_library import load_samples

SAMPLE_DIR = Path("data/ocr_samples")


async def _auth_headers(client):
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture
def set_mode(monkeypatch):
    """Đổi OCR_UPLOAD_MODE cho một test rồi tự trả lại."""

    def _apply(mode: str):
        settings = get_settings()
        monkeypatch.setattr(settings, "ocr_upload_mode", mode)
        return settings

    return _apply


def _sample_bytes() -> bytes:
    samples = load_samples()
    assert samples, "Thiếu bộ ảnh mẫu trong data/ocr_samples"
    return samples[0].path.read_bytes()


# --- Lớp 1: feature flag ------------------------------------------------


@pytest.mark.asyncio
async def test_internal_only_mode_disables_upload(client, set_mode):
    set_mode("internal_only")
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("x.png", _sample_bytes(), "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 503


# --- Lớp 2: consent bắt buộc, chặn ở server -----------------------------


@pytest.mark.asyncio
async def test_upload_rejected_without_consent(client, set_mode):
    """Bỏ qua checkbox ở UI bằng cách gọi thẳng API vẫn phải bị chặn."""
    set_mode("open_with_consent")
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("x.png", _sample_bytes(), "image/png")},
        # cố tình không gửi consent_acknowledged
    )

    assert response.status_code == 400
    assert "mô phỏng" in response.json()["detail"]


@pytest.mark.asyncio
async def test_consent_false_is_rejected(client, set_mode):
    set_mode("open_with_consent")
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("x.png", _sample_bytes(), "image/png")},
        data={"consent_acknowledged": "false"},
    )

    assert response.status_code == 400


# --- Lớp 3: demo_only chỉ nhận ảnh mẫu ----------------------------------


@pytest.mark.asyncio
async def test_demo_only_rejects_arbitrary_image(client, set_mode):
    """Ảnh người dùng tự tải lên bị chặn kể cả khi đã tick consent."""
    set_mode("demo_only")
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("real_report.png", b"anh-that-cua-benh-nhan", "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 403
    assert "ảnh phiếu mẫu" in response.json()["detail"]


@pytest.mark.asyncio
async def test_demo_only_still_requires_consent(client, set_mode):
    """Ảnh mẫu hợp lệ nhưng thiếu consent -> vẫn chặn (2 lớp độc lập)."""
    set_mode("demo_only")
    headers = await _auth_headers(client)

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("normal.png", _sample_bytes(), "image/png")},
    )

    assert response.status_code == 400


# --- Lớp 4: không lưu ảnh gốc -------------------------------------------


@pytest.mark.asyncio
async def test_uploaded_image_is_never_written_to_disk(client, set_mode, monkeypatch, tmp_path):
    """Chặn hồi quy: nếu ai đó thêm code ghi ảnh ra đĩa, test này phải đỏ.

    Chặn thẳng `Path.write_bytes`/`open(..., 'wb')` trong lúc xử lý upload —
    bất kỳ thao tác ghi file nhị phân nào cũng làm test nổ.
    """
    set_mode("demo_only")
    headers = await _auth_headers(client)

    written: list[str] = []
    real_open = open

    def _guard_open(file, mode="r", *args, **kwargs):
        if "w" in str(mode) or "a" in str(mode):
            written.append(f"{file}:{mode}")
        return real_open(file, mode, *args, **kwargs)

    def _guard_write_bytes(self, data):
        written.append(str(self))
        return len(data)

    monkeypatch.setattr("builtins.open", _guard_open)
    monkeypatch.setattr(Path, "write_bytes", _guard_write_bytes)

    class _StubAdapter:
        model = "stub-vision"

        async def extract(self, _image_bytes, _mime_type):
            from src.models.ocr_schemas import OCRIndicatorDraft

            return [
                OCRIndicatorDraft(
                    name="Glucose", value=5.2, unit="mmol/L", confidence=0.95, raw_text="Glucose 5.2"
                )
            ]

    from src.services.image_processor import ImageProcessor

    monkeypatch.setattr(ocr_routes, "_get_dependencies", lambda: (ImageProcessor(), _StubAdapter()))

    response = await client.post(
        "/api/v1/ocr/upload",
        headers=headers,
        files={"file": ("normal.png", _sample_bytes(), "image/png")},
        data={"consent_acknowledged": "true"},
    )

    assert response.status_code == 200, response.text
    assert written == [], f"Ảnh bị ghi ra đĩa: {written}"


# --- Endpoint chính sách + ảnh mẫu --------------------------------------


@pytest.mark.asyncio
async def test_policy_endpoint_reports_current_mode(client, set_mode):
    set_mode("demo_only")

    response = await client.get("/api/v1/ocr/policy")

    assert response.status_code == 200
    body = response.json()
    assert body["mode"] == "demo_only"
    assert body["upload_enabled"] is True
    assert body["custom_image_allowed"] is False
    assert body["consent_required"] is True
    assert len(body["samples"]) == 4


@pytest.mark.asyncio
async def test_sample_image_can_be_downloaded(client):
    response = await client.get("/api/v1/ocr/samples/normal")

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"


@pytest.mark.asyncio
async def test_unknown_sample_returns_404(client):
    response = await client.get("/api/v1/ocr/samples/khong-ton-tai")

    assert response.status_code == 404
