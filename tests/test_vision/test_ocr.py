"""Unit tests cho Adapter_Vision + ImageProcessor + endpoint OCR (ADR-006).

Không gọi API thật — VisionAdapter được inject client mock; endpoint OCR
được thay dependency bằng mock qua monkeypatch.
"""

import pytest

from src.adapters.vision_adapter import (
    VisionAdapter,
    VisionAdapterError,
    _clamp_conf,
    _extract_json,
    image_to_data_url,
)
from src.services.image_processor import ImageProcessor, ImageProcessorError

# ---------- Utils ----------

def test_image_to_data_url():
    url = image_to_data_url(b"\x00\x01\x02")
    assert url.startswith("data:image/jpeg;base64,")


def test_extract_json_from_markdown_fence():
    content = (
        "```json\n"
        '{"indicators": [{"name": "Glucose", "value": 5.2, "unit": "mmol/L", '
        '"confidence": 0.95}]}\n'
        "```"
    )
    payload = _extract_json(content)
    assert payload["indicators"][0]["name"] == "Glucose"


def test_extract_json_from_embedded_block():
    content = "Đây là kết quả:\n```json\n{\"items\": [{\"name\": \"Kali\"}]}\n```"
    payload = _extract_json(content)
    assert payload["items"][0]["name"] == "Kali"


def test_extract_json_invalid_raises():
    with pytest.raises(Exception):
        _extract_json("no json here at all")


def test_clamp_conf_clamps_to_unit_interval():
    assert _clamp_conf(1.4) == 1.0
    assert _clamp_conf(-0.2) == 0.0
    assert _clamp_conf(None) == 0.5
    assert _clamp_conf("oops") == 0.5
    assert _clamp_conf(0.33) == pytest.approx(0.33)


# ---------- VisionAdapter ----------


class FakeResponse:
    def __init__(self, content: str):
        self.choices = [FakeChoice(content)]


class FakeChoice:
    def __init__(self, content: str):
        self.message = FakeMessage(content)


class FakeMessage:
    def __init__(self, content: str):
        self.content = content


class FakeClient:
    """Mô phỏng client OpenAI với chuỗi chat.completions.create."""

    def __init__(self, content: str = ""):
        self._content = content
        self.last_kwargs = None

    @property
    def chat(self):
        return self

    @property
    def completions(self):
        return self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if isinstance(self._content, Exception):
            raise self._content
        return FakeResponse(self._content)


def test_extract_parses_drafts_and_maps_model():
    content = (
        '{"indicators": [{"name": "Glucose", "value": 5.2, "unit": "mmol/L", '
        '"confidence": 0.95, "raw_text": "Glucose  5.2  mmol/L"}, '
        '{"name": "Kali", "value": 7.2, "unit": "mmol/L", "confidence": 0.8, '
        '"raw_text": "Kali  7.2"}]}'
    )
    client = FakeClient(content=content)
    adapter = VisionAdapter(client=client, model="test-vlm")
    drafts = adapter.extract(image_to_data_url(b"abc"))
    assert len(drafts) == 2
    assert drafts[0].name == "Glucose"
    assert drafts[0].value == 5.2
    assert drafts[0].confidence == pytest.approx(0.95)
    assert client.last_kwargs["model"] == "test-vlm"


def test_extract_empty_content_raises():
    client = FakeClient(content="")
    adapter = VisionAdapter(client=client)
    with pytest.raises(VisionAdapterError):
        adapter.extract(image_to_data_url(b"abc"))


def test_extract_skips_bad_items():
    content = (
        '{"indicators": ['
        '{"name": "Glucose", "value": "not-a-number", "unit": "mmol/L"}, '
        '{"name": "Kali", "value": 7.2, "unit": "mmol/L", "confidence": 0.9, "raw_text": "Kali 7.2"}]}'
    )
    client = FakeClient(content=content)
    adapter = VisionAdapter(client=client)
    drafts = adapter.extract(image_to_data_url(b"abc"))
    assert len(drafts) == 1
    assert drafts[0].name == "Kali"


def test_extract_worker_on_api_error():
    client = FakeClient(content=RuntimeError("rate limited"))
    adapter = VisionAdapter(client=client)
    with pytest.raises(VisionAdapterError):
        adapter.extract(image_to_data_url(b"abc"))


# ---------- ImageProcessor ----------


def _make_png_bytes() -> bytes:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (100, 80), (255, 255, 255)).save(buf, format="PNG")
    return buf.getvalue()


def test_image_processor_validates_and_converts_to_jpeg():
    processor = ImageProcessor()
    out = processor.process(_make_png_bytes(), filename="x.png")
    assert out.mime_type == "image/jpeg"
    assert out.width == 100
    assert out.height == 80
    assert out.bytes


def test_image_processor_rejects_empty():
    processor = ImageProcessor()
    with pytest.raises(ImageProcessorError):
        processor.process(b"", filename="x.png")


def test_image_processor_rejects_non_image():
    processor = ImageProcessor()
    with pytest.raises(ImageProcessorError):
        processor.process(b"this is not an image", filename="x.txt")


def test_image_processor_deskew_survives_opencv5_shape():
    """Hồi quy: OpenCV 5.0 trả (N,4) thay vì (N,1,4) từ HoughLinesP."""
    from PIL import Image, ImageDraw

    # Ảnh thẳng có đường kẻ ngang để HoughLinesP ra kết quả thật.
    img = Image.new("RGB", (800, 600), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    for y in range(50, 600, 60):
        draw.line([(20, y), (780, y)], fill=(0, 0, 0), width=3)
    from io import BytesIO

    buf = BytesIO()
    img.save(buf, format="PNG")
    processor = ImageProcessor()
    out = processor.process(buf.getvalue(), filename="lines.png")
    assert out.mime_type == "image/jpeg"
    assert out.bytes
