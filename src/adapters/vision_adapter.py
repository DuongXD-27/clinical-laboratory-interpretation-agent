"""Async Vision adapter: direct Gemini first, OpenRouter as a narrow fallback.

Images stay in memory and are sent inline.  The adapter never uses Gemini's
Files API and never logs prompts, image bytes, extracted values, or secrets.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import random
import re
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal

import aiohttp
import httpx
from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from openai import AsyncOpenAI
from pydantic import BaseModel, Field, ValidationError

from src.config import Settings, get_settings
from src.models.ocr_schemas import OCRIndicatorDraft
from src.services.request_timing import add_timing_event, timing_span

logger = logging.getLogger(__name__)

EXTRACTION_SYSTEM_PROMPT = (
    "Bạn là công cụ trích xuất dữ liệu từ ảnh phiếu xét nghiệm máu. "
    "Chỉ đọc các dòng chỉ số gồm tên, giá trị, đơn vị, độ tin cậy và nguyên văn. "
    "Không giải thích, bình luận y khoa hoặc chẩn đoán. "
    "Nếu ảnh không phải phiếu xét nghiệm máu, trả về danh sách indicators rỗng."
)
EXTRACTION_USER_PROMPT = "Đọc các chỉ số xét nghiệm trên ảnh theo schema đã cung cấp."


class VisionAdapterError(Exception):
    """Provider call or response validation failed."""


class _ProviderIndicator(BaseModel):
    """Strict provider boundary matching the existing OCR domain fields."""

    name: str = Field(..., min_length=1)
    value: float = Field(..., allow_inf_nan=False)
    unit: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_text: str


class _GeminiOCRPayload(BaseModel):
    indicators: list[_ProviderIndicator]


_shared_gemini_client: Any | None = None
_shared_openrouter_client: AsyncOpenAI | None = None
_client_lock = threading.Lock()


def _create_gemini_client(settings: Settings) -> Any:
    """Create one process-wide client with all SDK retries disabled."""

    return genai.Client(
        api_key=settings.google_api_key,
        http_options=types.HttpOptions(
            timeout=int(settings.gemini_vision_timeout_seconds * 1000),
            # attempts includes the original request; one means no SDK retry.
            retry_options=types.HttpRetryOptions(attempts=1),
        ),
    )


def _get_gemini_client(settings: Settings) -> tuple[Any, bool]:
    global _shared_gemini_client
    with _client_lock:
        if _shared_gemini_client is None:
            _shared_gemini_client = _create_gemini_client(settings)
            return _shared_gemini_client, True
        return _shared_gemini_client, False


def _create_openrouter_client(settings: Settings) -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.openrouter_api_key,
        base_url=settings.vision_base_url,
        timeout=settings.vision_timeout_seconds,
        max_retries=0,
    )


def _get_openrouter_client(settings: Settings) -> tuple[AsyncOpenAI, bool]:
    global _shared_openrouter_client
    with _client_lock:
        if _shared_openrouter_client is None:
            _shared_openrouter_client = _create_openrouter_client(settings)
            return _shared_openrouter_client, True
        return _shared_openrouter_client, False


async def close_vision_clients() -> None:
    """Close shared HTTP transports during application shutdown."""

    global _shared_gemini_client, _shared_openrouter_client
    with _client_lock:
        gemini_client = _shared_gemini_client
        openrouter_client = _shared_openrouter_client
        _shared_gemini_client = None
        _shared_openrouter_client = None

    if gemini_client is not None:
        await gemini_client.aio.aclose()
    if openrouter_client is not None:
        await openrouter_client.close()


def image_to_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Encode only for the OpenRouter compatibility fallback."""

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _status_code(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code
    response = getattr(exc, "response", None)
    response_code = getattr(response, "status_code", None)
    return response_code if isinstance(response_code, int) else None


def _is_transient(exc: BaseException) -> bool:
    code = _status_code(exc)
    if code is not None:
        return code in {408, 429} or 500 <= code <= 599
    return isinstance(
        exc,
        (
            asyncio.TimeoutError,
            TimeoutError,
            httpx.TimeoutException,
            httpx.TransportError,
            aiohttp.ClientError,
            genai_errors.ServerError,
        ),
    )


class VisionAdapter:
    """Extract OCR drafts with direct Gemini and an optional sequential fallback."""

    def __init__(
        self,
        *,
        gemini_client: Any | None = None,
        openrouter_client: AsyncOpenAI | Any | None = None,
        primary_provider: Literal["gemini", "openrouter"] = "gemini",
        model: str | None = None,
        fallback_enabled: bool = True,
        sleep_func: Callable[[float], Awaitable[None]] = asyncio.sleep,
        jitter_func: Callable[[float, float], float] = random.uniform,
    ) -> None:
        self.settings = get_settings()
        self.primary_provider = primary_provider
        self.fallback_enabled = fallback_enabled
        self._sleep = sleep_func
        self._jitter = jitter_func
        self._openrouter_client = openrouter_client

        if primary_provider == "gemini":
            if gemini_client is None:
                self._gemini_client, created = _get_gemini_client(self.settings)
            else:
                self._gemini_client, created = gemini_client, False
            self.model = model or self.settings.gemini_vision_model
            logger.info(
                "vision_client provider=gemini reused=%s",
                str(not created).lower(),
            )
            add_timing_event(
                "vision-client",
                0.0,
                provider="gemini",
                outcome="created" if created else "reused",
            )
        else:
            self._gemini_client = gemini_client
            self.model = model or self.settings.vision_model

        self.last_provider = primary_provider
        self.last_model = self.model

    async def extract(
        self,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> list[OCRIndicatorDraft]:
        """Measure and execute the provider operation without blocking the event loop."""

        with timing_span("vision-total"):
            if self.primary_provider == "openrouter":
                return await self._extract_openrouter(image_bytes, mime_type)
            return await self._extract_gemini(image_bytes, mime_type)

    async def _extract_gemini(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> list[OCRIndicatorDraft]:
        config = types.GenerateContentConfig(
            system_instruction=EXTRACTION_SYSTEM_PROMPT,
            temperature=0,
            max_output_tokens=self.settings.gemini_vision_max_output_tokens,
            response_mime_type="application/json",
            response_json_schema=_GeminiOCRPayload.model_json_schema(),
            thinking_config=types.ThinkingConfig(
                thinking_level=self.settings.gemini_vision_thinking_level
            ),
        )
        contents = [
            EXTRACTION_USER_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type=mime_type),
        ]

        last_transient: BaseException | None = None
        for attempt in range(1, 3):
            started_at = time.perf_counter()
            try:
                response = await asyncio.wait_for(
                    self._gemini_client.aio.models.generate_content(
                        model=self.model,
                        contents=contents,
                        config=config,
                    ),
                    timeout=self.settings.gemini_vision_timeout_seconds,
                )
            except Exception as exc:
                transient = _is_transient(exc)
                duration_ms = (time.perf_counter() - started_at) * 1000
                self._record_attempt("gemini", self.model, attempt, "transient_error" if transient else "error", duration_ms)
                if not transient:
                    raise VisionAdapterError(
                        f"Gemini OCR bị từ chối hoặc lỗi cấu hình (HTTP {_status_code(exc) or 'unknown'})."
                    ) from exc
                last_transient = exc
                if attempt == 1:
                    delay = 0.5 + self._jitter(0.0, 0.25)
                    backoff_started_at = time.perf_counter()
                    await self._sleep(delay)
                    add_timing_event(
                        "vision-backoff",
                        (time.perf_counter() - backoff_started_at) * 1000,
                        provider="gemini",
                        after_attempt=attempt,
                    )
                    continue
                break

            duration_ms = (time.perf_counter() - started_at) * 1000
            self._record_attempt("gemini", self.model, attempt, "response", duration_ms)
            try:
                with timing_span("vision-parse"):
                    payload = _GeminiOCRPayload.model_validate_json(response.text or "")
                    drafts = [
                        OCRIndicatorDraft(**item.model_dump())
                        for item in payload.indicators
                    ]
            except (ValidationError, TypeError, ValueError) as exc:
                # A syntactically/semantically bad response is not a transport
                # failure: do not retry it and do not silently switch providers.
                raise VisionAdapterError("Gemini OCR trả về dữ liệu không đúng schema.") from exc
            self.last_provider = "gemini"
            self.last_model = self.model
            return drafts

        if self.fallback_enabled and self.settings.openrouter_api_key.strip():
            logger.warning(
                "vision_fallback from_provider=gemini to_provider=openrouter reason=transient_exhausted"
            )
            fallback_started_at = time.perf_counter()
            drafts = await self._extract_openrouter(image_bytes, mime_type)
            add_timing_event(
                "vision-fallback",
                (time.perf_counter() - fallback_started_at) * 1000,
                from_provider="gemini",
                to_provider="openrouter",
                outcome="success",
            )
            return drafts

        raise VisionAdapterError(
            "Gemini OCR tạm thời không khả dụng sau 2 lần gọi; fallback không được cấu hình."
        ) from last_transient

    async def _extract_openrouter(
        self,
        image_bytes: bytes,
        mime_type: str,
    ) -> list[OCRIndicatorDraft]:
        if self._openrouter_client is None:
            if not self.settings.openrouter_api_key.strip():
                raise VisionAdapterError("OpenRouter OCR chưa được cấu hình.")
            self._openrouter_client, created = _get_openrouter_client(self.settings)
            logger.info(
                "vision_client provider=openrouter reused=%s",
                str(not created).lower(),
            )

        with timing_span("openrouter-base64"):
            image_data_url = image_to_data_url(image_bytes, mime_type)
        messages = [
            {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": EXTRACTION_USER_PROMPT},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            },
        ]
        model = self.settings.vision_model if self.primary_provider == "gemini" else self.model
        started_at = time.perf_counter()
        try:
            response = await self._openrouter_client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0,
                max_tokens=self.settings.gemini_vision_max_output_tokens,
            )
        except Exception as exc:
            self._record_attempt(
                "openrouter",
                model,
                1,
                "error",
                (time.perf_counter() - started_at) * 1000,
            )
            raise VisionAdapterError("OpenRouter OCR fallback không khả dụng.") from exc

        content = response.choices[0].message.content if response.choices else ""
        self._record_attempt(
            "openrouter",
            model,
            1,
            "response" if content else "empty",
            (time.perf_counter() - started_at) * 1000,
        )
        if not content:
            raise VisionAdapterError("OpenRouter OCR trả về nội dung rỗng.")
        try:
            with timing_span("vision-parse"):
                drafts = self._parse_openrouter_response(content)
        except (ValidationError, TypeError, ValueError, _NotParsableError) as exc:
            raise VisionAdapterError("OpenRouter OCR trả về dữ liệu không đúng schema.") from exc
        self.last_provider = "openrouter"
        self.last_model = model
        return drafts

    @staticmethod
    def _record_attempt(
        provider: str,
        model: str,
        attempt: int,
        outcome: str,
        duration_ms: float,
    ) -> None:
        add_timing_event(
            "vision-provider-attempt",
            duration_ms,
            provider=provider,
            model=model,
            attempt=attempt,
            outcome=outcome,
            sdk_retries=0,
        )
        logger.info(
            "vision_provider provider=%s model=%s attempt=%d outcome=%s duration_ms=%.3f",
            provider,
            model,
            attempt,
            outcome,
            duration_ms,
        )

    @staticmethod
    def _parse_openrouter_response(content: str) -> list[OCRIndicatorDraft]:
        payload = _extract_json(content)
        if not isinstance(payload, dict):
            raise ValueError("response root must be an object")
        items = payload.get("indicators") or payload.get("items") or []
        if not isinstance(items, list):
            raise ValueError("indicators must be a list")
        return [OCRIndicatorDraft(**item) for item in items]


_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json(content: str) -> Any:
    """Compatibility parser used only by the OpenRouter fallback."""

    text = (content or "").strip()
    if not text:
        raise _NotParsableError(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for block in _FENCE_RE.findall(text):
        try:
            return json.loads(block.strip())
        except json.JSONDecodeError:
            continue
    decoder = json.JSONDecoder()
    for match in re.finditer(r"[{\[]", text):
        try:
            payload, _ = decoder.raw_decode(text, match.start())
            return payload
        except json.JSONDecodeError:
            continue
    raise _NotParsableError(text[:200])


class _NotParsableError(Exception):
    pass


def _clamp_conf(value: Any) -> float:
    """Retained for callers of the former compatibility helper."""

    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, conf))
