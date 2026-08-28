"""Trace log của request: có ra được log không, và có tra ngược được không.

Bộ test này tồn tại vì một lỗi thật: `RequestTiming`, span ở graph node, span ở
vision adapter đều chạy đúng, nhưng **không dòng nào ra tới log**. Không chỗ nào
áp `settings.log_level` vào logging, nên logger `src.*` rơi về mặc định WARNING
của Python và mọi `logger.info()` bị nuốt. Kiểm trên production 15/08: chuỗi
`request_timing` xuất hiện đúng 3 lần và cả 3 đều nằm trong traceback.

Nên test đầu tiên ở đây không kiểm nội dung trace, mà kiểm nó **có tồn tại**.
"""

import json
import logging

import pytest

from src.services.logging_config import JsonLogFormatter, build_logging_config

# --- Log có thật sự ra được không --------------------------------------------


def test_app_logger_emits_info_after_configuration():
    """Lỗi gốc: logger `src.*` ở mức WARNING nên INFO bị nuốt.

    Không dùng caplog vì caplog tự gắn handler và tự hạ level, nên nó sẽ pass
    kể cả khi cấu hình thật hỏng — đúng cách lỗi này lọt qua bấy lâu.
    """

    logging.config.dictConfig(build_logging_config("INFO"))

    logger = logging.getLogger("src.some.module")

    assert logger.isEnabledFor(logging.INFO), "INFO bi nuot — trace se khong bao gio ra log"


def test_log_level_from_config_is_actually_applied():
    logging.config.dictConfig(build_logging_config("WARNING"))
    assert not logging.getLogger("src.x").isEnabledFor(logging.INFO)

    logging.config.dictConfig(build_logging_config("DEBUG"))
    assert logging.getLogger("src.x").isEnabledFor(logging.DEBUG)


def test_uvicorn_loggers_are_not_disabled():
    """`disable_existing_loggers` bật lên là mất log truy cập và log lỗi server."""

    config = build_logging_config("INFO")

    assert config["disable_existing_loggers"] is False
    assert "uvicorn.error" in config["loggers"]


# --- Định dạng JSON ----------------------------------------------------------


def format_record(**extra) -> dict:
    record = logging.LogRecord(
        name="src.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="something_happened",
        args=(),
        exc_info=None,
    )
    for key, value in extra.items():
        setattr(record, key, value)
    return json.loads(JsonLogFormatter().format(record))


def test_formatter_emits_one_parseable_json_line():
    payload = format_record()

    assert payload["level"] == "INFO"
    assert payload["logger"] == "src.test"
    assert payload["message"] == "something_happened"
    assert isinstance(payload["created"], float)


def test_extra_fields_become_top_level_keys():
    """Phải phẳng thì `jq '.path'` mới dùng được, chứ không nhét JSON vào message."""

    payload = format_record(request_id="abc123", path="/api/v1/analyze", status_code=200)

    assert payload["request_id"] == "abc123"
    assert payload["path"] == "/api/v1/analyze"
    assert payload["status_code"] == 200


def test_unserialisable_extra_does_not_break_the_line():
    """Một object lạ lọt vào `extra=` không được làm hỏng cả dòng log."""

    payload = format_record(weird=object())

    assert isinstance(payload["weird"], str)


# --- Tra ngược từ người dùng về log ------------------------------------------


@pytest.mark.asyncio
async def test_every_response_carries_a_request_id(client):
    response = await client.get("/health")

    assert response.status_code == 200
    assert response.headers.get("X-Request-ID")
    assert response.headers.get("Server-Timing")


@pytest.mark.asyncio
async def test_request_ids_are_unique_per_request(client):
    first = await client.get("/health")
    second = await client.get("/health")

    assert first.headers["X-Request-ID"] != second.headers["X-Request-ID"]


@pytest.mark.asyncio
async def test_server_timing_header_reports_total_time(client):
    response = await client.get("/health")

    assert "http-total;dur=" in response.headers["Server-Timing"]


# --- Đo truy vấn DB ----------------------------------------------------------


def test_accumulate_sums_duration_and_counts_calls():
    """`record()` ghi đè nên chỉ giữ lần cuối; N+1 chỉ lộ ra qua SỐ LẦN."""

    from src.services.request_timing import RequestTiming

    timing = RequestTiming()
    for _ in range(12):
        timing.accumulate("db-query", 5.0)

    fields = timing.as_log_fields(method="GET", path="/x", status_code=200)

    assert fields["db_query_count"] == 12
    assert fields["db_ms"] == pytest.approx(60.0)


