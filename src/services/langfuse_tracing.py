"""Trace LLM sang Langfuse — chạy song song với structured log, không thay thế.

Hai lớp quan sát giải quyết hai câu hỏi khác nhau và không thay nhau được:

- `request_timing` + `logging_config` trả lời "request nào chậm, hỏng ở đâu",
  đọc bằng `jq` trên log Railway, và cấp `X-Request-ID` để nối lời than phiền
  của người dùng về đúng dòng log. Thứ này phải sống kể cả khi mạng ra ngoài
  chết.
- Langfuse trả lời "lần gọi LLM đó tốn bao nhiêu token, hết bao nhiêu tiền, cây
  span của nó ra sao". Structured log không làm được vì `llm_ms` chỉ là một con
  số cộng dồn.

Nguyên tắc xuyên suốt file này: **đây là đường phụ**. Thiếu key, sai host, SDK
ném lỗi, mạng đứt — tất cả đều phải im lặng thoái lui, không được để một lời
gọi LLM thật hỏng theo. Mọi hàm public ở đây đều nuốt exception có chủ ý, và
đó là lý do chúng trông "quá cẩn thận" so với phần còn lại của repo.

Che dữ liệu mặc định BẬT (`LANGFUSE_MASK_PAYLOADS`). Prompt của app nhúng tên
chỉ số, giá trị, đơn vị, tuổi và giới tính bệnh nhân; gửi nguyên sang máy chủ
bên thứ ba là đưa dữ liệu sức khoẻ ra ngoài hạ tầng của mình. Cùng lý do đã
khiến listener SQLAlchemy không bao giờ log `statement`/`parameters`.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from src.config import get_settings

logger = logging.getLogger(__name__)

# Nội dung thay cho payload khi bật che. Cố ý là một chuỗi cố định, dễ nhận ra
# trên UI Langfuse, để không ai nhìn trace rỗng rồi tưởng LLM không được gọi.
MASKED_PLACEHOLDER = "[đã che — bật LANGFUSE_MASK_PAYLOADS=false ở môi trường dev để xem]"

# Khoá metadata được phép đi qua nguyên vẹn kể cả khi bật che. Toàn bộ là số đo
# hoặc mã trạng thái, không khoá nào mang dữ liệu bệnh nhân.
_SAFE_METADATA_KEYS = frozenset(
    {
        "analyte_id",
        "duration_ms",
        "environment",
        "error_type",
        "http_status",
        "model",
        "node",
        "outcome",
        "provider",
        "reason",
        "request_id",
        "role",
        "status",
        "workflow",
    }
)

_client: Any = None
_initialised = False


def _mask(*, data: Any, **_kwargs: Any) -> Any:
    """Thay mọi payload tự do bằng placeholder, giữ lại khoá đo lường an toàn.

    Langfuse gọi hàm này cho input/output của từng span trước khi gửi đi. Cách
    tiếp cận là danh sách CHO PHÉP chứ không phải danh sách chặn: chỉ khoá nào
    được liệt kê trong `_SAFE_METADATA_KEYS` mới đi qua. Danh sách chặn sẽ rò
    ngay lần đầu ai đó thêm một trường mới vào prompt mà quên cập nhật nó.
    """

    if isinstance(data, dict):
        return {key: (value if key in _SAFE_METADATA_KEYS else MASKED_PLACEHOLDER) for key, value in data.items()}
    if isinstance(data, list):
        return [_mask(data=item) for item in data]
    return MASKED_PLACEHOLDER


# Attribute chua thong bao loi cua provider tren span Langfuse.
_STATUS_MESSAGE_ATTR = "langfuse.observation.status_message"

# Chuoi trong thong bao loi bat dau tu day tro di la than JSON cua provider.
_ERROR_BODY_RE = re.compile(r"[{\[].*", re.DOTALL)

# Luoi an toan: bat cac token trong nhu API key cua cac nha cung cap hay gap.
_KEY_LIKE_RE = re.compile(r"(sk-[A-Za-z0-9_-]{4,}|AIza[A-Za-z0-9_-]{4,}|lsv2[A-Za-z0-9_-]{4,})")

_MAX_STATUS_MESSAGE_CHARS = 120


def scrub_status_message(text: str) -> str:
    """Giu lai ma loi, bo than thong bao cua provider.

    Do bang do that: mot lan goi hong tra ve

        Error code: 401 - {'error': {'message': 'Incorrect API key provided: AIzaSyBD***...

    va Langfuse ghi nguyen chuoi do len may chu cua ho. Ham `_mask()` khong cuu
    duoc vi no chi chay tren input/output, con day la mot attribute rieng.

    Than JSON cua provider la cho nguy hiem theo hai huong: no nhac lai mot phan
    API key nhu tren, va voi loi kiem duyet noi dung thi no nhac lai ca prompt —
    tuc la ca gia tri xet nghiem. Cat tu dau ngoac dau tien la chan duoc ca hai
    ma van giu "Error code: 401" / "Error code: 429", chinh la phan dang xem.

    CHAY BAT KE `LANGFUSE_MASK_PAYLOADS`. Tat che nghia la "cho toi xem prompt
    luc dev", khong bao gio co nghia la "cho phep lo credential".
    """

    cleaned = _ERROR_BODY_RE.sub("", text).strip(" -\t\n")
    cleaned = _KEY_LIKE_RE.sub("[redacted]", cleaned)
    if len(cleaned) > _MAX_STATUS_MESSAGE_CHARS:
        cleaned = cleaned[:_MAX_STATUS_MESSAGE_CHARS] + "..."
    return cleaned or "[loi khong ro]"


def _mask_otel_spans(*, params: Any) -> Any:
    """Lam sach `status_message` trong tung lo span truoc khi xuat di."""

    from langfuse.types import MaskOtelSpansResult, OtelSpanPatch

    patches = {}
    for identifier, span in params.spans.items():
        attributes = getattr(span, "attributes", None) or {}
        raw = attributes.get(_STATUS_MESSAGE_ATTR)
        if not raw:
            continue
        scrubbed = scrub_status_message(str(raw))
        if scrubbed != raw:
            patches[identifier] = OtelSpanPatch(set_attributes={_STATUS_MESSAGE_ATTR: scrubbed})

    return MaskOtelSpansResult(span_patches=patches) if patches else None


def is_configured() -> bool:
    """Có đủ cặp key để bật Langfuse hay không.

    Thiếu một trong hai là coi như tắt. Gửi nửa cặp key chỉ tạo ra một dòng lỗi
    xác thực mỗi lần gọi LLM.
    """

    settings = get_settings()
    return bool(settings.langfuse_public_key and settings.langfuse_secret_key)


def get_client() -> Any | None:
    """Client Langfuse dùng chung, khởi tạo một lần. `None` khi chưa cấu hình."""

    global _client, _initialised

    if _initialised:
        return _client

    _initialised = True

    if not is_configured():
        logger.info(
            "langfuse_disabled",
            extra={"reason": "missing_keys"},
        )
        return None

    settings = get_settings()
    try:
        from langfuse import Langfuse

        _client = Langfuse(
            public_key=settings.langfuse_public_key,
            secret_key=settings.langfuse_secret_key,
            host=settings.langfuse_host,
            environment=settings.app_env,
            mask=_mask if settings.langfuse_mask_payloads else None,
            # Luon bat, khong phu thuoc co che: khong bao gio duoc lo credential.
            mask_otel_spans=_mask_otel_spans,
        )
        logger.info(
            "langfuse_enabled",
            extra={
                "host": settings.langfuse_host,
                "environment": settings.app_env,
                "masked": settings.langfuse_mask_payloads,
            },
        )
    except Exception:
        # Không dùng logger.exception ở mức ERROR cho cả traceback: Langfuse
        # không cấu hình được là chuyện vận hành, không phải sự cố ứng dụng.
        logger.warning(
            "langfuse_init_failed",
            extra={"host": settings.langfuse_host},
            exc_info=True,
        )
        _client = None

    return _client


def get_callback_handler() -> Any | None:
    """Callback LangChain để gắn vào `get_llm()`. `None` khi Langfuse tắt.

    Gắn ở tầng `get_llm()` chứ không rải ở từng node, vì mọi lời gọi LLM trong
    repo đều đi qua đúng hàm đó — analyzer, guardrail, intent router, response
    composer, hai service xu hướng. Rải theo node là chắc chắn bỏ sót chỗ mới.
    """

    if get_client() is None:
        return None

    try:
        return _build_scrubbing_handler()
    except Exception:
        logger.warning("langfuse_callback_unavailable", exc_info=True)
        return None


def _build_scrubbing_handler() -> Any:
    """CallbackHandler co lam sach thong bao loi truoc khi ghi vao span.

    Vi sao phai lam o day chu khong o `mask_otel_spans`: thong bao loi cua
    provider duoc ghi vao HAI cho — attribute `langfuse.observation.status_message`
    VA truong Status cua span OTel. `OtelSpanPatch` chi sua duoc attribute, nen
    va o do thi ban sao trong Status van di ra nguyen ven. Do bang may chu bat
    goi cuc bo: va o tang patch, payload giam 251 byte nhung chuoi key van con.

    `_get_error_level_and_status_message()` la nguon chung cua ca hai ban sao,
    nen chan tai day la bit ca hai duong cung luc.

    Day la method private cua SDK, co the doi ten khi nang cap Langfuse. Nen neu
    khong tim thay thi lui ve handler goc thay vi no — mat mot lop lam sach con
    hon mat toan bo trace. `test_scrubbing_handler_falls_back_when_sdk_changes`
    giu dung hanh vi do.
    """

    from langfuse.langchain import CallbackHandler

    if not hasattr(CallbackHandler, "_get_error_level_and_status_message"):
        logger.warning("langfuse_error_scrubbing_unavailable")
        return CallbackHandler()

    class _ScrubbingCallbackHandler(CallbackHandler):  # type: ignore[misc, valid-type]
        def _get_error_level_and_status_message(self, error: BaseException) -> Any:
            level, message = super()._get_error_level_and_status_message(error)
            if message:
                message = scrub_status_message(str(message))
            return level, message

    return _ScrubbingCallbackHandler()


def flush() -> None:
    """Đẩy nốt trace còn trong buffer. Gọi lúc shutdown.

    Langfuse gửi theo lô ở luồng nền. Container bị kill mà không flush thì lô
    cuối mất — đúng lô chứa những request ngay trước sự cố, tức là lô đáng xem
    nhất.
    """

    client = get_client()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.warning("langfuse_flush_failed", exc_info=True)


def reset_for_tests() -> None:
    """Xoá client đã nhớ, để test đổi cấu hình rồi khởi tạo lại."""

    global _client, _initialised
    _client = None
    _initialised = False


__all__ = [
    "MASKED_PLACEHOLDER",
    "flush",
    "get_callback_handler",
    "get_client",
    "is_configured",
    "reset_for_tests",
    "scrub_status_message",
]
