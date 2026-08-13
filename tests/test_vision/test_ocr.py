"""Unit tests for direct Gemini OCR, fallback policy, and image preprocessing."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

import src.adapters.vision_adapter as vision_module
from src.adapters.vision_adapter import (
    VisionAdapter,
    VisionAdapterError,
    _clamp_conf,
    _extract_json,
    image_to_data_url,
)
from src.services.image_processor import ImageProcessor, ImageProcessorError
from src.services.request_timing import (
    RequestTiming,
    reset_current_timing,
    set_current_timing,
)

VALID_JSON = (
    '{"indicators":[{"name":"Glucose","value":5.2,"unit":"mmol/L",'
    '"confidence":0.95,"raw_text":"Glucose 5.2 mmol/L"}]}'
)


class FakeGeminiResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeGeminiClient:
    def __init__(self, *outcomes: object) -> None:
        self.outcomes = list(outcomes or [FakeGeminiResponse(VALID_JSON)])
        self.calls: list[dict] = []
        self.aio = self
        self.models = self
        self.aclose = AsyncMock()

    async def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeOpenRouterResponse:
    def __init__(self, content: str = VALID_JSON) -> None:
        message = type("Message", (), {"content": content})()
        self.choices = [type("Choice", (), {"message": message})()]


class FakeOpenRouterClient:
    def __init__(self, content: str = VALID_JSON) -> None:
        self.content = content
        self.calls: list[dict] = []
        self.chat = self
        self.completions = self
        self.close = AsyncMock()

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return FakeOpenRouterResponse(self.content)


class ProviderError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code
        super().__init__(f"provider status {status_code}")


def test_image_to_data_url():
    url = image_to_data_url(b"\x00\x01\x02")
    assert url.startswith("data:image/jpeg;base64,")


def test_extract_json_compatibility_parser():
    payload = _extract_json(f"prefix\n```json\n{VALID_JSON}\n```\nsuffix")
    assert payload["indicators"][0]["name"] == "Glucose"


def test_extract_json_invalid_raises():
    with pytest.raises(Exception):
        _extract_json("no json here")


def test_clamp_conf_clamps_to_unit_interval():
    assert _clamp_conf(1.4) == 1.0
    assert _clamp_conf(-0.2) == 0.0
    assert _clamp_conf(None) == 0.5


@pytest.mark.asyncio
async def test_gemini_success_uses_inline_bytes_structured_schema_and_no_fallback():
    gemini = FakeGeminiClient(FakeGeminiResponse(VALID_JSON))
    fallback = FakeOpenRouterClient()
    adapter = VisionAdapter(
        gemini_client=gemini,
        openrouter_client=fallback,
    )

    drafts = await adapter.extract(b"private-image-marker", "image/jpeg")

    assert [(draft.name, draft.value) for draft in drafts] == [("Glucose", 5.2)]
    assert len(gemini.calls) == 1
    assert len(fallback.calls) == 0
    call = gemini.calls[0]
    assert call["model"] == "gemini-3.5-flash-lite"
    assert call["contents"][1].inline_data.data == b"private-image-marker"
    assert call["contents"][1].inline_data.mime_type == "image/jpeg"
    assert call["config"].temperature == 0
    assert call["config"].max_output_tokens <= 4096
    assert call["config"].response_mime_type == "application/json"
    assert "indicators" in call["config"].response_json_schema["properties"]
    assert adapter.last_provider == "gemini"


@pytest.mark.asyncio
async def test_gemini_validates_domain_schema_without_compatibility_parser(monkeypatch):
    parser = AsyncMock(side_effect=AssertionError("compat parser must not run"))
    monkeypatch.setattr(vision_module, "_extract_json", parser)
    invalid = '{"indicators":[{"name":"Glucose","value":"bad"}]}'
    gemini = FakeGeminiClient(FakeGeminiResponse(invalid))
    fallback = FakeOpenRouterClient()

    with pytest.raises(VisionAdapterError, match="schema"):
        await VisionAdapter(
            gemini_client=gemini,
            openrouter_client=fallback,
        ).extract(b"image")

    assert len(gemini.calls) == 1
    assert len(fallback.calls) == 0
    parser.assert_not_awaited()


@pytest.mark.asyncio
async def test_transient_error_retries_once_with_async_delay_then_succeeds():
    sleep = AsyncMock()
    gemini = FakeGeminiClient(
        ProviderError(429),
        FakeGeminiResponse(VALID_JSON),
    )
    adapter = VisionAdapter(
        gemini_client=gemini,
        sleep_func=sleep,
        jitter_func=lambda _start, _end: 0.0,
    )

    drafts = await adapter.extract(b"image")

    assert len(drafts) == 1
    assert len(gemini.calls) == 2
    sleep.assert_awaited_once_with(0.5)


@pytest.mark.asyncio
@pytest.mark.parametrize("status_code", [400, 401, 403])
async def test_non_retryable_client_errors_do_not_retry_or_fallback(status_code):
    gemini = FakeGeminiClient(ProviderError(status_code))
    fallback = FakeOpenRouterClient()
    with pytest.raises(VisionAdapterError):
        await VisionAdapter(
            gemini_client=gemini,
            openrouter_client=fallback,
        ).extract(b"image")
    assert len(gemini.calls) == 1
    assert len(fallback.calls) == 0


@pytest.mark.asyncio
async def test_two_transient_failures_trigger_exactly_one_openrouter_fallback(monkeypatch):
    monkeypatch.setattr(
        vision_module.get_settings(),
        "openrouter_api_key",
        "configured-for-test",
    )
    gemini = FakeGeminiClient(TimeoutError(), ProviderError(500))
    fallback = FakeOpenRouterClient()
    adapter = VisionAdapter(
        gemini_client=gemini,
        openrouter_client=fallback,
        sleep_func=AsyncMock(),
        jitter_func=lambda _start, _end: 0.0,
    )

    drafts = await adapter.extract(b"image")

    assert len(drafts) == 1
    assert len(gemini.calls) == 2
    assert len(fallback.calls) == 1
    assert adapter.last_provider == "openrouter"


def test_gemini_client_singleton_is_created_once(monkeypatch):
    fake = FakeGeminiClient()
    factory_calls = 0

    def factory(_settings):
        nonlocal factory_calls
        factory_calls += 1
        return fake

    monkeypatch.setattr(vision_module, "_shared_gemini_client", None)
    monkeypatch.setattr(vision_module, "_create_gemini_client", factory)

    first = VisionAdapter()
    second = VisionAdapter()

    assert first._gemini_client is second._gemini_client
    assert factory_calls == 1


def test_gemini_sdk_retry_is_disabled(monkeypatch):
    captured = {}

    def fake_client(**kwargs):
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(vision_module.genai, "Client", fake_client)
    vision_module._create_gemini_client(vision_module.get_settings())

    assert captured["http_options"].retry_options.attempts == 1


@pytest.mark.asyncio
async def test_retry_never_uses_blocking_sleep(monkeypatch):
    def forbidden_sleep(_seconds):
        raise AssertionError("blocking sleep called")

    monkeypatch.setattr(vision_module.time, "sleep", forbidden_sleep, raising=False)
    async_sleep = AsyncMock()
    gemini = FakeGeminiClient(ProviderError(408), FakeGeminiResponse(VALID_JSON))
    await VisionAdapter(
        gemini_client=gemini,
        sleep_func=async_sleep,
        jitter_func=lambda _start, _end: 0.0,
    ).extract(b"image")
    async_sleep.assert_awaited_once()


@pytest.mark.asyncio
async def test_trace_contains_operational_fields_but_no_private_payload(caplog):
    secret = "secret-api-key-marker"
    image_marker = b"private-image-marker"
    value_marker = "987654.321"
    content = VALID_JSON.replace("5.2", value_marker)
    timing = RequestTiming(request_id="vision-timing-test")
    token = set_current_timing(timing)
    try:
        with caplog.at_level(logging.INFO):
            await VisionAdapter(
                gemini_client=FakeGeminiClient(FakeGeminiResponse(content)),
                model="gemini-test",
            ).extract(image_marker)
    finally:
        reset_current_timing(token)

    attempts = [event for event in timing.events if event.name == "vision-provider-attempt"]
    assert len(attempts) == 1
    assert attempts[0].attributes == {
        "provider": "gemini",
        "model": "gemini-test",
        "attempt": 1,
        "outcome": "response",
        "sdk_retries": 0,
    }
    combined = caplog.text
    assert "provider=gemini" in combined
    assert "outcome=response" in combined
    assert secret not in combined
    assert image_marker.decode() not in combined
    assert value_marker not in combined
    assert vision_module.EXTRACTION_USER_PROMPT not in combined


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
    with pytest.raises(ImageProcessorError):
        ImageProcessor().process(b"", filename="x.png")


def test_image_processor_rejects_non_image():
    with pytest.raises(ImageProcessorError):
        ImageProcessor().process(b"not an image", filename="x.txt")


def test_image_processor_deskew_survives_opencv5_shape():
    from io import BytesIO

    from PIL import Image, ImageDraw

    image = Image.new("RGB", (800, 600), (255, 255, 255))
    draw = ImageDraw.Draw(image)
    for y in range(50, 600, 60):
        draw.line([(20, y), (780, y)], fill=(0, 0, 0), width=3)
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    output = ImageProcessor().process(buffer.getvalue(), filename="lines.png")
    assert output.mime_type == "image/jpeg"
    assert output.bytes
