"""Adapter_Vision — Vision LLM Adapter (ADR-006).

Nhận ảnh phiếu xét nghiệm (dạng base64 data-URI), gọi VLM qua OpenRouter
(OpenAI-compatible API) để trích xuất danh sách chỉ số, parse thành
`OCRIndicatorDraft` (bản nháp). Bản nháp này KHÔNG được đưa thẳng vào
`AgentState` — luồng chính phải đi qua UI_Review (xem kickoff V2 mục 4.1).
"""

from __future__ import annotations

import base64
import json
import logging
import re
import time

from openai import OpenAI

from src.config import get_settings
from src.models.ocr_schemas import OCRIndicatorDraft

logger = logging.getLogger(__name__)

# Prompt buộc VLM trả về JSON — khớp schema OCRIndicatorDraft. Giữ prompt
# không chứa khuyến nghị y khoa (guardrail, ADR-004).
EXTRACTION_SYSTEM_PROMPT = (
    "Bạn là công cụ trích xuất dữ liệu từ ảnh phiếu xét nghiệm máu. "
    "Nhiệm vụ DUY NHẤT của bạn: đọc các dòng chỉ số (tên, giá trị, đơn vị) "
    "trên ảnh và trả về strict JSON. "
    "TUYỆT ĐỐI không giải thích, không bình luận y khoa, không chẩn đoán, "
    "không thêm chữ ngoài JSON. "
    "Trả về đúng cấu trúc: "
    '{"indicators": [{"name": "...", "value": 0.0, "unit": "...", '
    '"confidence": 0.0, "raw_text": "..."}]} '
    "Trong đó: name là tên viết tắt/viết đầy đủ của chỉ số; value là số đọc "
    "được (float); unit là đơn vị; confidence là số 0-1 thể hiện mức bạn tin "
    "giá trị đó đọc đúng; raw_text là chuỗi ký tự thô đúng như trên ảnh. "
    "Những con số Không đọc chắc chắn → confidence thấp (vd 0.3). "
    "Nếu ảnh không phải phiếu xét nghiệm máu, trả về {\"items\": []}."
)


class VisionAdapterError(Exception):
    """Lỗi khi gọi VLM hoặc parse kết quả OCR."""


