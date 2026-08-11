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
    events: list[TimingEvent] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def record(self, name: str, duration_ms: float) -> None:
        with self._lock:
            self.metrics[_metric_name(name)] = round(max(0.0, duration_ms), 3)

    def record_since(self, name: str, started_at: float) -> float:
        duration = _duration_ms(started_at)
        self.record(name, duration)
        return duration

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
