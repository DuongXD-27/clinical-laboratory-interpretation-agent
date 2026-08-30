# Issue: Gemini OCR Schema Validation Failure

**Severity:** P0  
**Component:** `src/adapters/vision_adapter.py`  
**Observed in:** OCR evaluation runs on `png/` and `png_v2/` (2026-08-30)

---

## Mô tả

60% request gọi Gemini Vision (`gemini-3.5-flash-lite`) trả về response không khớp Pydantic schema `_GeminiOCRPayload`, khiến `VisionAdapter._extract_gemini()` raise `VisionAdapterError` và từ chối toàn bộ phiếu — không có fallback sang OpenRouter.

```
VisionAdapterError: Gemini OCR trả về dữ liệu không đúng schema.
```

Lỗi phát sinh tại [`vision_adapter.py:274`](../src/adapters/vision_adapter.py#L274):

```python
payload = _GeminiOCRPayload.model_validate_json(response.text or "")
```

---

## Bằng chứng

| Run | Bộ ảnh | Thành công | Thất bại | Success Rate |
|-----|--------|------------|----------|--------------|
| v1  | `png/`     | 8/20 | 12/20 | 40% |
| v2  | `png_v2/`  | 8/20 | 12/20 | 40% |

Tỉ lệ thất bại giống nhau trên cả hai bộ ảnh với bố cục khác nhau.  
Các file bị lỗi **không cố định** giữa hai lần chạy (phiếu 001–002 thành công ở lần 1, thất bại ở lần 2; ngược lại với phiếu 003–004) → lỗi **không phụ thuộc vào nội dung ảnh**, mà là vấn đề **API-level**.

---

## Phân tích nguyên nhân

### Nguyên nhân 1 (khả năng cao nhất) — Thinking tokens lẫn vào JSON output

Model được khởi tạo với `thinking_config=types.ThinkingConfig(thinking_level="low")`. Với một số prompt/ảnh, Gemini có thể emit thinking tokens trước JSON body, khiến `response.text` chứa text dạng:

```
<thinking>
Tôi cần đọc bảng xét nghiệm...
</thinking>
{"indicators": [...]}
```

`model_validate_json()` không parse được phần `<thinking>...` và raise `ValidationError`.

### Nguyên nhân 2 — Model trả `null` cho trường `value`

Khi OCR không đọc được giá trị số (ô trống, font không nhận diện được), model có thể trả:

```json
{"name": "WBC", "value": null, "unit": "10^9/L", "confidence": 0.4, "raw_text": "WBC  —"}
```

`_ProviderIndicator.value` được khai báo `float` không có `Optional` → Pydantic reject toàn bộ response.

### Nguyên nhân 3 — Rate limit / quota

Gemini API trả HTTP 429 hoặc 503 nhưng `_is_transient()` không nhận dạng được response body dạng JSON error, dẫn đến parse JSON thất bại thay vì trigger retry.

---

## Tác động

- **60% phiếu không được xử lý** — người dùng nhận lỗi thay vì kết quả OCR.
- OpenRouter fallback **không được kích hoạt** vì lỗi schema được classify là non-transient (`raise VisionAdapterError` không qua `fallback_enabled` branch).
- Mất dữ liệu không tường minh: không có log nào ghi lại `response.text` raw khi schema fail.

---

## Hướng khắc phục

### Fix ngắn hạn — Trigger fallback khi schema fail

Tại `vision_adapter.py:274–280`, thay vì raise ngay, thử fallback sang OpenRouter:

```python
# Hiện tại (không fallback):
try:
    payload = _GeminiOCRPayload.model_validate_json(response.text or "")
    ...
except (ValidationError, TypeError, ValueError) as exc:
    raise VisionAdapterError("Gemini OCR trả về dữ liệu không đúng schema.") from exc

# Đề xuất (có fallback):
try:
    payload = _GeminiOCRPayload.model_validate_json(response.text or "")
    ...
except (ValidationError, TypeError, ValueError) as exc:
    logger.warning(
        "vision_gemini_schema_fail attempt=%d response_preview=%r",
        attempt, (response.text or "")[:200],
    )
    if self.fallback_enabled and self.settings.openrouter_api_key.strip():
        return await self._extract_openrouter(image_bytes, mime_type)
    raise VisionAdapterError("Gemini OCR trả về dữ liệu không đúng schema.") from exc
```

### Fix trung hạn — Strip thinking tokens trước khi parse

```python
import re

def _strip_thinking(text: str) -> str:
    """Remove <thinking>...</thinking> blocks Gemini may prepend."""
    return re.sub(r"<thinking>.*?</thinking>", "", text, flags=re.DOTALL).strip()

# Dùng trước model_validate_json:
clean_text = _strip_thinking(response.text or "")
payload = _GeminiOCRPayload.model_validate_json(clean_text)
```

### Fix dài hạn — Cho phép `value` là `Optional[float]`

```python
class _ProviderIndicator(BaseModel):
    name: str = Field(..., min_length=1)
    value: float | None = Field(None, allow_inf_nan=False)  # None khi không đọc được
    unit: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)
    raw_text: str
```

Row có `value=None` sẽ được annotate `needs_review=True` và hiển thị cho user tự nhập thay vì bị drop.

---

## Các bước điều tra tiếp theo

1. **Bật DEBUG logging** — thêm `logger.debug("response_text=%r", response.text)` trước dòng `model_validate_json` để xem raw output của 12 request thất bại.
2. **Kiểm tra thinking config** — thử lại với `thinking_level="none"` để loại trừ Nguyên nhân 1.
3. **Kiểm tra quota** — so sánh timestamp của các request thất bại với Cloud Console logs để xem có liên quan đến rate limit không.

---

*Issue documented from evaluation runs — `data_mock/run_eval.py`. See `report.md` and `report_v2.md` for full metric context.*
