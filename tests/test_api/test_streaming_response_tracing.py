"""Phản hồi dạng stream phải được đo hết, không dừng ở lúc gửi xong header.

## Lỗi thật, đo trên production 29/08

Hỏi chatbot một câu rồi mở màn `/admin`: tần suất request và chi phí LLM đều
bằng 0. Dòng trace nói rõ vì sao:

    POST /api/v1/orchestrator/message/stream  200  dur=30.985  llm_calls=0  llm_ms=0.0
    POST /api/v1/orchestrator/message/stream  200  dur=31.542  llm_calls=0  llm_ms=0.0

Một lượt chat thật mất vài giây và gọi LLM nhiều lần. 31ms là thời gian trả
**header** SSE.

`BaseHTTPMiddleware` trả về ngay khi `call_next` có đối tượng response. Với
`StreamingResponse` thì lúc đó thân phản hồi chưa chạy dòng nào — mà toàn bộ
lượt orchestrator, tức mọi lời gọi LLM, nằm trong `stream_sse_frames`. Middleware
chốt sổ, ghi log, ghi DB, rồi `reset_current_timing` — tất cả trước khi công việc
thật bắt đầu.

Hậu quả không chỉ là mất số:

- `llm_call_count` và chi phí về 0, nên đường chat coi như miễn phí. Đây là
  đường tốn tiền nhất trong sản phẩm.
- `duration_ms` 31ms lẫn vào mẫu tính phân vị của nhóm AI, kéo P95 xuống. Đúng
  cái bệnh mà việc tách nhóm endpoint sinh ra để chữa.
- Không lỗi nào hiện ra. Một lượt chat vỡ giữa stream vẫn ghi 200.

## Vì sao test dựng route riêng chứ không gọi thẳng `/orchestrator/message/stream`

Endpoint thật cần đăng nhập, hội thoại, và một LLM sống. Ghim vào đó thì test đo
lẫn nhiều thứ và sẽ đỏ vì lý do khác. Cái cần ghim là hợp đồng của tầng
middleware: **việc làm bên trong thân stream phải nằm trong dòng trace**. Route
dựng ở đây phát đúng loại sự kiện mà `LlmUsageCallback` phát, nên nếu middleware
đúng thì đường chat thật cũng đúng.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.responses import StreamingResponse

from src.main import app
from src.services.request_timing import LLM_CALL_EVENT, add_timing_event

STREAM_PATH = "/api/v1/test-only/stream"
PLAIN_PATH = "/api/v1/test-only/plain"

# Đủ lâu để phân biệt chắc chắn với thời gian trả header.
WORK_MS = 120


@pytest.fixture(autouse=True)
def temporary_streaming_routes():
    """Gắn hai route chỉ dùng cho test, gỡ sạch sau đó.

    Có cả bản không stream để làm đối chứng: nếu bản đó cũng hỏng thì lỗi nằm ở
    chỗ khác chứ không phải ở stream.
    """

    async def frames():
        await asyncio.sleep(WORK_MS / 1000)
        # Đúng sự kiện mà `LlmUsageCallback.on_llm_end` phát ra.
        add_timing_event(
            LLM_CALL_EVENT,
            42.0,
            outcome="ok",
            input_tokens=100,
            output_tokens=5,
            model="gpt-4o-mini",
        )
        yield b"data: xong\n\n"

    @app.get(STREAM_PATH)
    async def _stream():  # pragma: no cover - đăng ký route
        return StreamingResponse(frames(), media_type="text/event-stream")

    @app.get(PLAIN_PATH)
    async def _plain():  # pragma: no cover - đăng ký route
        await asyncio.sleep(WORK_MS / 1000)
        add_timing_event(
            LLM_CALL_EVENT,
            42.0,
            outcome="ok",
            input_tokens=100,
            output_tokens=5,
            model="gpt-4o-mini",
        )
        return {"ok": True}

    yield

    app.router.routes = [
        route for route in app.router.routes if getattr(route, "path", None) not in {STREAM_PATH, PLAIN_PATH}
    ]
    app.openapi_schema = None


TASK_PATH = "/api/v1/test-only/stream-task"


@pytest.fixture(autouse=True)
def temporary_task_spawning_route():
    """Đúng hình dạng của đường chat thật, không phải một bản giản lược.

    `stream_sse_frames` không tự gọi LLM: nó `asyncio.create_task` cho
    `handle_message` rồi đọc kết quả qua một hàng đợi. Nghĩa là lời gọi LLM nằm
    sâu thêm **một** lớp task nữa so với thân stream.

    Chuyện đó quan trọng vì `asyncio.create_task` COPY context lúc tạo. Nếu
    `reset_current_timing` chạy trước khi task được tạo thì task copy phải một
    context đã rỗng, và sự kiện rơi vào hư không — im lặng, y như lỗi gốc. Test
    này ghim đúng chỗ đó.
    """

    async def frames():
        async def work():
            await asyncio.sleep(WORK_MS / 1000)
            add_timing_event(
                LLM_CALL_EVENT,
                42.0,
                outcome="ok",
                input_tokens=100,
                output_tokens=5,
                model="gpt-4o-mini",
            )

        task = asyncio.create_task(work())
        await task
        yield b"data: xong\n\n"

    @app.get(TASK_PATH)
    async def _stream_task():  # pragma: no cover - đăng ký route
        return StreamingResponse(frames(), media_type="text/event-stream")

    yield

    app.router.routes = [route for route in app.router.routes if getattr(route, "path", None) != TASK_PATH]
    app.openapi_schema = None


def _trace(test_db, path: str):
    from src.models.db import RequestTrace

    with test_db.session() as session:
        return session.query(RequestTrace).filter(RequestTrace.path == path).one_or_none()


# --- đối chứng: đường không stream phải đúng ---------------------------------


@pytest.mark.asyncio
async def test_non_streaming_response_records_its_llm_call(client, test_db):
    """Đối chứng. Nếu ca này cũng đỏ thì lỗi không nằm ở stream."""

    response = await client.get(PLAIN_PATH)
    assert response.status_code == 200

    row = _trace(test_db, PLAIN_PATH)
    assert row is not None, "không có dòng trace nào"
    assert row.llm_call_count == 1
    assert row.duration_ms >= WORK_MS * 0.8


# --- điều kiện chính ----------------------------------------------------------


@pytest.mark.asyncio
async def test_streaming_response_counts_llm_calls_made_inside_the_body(client, test_db):
    """Lời gọi LLM phát trong thân stream phải vào dòng trace.

    Đây chính là con số 0 mà nhóm trưởng nhìn thấy trên `/admin`.
    """

    response = await client.get(STREAM_PATH)
    assert response.status_code == 200
    assert b"xong" in response.content  # đọc hết thân, giống trình duyệt

    row = _trace(test_db, STREAM_PATH)
    assert row is not None, "không có dòng trace nào cho đường stream"
    assert row.llm_call_count == 1, f"lời gọi LLM trong thân stream không được đếm (đếm được {row.llm_call_count})"
    assert row.llm_input_tokens == 100
    assert row.llm_output_tokens == 5


@pytest.mark.asyncio
async def test_normal_responses_keep_their_server_timing_header(client):
    """Đường thường KHÔNG được mất `Server-Timing` vì bản sửa này.

    Dưới `BaseHTTPMiddleware` mọi phản hồi đều là `_StreamingResponse`, nên bản
    sửa đầu tiên của tôi hoãn chốt sổ cho tất cả — và header biến mất khỏi mọi
    request. Không ai nhìn thấy: nó chỉ lặng lẽ không còn ở devtools.

    Phân biệt bằng `content-length`: phản hồi thường có, phản hồi stream không.
    """

    response = await client.get(PLAIN_PATH)
    assert "http-total;dur=" in response.headers.get("Server-Timing", ""), (
        "Server-Timing rỗng hoặc mất — đã chốt sổ sau khi dựng header"
    )


@pytest.mark.asyncio
async def test_streaming_response_still_carries_a_request_id(client):
    """Stream không có `Server-Timing` nhưng phải có `X-Request-ID`.

    Header phải gửi đi khi chưa đo được gì, nên một `Server-Timing` ở đó chỉ có
    thể là số rỗng hoặc số sai — mà số sai thì chạy thẳng vào cây span. Chuỗi
    đầy đủ vẫn được ghi vào DB sau khi stream xong, và đó mới là thứ `/admin`
    đọc; header chỉ phục vụ devtools.

    `X-Request-ID` thì vẫn phải có: không có nó thì một lượt chat hỏng không tra
    ngược được về dòng log nào.
    """

    response = await client.get(STREAM_PATH)
    assert response.headers.get("X-Request-ID")
    assert not response.headers.get("Server-Timing")


@pytest.mark.asyncio
async def test_streaming_trace_still_stores_the_full_server_timing(client, test_db):
    """Mất header là chấp nhận được; mất dữ liệu thì không."""

    response = await client.get(STREAM_PATH)
    assert b"xong" in response.content

    row = _trace(test_db, STREAM_PATH)
    assert row is not None
    assert "http-total;dur=" in (row.server_timing or ""), "dòng trace của stream không có chuỗi Server-Timing"


@pytest.mark.asyncio
async def test_streaming_duration_covers_the_body_not_just_the_headers(client, test_db):
    """`duration_ms` phải là thời gian tới lúc stream xong.

    Dừng ở header thì một lượt chat 5 giây ghi thành 31ms, và con số đó lẫn vào
    mẫu tính phân vị của nhóm AI — kéo P95 xuống đúng chỗ nó phải cảnh báo.
    """

    response = await client.get(STREAM_PATH)
    assert response.status_code == 200
    assert b"xong" in response.content

    row = _trace(test_db, STREAM_PATH)
    assert row is not None
    assert row.duration_ms >= WORK_MS * 0.8, (
        f"duration_ms {row.duration_ms} nhỏ hơn thời gian thân stream ({WORK_MS}ms) — đồng hồ đã chốt ở lúc gửi header"
    )


@pytest.mark.asyncio
async def test_llm_call_from_a_task_spawned_inside_the_stream_is_counted(client, test_db):
    """Đây là hình dạng thật của `/orchestrator/message/stream`.

    Lời gọi LLM nằm trong một task được tạo bên trong thân stream. Nếu context
    không còn giữ được `RequestTiming` tới lúc đó thì sự kiện mất, và mất im
    lặng — trace vẫn 200, chỉ là 0 lượt gọi và 0 đồng.
    """

    response = await client.get(TASK_PATH)
    assert response.status_code == 200
    assert b"xong" in response.content

    row = _trace(test_db, TASK_PATH)
    assert row is not None
    assert row.llm_call_count == 1, "lời gọi LLM trong task lồng trong stream không được đếm"
    assert row.duration_ms >= WORK_MS * 0.8
