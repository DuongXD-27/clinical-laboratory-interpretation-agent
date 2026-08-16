"""Per-request latency tracing exposed through logs and ``Server-Timing``.

The trace deliberately stores durations and operational labels only.  It must
never receive image contents, laboratory values, prompts, tokens or provider
credentials.
"""

from __future__ import annotations

import json
import re
import threading
import time
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass, field

_SERVER_TIMING_NAME_RE = re.compile(r"[^a-zA-Z0-9_-]+")
_current_timing: ContextVar[RequestTiming | None] = ContextVar(
    "current_request_timing",
    default=None,
)


def _duration_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 3)


def _metric_name(name: str) -> str:
    sanitized = _SERVER_TIMING_NAME_RE.sub("-", name.strip()).strip("-")
    return sanitized or "unnamed"


@dataclass
class TimingEvent:
    name: str
    duration_ms: float
    attributes: dict[str, str | int | float | bool] = field(default_factory=dict)


@dataclass
class RequestTiming:
    """Collect wall-clock stages for one HTTP request.

    ``metrics`` are unique, high-level spans suitable for the response header.
    ``events`` preserve repeated operations such as provider attempts and
    per-indicator LLM calls for the structured server log.
    """

    request_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    started_at: float = field(default_factory=time.perf_counter)
    metrics: dict[str, float] = field(default_factory=dict)
    # Số lần một metric được cộng dồn (xem `accumulate`). Chỉ có ý nghĩa với
    # thứ lặp lại trong một request, ví dụ số câu truy vấn DB.
    counters: dict[str, int] = field(default_factory=dict)
    events: list[TimingEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self.metrics[_metric_name(name)] = round(max(0.0, duration_ms), 3)

    def record_since(self, name: str, started_at: float) -> float:
        duration = _duration_ms(started_at)
        self.record(name, duration)
        return duration

    def accumulate(self, name: str, duration_ms: float) -> None:
        """Cộng dồn thay vì ghi đè, kèm đếm số lần.

        Dùng cho thứ lặp nhiều lần trong một request — truy vấn DB là ví dụ
        chính. `record()` ghi đè nên chỉ giữ được lần cuối; ở đây cần tổng thời
        gian và **số lần**, vì số lần mới là thứ để lộ N+1.
        """

        metric = _metric_name(name)
        with self._lock:
            self.metrics[metric] = round(
                self.metrics.get(metric, 0.0) + max(0.0, duration_ms), 3
            )
            self.counters[metric] = self.counters.get(metric, 0) + 1

    def add_event(
        self,
        name: str,
        duration_ms: float,
        **attributes: str | int | float | bool,
    ) -> None:
        event = TimingEvent(
            name=_metric_name(name),
            duration_ms=round(max(0.0, duration_ms), 3),
            attributes=attributes,
        )
        with self._lock:
            self.events.append(event)

    @contextmanager
    def span(self, name: str) -> Iterator[None]:
        started_at = time.perf_counter()
        try:
            yield
        finally:
            self.record_since(name, started_at)

    def finish(self) -> float:
        return self.record_since("http-total", self.started_at)

    def server_timing_header(self) -> str:
        with self._lock:
            metrics = list(self.metrics.items())
        return ", ".join(f'{name};dur={duration:.3f}' for name, duration in metrics)

    def _llm_summary(self, events: list[TimingEvent]) -> dict[str, object]:
        """Gom các lần gọi LLM thành ba con số phẳng.

        Suy từ event đã có sẵn chứ không bắt `analyzer_node` ghi thêm — nó vốn
        đã ghi `llm-explanation-call` kèm `outcome` cho từng chỉ số.

        Cần phẳng vì `events` là một chuỗi JSON trong dòng log: hỏi "request nào
        LLM chạy quá 5 giây" mà phải parse chuỗi đó thì không ai hỏi.

        ``llm_error_count`` là field đáng giá nhất ở đây. Khi LLM hỏng, analyzer
        im lặng rơi về curated explanation và bệnh nhân nhận nội dung xuống cấp —
        không mã lỗi, không cảnh báo, response vẫn 200. Có con số này thì "LLM
        đang hỏng bao nhiêu phần trăm" là một truy vấn log, thay vì phải gọi API
        rồi bấm giờ bằng tay.
        """

        calls = [event for event in events if event.name == "llm-explanation-call"]

        if not calls:
            return {"llm_call_count": 0, "llm_ms": None, "llm_error_count": 0}

        return {
            "llm_call_count": len(calls),
            "llm_ms": round(sum(call.duration_ms for call in calls), 3),
            "llm_error_count": sum(
                1 for call in calls if call.attributes.get("outcome") == "error"
            ),
        }

    def as_log_fields(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
    ) -> dict[str, object]:
        """Field phẳng để đưa vào `extra=` của logger.

        Khác `as_log_payload`: chỗ này trả dict để formatter JSON trộn thẳng vào
        dòng log, thay vì nhét một chuỗi JSON vào trong field `message`. Nhờ vậy
        `jq '.path'` hay lọc theo `.status_code` mới dùng được.
        """

        with self._lock:
            metrics = dict(self.metrics)
            counters = dict(self.counters)
            raw_events = list(self.events)

        events = [
            {
                "name": event.name,
                "duration_ms": event.duration_ms,
                **event.attributes,
            }
            for event in raw_events
        ]

        return {
            "request_id": self.request_id,
            "db_query_count": counters.get("db-query", 0),
            "db_ms": metrics.get("db-query"),
            **self._llm_summary(raw_events),
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": metrics.get("http-total"),
            # Hai field dưới là dict/list nên formatter sẽ repr() chúng; giữ
            # nguyên vì chúng là phần chi tiết, không phải khoá để lọc.
            "metrics_ms": json.dumps(metrics, ensure_ascii=False, separators=(",", ":")),
            "events": json.dumps(events, ensure_ascii=False, separators=(",", ":")),
        }

    def as_log_payload(
        self,
        *,
        method: str,
        path: str,
        status_code: int,
    ) -> str:
        with self._lock:
            metrics = dict(self.metrics)
            events = [
                {
                    "name": event.name,
                    "duration_ms": event.duration_ms,
                    **event.attributes,
                }
                for event in self.events
            ]
        return json.dumps(
            {
                "request_id": self.request_id,
                "method": method,
                "path": path,
                "status_code": status_code,
                "metrics_ms": metrics,
                "events": events,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def get_current_timing() -> RequestTiming | None:
    return _current_timing.get()


def set_current_timing(timing: RequestTiming) -> Token[RequestTiming | None]:
    return _current_timing.set(timing)


def reset_current_timing(token: Token[RequestTiming | None]) -> None:
    _current_timing.reset(token)


@contextmanager
def timing_span(name: str) -> Iterator[None]:
    timing = get_current_timing()
    if timing is None:
        yield
        return
    with timing.span(name):
        yield


def add_timing_event(
    name: str,
    duration_ms: float,
    **attributes: str | int | float | bool,
) -> None:
    timing = get_current_timing()
    if timing is not None:
        timing.add_event(name, duration_ms, **attributes)
