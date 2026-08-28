"""Phân loại lỗi — hàm thuần, không chạm DB.

## Vì sao "5xx = 3" là con số không dùng được

Card hiện tại trên `/admin` hiện `Lỗi 5xx — 3`. Câu hỏi tiếp theo của bất kỳ ai
đọc nó là "ba lỗi đó là lỗi gì?", và màn hình không trả lời được. Hôm nay tôi
truy được một trong số đó — `StringDataRightTruncation` từ cột
`pending_question` quá ngắn — nhưng phải grep log bằng tay, đọc traceback, rồi
đối chiếu tham số SQL. Một dashboard nói "có 3 lỗi" mà không nói loại thì chỉ
tiết kiệm được đúng bước đầu tiên.

## Nhóm được chọn theo "sửa bằng cách nào", không theo tên ngoại lệ

Phân loại có ích khi hai lỗi cùng nhóm thì cùng cách xử lý. `OperationalError`
và `PendingRollbackError` đều là `DB_*` vì cùng dẫn tới việc soi kết nối DB;
`RateLimitError` tách khỏi `LLM_PROVIDER` vì cách xử lý khác hẳn — một cái là
chờ, một cái là gọi nhà cung cấp.

## Ngoại lệ chưa khai KHÔNG bị bỏ

Nó thành `INTERNAL_EXCEPTION` và **giữ nguyên tên lớp** trong `raw_type`. Gộp
vào một nhóm "khác" rồi mất tên là làm chính lỗi chưa biết trở thành lỗi không
tra được — mà lỗi chưa biết mới đúng là loại cần tra.
"""

from __future__ import annotations

# Nhóm lỗi. Khai tường minh để `git diff` cho thấy ai thêm nhóm nào.
DB_TIMEOUT = "DB_TIMEOUT"
DB_CONNECTION = "DB_CONNECTION"
DB_INTEGRITY = "DB_INTEGRITY"
DB_SCHEMA = "DB_SCHEMA"
LLM_TIMEOUT = "LLM_TIMEOUT"
LLM_RATE_LIMIT = "LLM_RATE_LIMIT"
LLM_PROVIDER = "LLM_PROVIDER"
OCR_ERROR = "OCR_ERROR"
VALIDATION = "VALIDATION"
INTERNAL_EXCEPTION = "INTERNAL_EXCEPTION"

# Khớp theo tên lớp ngoại lệ. Khớp CHÍNH XÁC trước, rồi mới tới chứa-chuỗi:
# `TimeoutError` phải thắng luật "chứa Error" chung.
_EXACT: dict[str, str] = {
    # --- cơ sở dữ liệu ---
    "OperationalError": DB_CONNECTION,
    "InterfaceError": DB_CONNECTION,
    "DisconnectionError": DB_CONNECTION,
    "PendingRollbackError": DB_CONNECTION,
    "IntegrityError": DB_INTEGRITY,
    # `DataError` là cột quá ngắn / kiểu sai — lỗi lược đồ, không phải lỗi kết
    # nối. Đây đúng là loại đã làm mất lượt trả lời của trợ lý hôm 27/08.
    "DataError": DB_SCHEMA,
    "ProgrammingError": DB_SCHEMA,
    "UndefinedColumn": DB_SCHEMA,
    "StringDataRightTruncation": DB_SCHEMA,
    "TimeoutError": DB_TIMEOUT,
    "QueuePool": DB_TIMEOUT,
    # --- nhà cung cấp LLM ---
    "RateLimitError": LLM_RATE_LIMIT,
    "ResourceExhausted": LLM_RATE_LIMIT,
    "APITimeoutError": LLM_TIMEOUT,
    "ReadTimeout": LLM_TIMEOUT,
    "APIConnectionError": LLM_PROVIDER,
    "APIStatusError": LLM_PROVIDER,
    "InternalServerError": LLM_PROVIDER,
    "AuthenticationError": LLM_PROVIDER,
    "ChatGoogleGenerativeAIError": LLM_PROVIDER,
    "OrchestratorWrapperError": LLM_PROVIDER,
    # --- khác ---
    "ValidationError": VALIDATION,
    "ValueError": VALIDATION,
}

# Khớp theo chuỗi con, dùng khi tên lớp mang tiền tố của thư viện.
_CONTAINS: tuple[tuple[str, str], ...] = (
    ("RateLimit", LLM_RATE_LIMIT),
    ("Timeout", LLM_TIMEOUT),
    ("Vision", OCR_ERROR),
    ("Ocr", OCR_ERROR),
    ("OCR", OCR_ERROR),
    ("Integrity", DB_INTEGRITY),
    ("Operational", DB_CONNECTION),
    ("Data", DB_SCHEMA),
)


def classify_exception(exception_name: str | None) -> str:
    """Tên lớp ngoại lệ -> nhóm lỗi. Không khai thì `INTERNAL_EXCEPTION`."""

    if not exception_name:
        return INTERNAL_EXCEPTION

    name = exception_name.strip()
    if name in _EXACT:
        return _EXACT[name]
    for needle, group in _CONTAINS:
        if needle in name:
            return group
    return INTERNAL_EXCEPTION


def classify_status(status_code: int) -> str | None:
    """Nhóm lỗi suy từ mã HTTP khi không bắt được tên ngoại lệ.

    Chỉ 5xx. 4xx không phải lỗi hệ thống — đếm nó vào sẽ làm một đợt bot quét
    URL trông như hệ thống đang sập, cùng lý do đã áp cho error rate.

    `None` khi request không lỗi: khác hẳn `INTERNAL_EXCEPTION`, vốn nghĩa là
    "có lỗi mà chưa phân loại được".
    """

    if status_code >= 500:
        return INTERNAL_EXCEPTION
    return None


ALL_GROUPS: tuple[str, ...] = (
    DB_CONNECTION,
    DB_SCHEMA,
    DB_INTEGRITY,
    DB_TIMEOUT,
    LLM_PROVIDER,
    LLM_RATE_LIMIT,
    LLM_TIMEOUT,
    OCR_ERROR,
    VALIDATION,
    INTERNAL_EXCEPTION,
)


__all__ = [
    "ALL_GROUPS",
    "DB_CONNECTION",
    "DB_INTEGRITY",
    "DB_SCHEMA",
    "DB_TIMEOUT",
    "INTERNAL_EXCEPTION",
    "LLM_PROVIDER",
    "LLM_RATE_LIMIT",
    "LLM_TIMEOUT",
    "OCR_ERROR",
    "VALIDATION",
    "classify_exception",
    "classify_status",
]