def image_to_data_url(image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
    """Chuyển ảnh nhị phân thành base64 data-URI để gửi cho VLM."""
    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


class VisionAdapter:
    """Adapter gọi OpenRouter VLM để OCR phiếu xét nghiệm.

    Dependencies được inject (client/model) để dễ test mà không gọi API thật.
    """

    def __init__(
        self,
        *,
        client: OpenAI | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 2.0,
    ) -> None:
        settings = get_settings()
        if client is None:
            self._client = OpenAI(
                api_key=settings.openrouter_api_key,
                base_url=settings.vision_base_url,
                timeout=settings.vision_timeout_seconds,
            )
            self.timeout_seconds = settings.vision_timeout_seconds
        else:
            # Client inject (test): không phụ thuộc thuộc tính lỏng lẻo của mock;
            # lấy timeout hợp lệ hoặc rơi về cấu hình mặc định.
            self._client = client
            injected_timeout = getattr(client, "timeout", None)
            self.timeout_seconds = (
                injected_timeout
                if isinstance(injected_timeout, (int, float))
                else settings.vision_timeout_seconds
            )
        self.model = model or settings.vision_model
        self.temperature = temperature if temperature is not None else settings.vision_temperature
        self.max_retries = max_retries
        self.retry_backoff_seconds = retry_backoff_seconds

    def extract(self, image_data_url: str) -> list[OCRIndicatorDraft]:
        """Gọi VLM với ảnh (data URL) và parse kết quả thành bản nháp chỉ số.

        Returns:
            list[OCRIndicatorDraft]: danh sách chỉ số đọc được (có thể rỗng).
        Raises:
            VisionAdapterError: nếu gọi API lỗi hoặc JSON trả về không parse được.
        """
        messages = [
            {
                "role": "system",
                "content": EXTRACTION_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "Đọc các chỉ số xét nghiệm trên ảnh và trả JSON như hướng dẫn.",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": image_data_url},
                    },
                ],
            },
        ]

        # Ngân sách thời gian tổng cho toàn bộ vòng retry (network lỗi + rỗng
        # cộng dồn), tránh việc hai loại retry nối tiếp nhau vượt timeout kỳ
        # vọng của caller.
        deadline = time.monotonic() + self.max_retries * self.timeout_seconds + (
            self.max_retries * self.retry_backoff_seconds
        )

        for attempt in range(self.max_retries):
            if time.monotonic() > deadline:
                raise VisionAdapterError(
                    f"Vision LLM ({self.model}) vượt quá thời gian chờ tổng sau {attempt} lần thử."
                )
            try:
                resp = self._client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=self.temperature,
                    max_tokens=1000,
                )
            except Exception as exc:  # network / auth / rate-limit
                logger.warning(
                    "Lỗi gọi OpenRouter VLM (%s) lần %d/%d: %s",
                    self.model,
                    attempt + 1,
                    self.max_retries,
                    exc,
                )
                if attempt + 1 < self.max_retries:
                    time.sleep(self.retry_backoff_seconds)
                    continue
                raise VisionAdapterError(
                    f"Không gọi được Vision LLM ({self.model}): {exc}"
                ) from exc

            content = resp.choices[0].message.content if resp.choices else ""
            if content:
                return self._parse_response(content)

            # Content rỗng — free-tier thường rate-limit; thử lại vài lần.
            logger.warning(
                "Vision LLM (%s) trả về rỗng lần %d/%d",
                self.model,
                attempt + 1,
                self.max_retries,
            )
            time.sleep(self.retry_backoff_seconds)

        raise VisionAdapterError(
            f"Vision LLM ({self.model}) trả về rỗng sau {self.max_retries} lần thử."
        )

    def _parse_response(self, content: str) -> list[OCRIndicatorDraft]:
        """Tách JSON từ text reply (VLM hay kèm markdown/khai báo) rồi parse."""
        payload = _extract_json(content)
        if isinstance(payload, dict):
            items = payload.get("indicators") or payload.get("items") or []
        else:
            items = []
        drafts: list[OCRIndicatorDraft] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name", "")).strip()

            value = item.get("value")
            if name and value is not None:
                try:
                    drafts.append(
                        OCRIndicatorDraft(
                            name=name,
                            value=float(value),
                            unit=str(item.get("unit", "")).strip(),
                            confidence=_clamp_conf(item.get("confidence")),
                            raw_text=str(item.get("raw_text", "")).strip(),
                        )
                    )
                except (TypeError, ValueError) as exc:
                    logger.warning("Bỏ qua chỉ số không parse được: %r (%s)", item, exc)
        return drafts


# Khớp mọi markdown code fence (```json ... ``` hoặc ``` ... ```), kể cả khi
# VLM trả về nhiều khối hoặc kèm chữ thừa trước/sau.
_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json(content: str):
    """Trích khối JSON hợp lệ đầu tiên từ content của VLM.

    Chiến lược, theo thứ tự ưu tiên:
    1. Parse trực tiếp toàn bộ text.
    2. Parse nội dung bên trong từng fence ``` ... ``` (có thể nhiều khối).
    3. Dùng JSONDecoder.raw_decode quét từ mỗi vị trí '{' để tìm khối JSON
       hợp lệ đầu tiên (bền hơn find/rfind vì không giả định JSON là khối
       liên tục cuối cùng trong text).
    """
    text = (content or "").strip()
    if not text:
        raise _NotParsableError(text[:200])

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for block in _FENCE_RE.findall(text):
        block = block.strip()
        if not block:
            continue
        try:
            return json.loads(block)
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
    def __init__(self, snippet: str) -> None:
        super().__init__(f"Không phân tích được JSON từ phản hồi VLM: {snippet!r}...")


def _clamp_conf(value) -> float:
    """Chuẩn hoá confidence về [0,1]; giá trị thiếu/không hợp lệ -> 0.5."""
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return 0.5
    return max(0.0, min(1.0, conf))