@pytest.mark.asyncio
async def test_db_queries_are_counted_for_a_real_request(client):
    """Số truy vấn của một request thật phải được đếm, không phải 0.

    Đây là con số làm N+1 nhìn thấy được. `_to_summary()` từng bắn hai truy vấn
    cho mỗi phiếu, vô hình khi DB nằm cùng đĩa và thành vài giây khi DB ra ngoài
    mạng.
    """

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "benhnhan", "password": "benhnhan123"},
    )
    assert login.status_code == 200

    timing_header = login.headers.get("Server-Timing", "")

    assert "db-query;dur=" in timing_header, timing_header


def test_third_party_libraries_stay_quiet_at_info():
    """Root phải là WARNING, nếu không log của app chìm trong log thư viện.

    Đặt root theo `level` thì httpx, asyncio, langchain, ragas cũng đổ INFO ra
    cùng chỗ. httpx ghi một dòng "HTTP Request: ..." mỗi lần gọi, trùng hoàn
    toàn với thứ `request_timing` đã ghi, chỉ tổ làm log production phình.
    """

    logging.config.dictConfig(build_logging_config("INFO"))

    assert logging.getLogger("src.main").isEnabledFor(logging.INFO)
    assert not logging.getLogger("httpx").isEnabledFor(logging.INFO)
    assert not logging.getLogger("ragas").isEnabledFor(logging.INFO)


# --- Gom số lần gọi LLM ------------------------------------------------------


def timing_with_llm_calls(*outcomes: str):
    from src.services.request_timing import RequestTiming

    timing = RequestTiming()
    for index, outcome in enumerate(outcomes):
        timing.add_event(
            "llm-explanation-call",
            100.0 + index,
            analyte_id=f"a{index}",
            outcome=outcome,
        )
    return timing


def test_llm_calls_are_summed_and_counted():
    timing = timing_with_llm_calls("success", "success", "success")

    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)

    assert fields["llm_call_count"] == 3
    assert fields["llm_ms"] == pytest.approx(303.0)
    assert fields["llm_error_count"] == 0


def test_failed_llm_calls_are_counted_separately():
    """Field đáng giá nhất: LLM hỏng thì response vẫn 200, chỉ nội dung xuống cấp.

    Analyzer im lặng rơi về curated explanation, không mã lỗi và không cảnh báo.
    Không có con số này thì không cách nào biết LLM đang hỏng bao nhiêu phần trăm
    trên production ngoài việc ngồi gọi API rồi bấm giờ bằng tay.
    """

    timing = timing_with_llm_calls("success", "error", "error")

    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)

    assert fields["llm_call_count"] == 3
    assert fields["llm_error_count"] == 2


def test_request_without_llm_reports_zero_not_missing():
    """Field phải luôn có mặt, nếu không thì lọc theo nó sẽ bỏ sót request."""

    from src.services.request_timing import RequestTiming

    fields = RequestTiming().as_log_fields(method="GET", path="/health", status_code=200)

    assert fields["llm_call_count"] == 0
    assert fields["llm_error_count"] == 0
    assert fields["llm_ms"] is None


def test_semaphore_wait_is_not_counted_as_an_llm_call():
    """`llm-semaphore-wait` là thời gian xếp hàng, không phải một lượt gọi."""

    from src.services.request_timing import RequestTiming

    timing = RequestTiming()
    timing.add_event("llm-semaphore-wait", 50.0, analyte_id="a0")
    timing.add_event("llm-explanation-call", 100.0, analyte_id="a0", outcome="success")

    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)

    assert fields["llm_call_count"] == 1
    assert fields["llm_ms"] == pytest.approx(100.0)


# --- Nối các dòng log của cùng một request --------------------------------


@pytest.mark.asyncio
async def test_orchestrator_log_shares_the_request_id_with_the_http_log(client, caplog):
    """Một lượt gọi HTTP chỉ được có MỘT request_id, dù sinh ra nhiều dòng log.

    `orchestrator_turn` từng tự sinh `uuid.uuid4().hex` riêng. Hệ quả: một lượt
    gọi đẻ ra hai dòng mang hai id khác nhau, không cách nào nối lại — đúng thứ
    mà cả lớp trace tồn tại để làm. Cùng id đó còn đi ra header `X-Request-ID`
    và vào bảng `request_traces`, nên admin dán một id là thấy cả chuỗi.
    """

    guest = await client.post("/api/v1/auth/guest")
    headers = {"Authorization": f"Bearer {guest.json()['access_token']}"}

    with caplog.at_level(logging.INFO, logger="src"):
        response = await client.post(
            "/api/v1/orchestrator/message",
            headers=headers,
            json={"message": "xin chao"},
        )

    assert response.status_code == 200
    header_id = response.headers["X-Request-ID"]

    turns = [record for record in caplog.records if record.getMessage() == "orchestrator_turn"]
    assert turns, "không thấy dòng orchestrator_turn nào"

    assert turns[-1].request_id == header_id, (
        "orchestrator ghi một id khác với id của request — hai dòng log không nối được"
    )
