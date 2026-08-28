"""Cấu hình logging cho toàn app, đọc từ ``settings.log_level``.

Vì sao cần file này: trước đây không chỗ nào áp `log_level` vào logging. Uvicorn
chỉ cấu hình logger của riêng nó (`uvicorn.access`, `uvicorn.error`), còn logger
`src.*` rơi về mặc định WARNING của Python. Hệ quả là **mọi `logger.info()` trong
app đều bị nuốt**, kể cả dòng `request_timing` mang toàn bộ số liệu đo đạc.

Kiểm được trên production ngày 15/08: chuỗi `request_timing` xuất hiện đúng 3 lần
trong log và cả 3 đều nằm trong traceback, không có dòng trace thật nào. `RequestTiming`,
span ở graph node, span ở vision adapter — tất cả đang đo rồi đổ vào hư không.

Format là JSON một dòng để `grep` và `jq` được, và để sau này đẩy sang log
aggregator không phải viết lại parser.
"""

from __future__ import annotations

import json
import logging
import logging.config
from typing import Any

# Field chuẩn của LogRecord; mọi field khác là do người gọi thêm qua `extra=`
# nên được đưa hết vào payload JSON.
_RESERVED = frozenset(
    {
        "args",
        "asctime",
        "created",
        "exc_info",
        "exc_text",
        "filename",
        "funcName",
        "levelname",
        "levelno",
        "lineno",
        "message",
        "module",
        "msecs",
        "msg",
        "name",
        "pathname",
        "process",
        "processName",
        "relativeCreated",
        "stack_info",
        "taskName",
        "thread",
        "threadName",
    }
)


class JsonLogFormatter(logging.Formatter):
    """Một dòng JSON cho mỗi log record.

    Không tự thêm timestamp dạng chữ: Railway và hầu hết log collector đã tự gắn
    thời điểm nhận, thêm nữa chỉ tốn chỗ. `created` (epoch) vẫn giữ để sắp xếp
    chính xác khi cần.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "created": round(record.created, 3),
        }

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, value in record.__dict__.items():
            if key in _RESERVED or key.startswith("_"):
                continue
            # Chỉ nhận kiểu serialise được; tránh làm hỏng cả dòng log vì một
            # object lạ lọt vào qua extra=.
            if isinstance(value, str | int | float | bool | type(None)):
                payload[key] = value
            else:
                payload[key] = repr(value)

        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def build_logging_config(level: str) -> dict[str, Any]:
    level = level.upper()

    return {
        "version": 1,
        # KHÔNG tắt logger đã tồn tại: uvicorn cấu hình logger của nó trước khi
        # app import xong, tắt đi là mất log truy cập và log lỗi của server.
        "disable_existing_loggers": False,
        "formatters": {
            "json": {"()": "src.services.logging_config.JsonLogFormatter"},
        },
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "json",
                "stream": "ext://sys.stdout",
            },
        },
        # Root để WARNING chứ không phải `level`: nếu để INFO thì mọi thư viện
        # (httpx, asyncio, langchain, ragas...) cũng đổ log theo, dòng trace của
        # app chìm nghỉm và log production phình vô ích. httpx log một dòng
        # "HTTP Request: ..." cho mỗi lần gọi, trùng hoàn toàn với thứ
        # `request_timing` đã ghi.
        "root": {"handlers": ["default"], "level": "WARNING"},
        "loggers": {
            # Chỉ log của app mới đi theo level cấu hình.
            "src": {"level": level, "propagate": True},
            # uvicorn.access rất ồn và trùng thông tin với dòng `request_timing`
            # (đã có method, path, status_code, và toàn bộ breakdown thời gian).
            # Để WARNING cho khỏi nhân đôi mỗi request thành hai dòng.
            "uvicorn.access": {"level": "WARNING", "propagate": True},
            "uvicorn.error": {"level": level, "propagate": True},
        },
    }


def configure_logging(level: str | None = None) -> str:
    """Áp cấu hình logging. Trả về level đã dùng, để log lại được.

    Gọi càng sớm càng tốt lúc khởi động, trước khi có dòng log nào cần giữ.
    """

    if level is None:
        # Import trong hàm: file này được nạp rất sớm, tránh vòng import với
        # config nếu sau này config có thêm phụ thuộc.
        from src.config import get_settings

        level = get_settings().log_level

    logging.config.dictConfig(build_logging_config(level))

    return level.upper()
