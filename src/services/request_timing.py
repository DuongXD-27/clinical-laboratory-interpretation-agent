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

from src.services import error_taxonomy, llm_cost

# Ten event cua moi loi goi LLM. Dinh nghia TAI DAY chu khong o `llm_usage`:
# `llm_usage` da phu thuoc module nay (no goi `add_timing_event`), nen dat hang
# so ben do roi import nguoc lai la vong tron import.
LLM_CALL_EVENT = "llm-call"

# Guardrail phai thay van ban cua LLM bang van ban an toan dung san.
GUARDRAIL_FALLBACK_EVENT = "guardrail-fallback"
# Guardrail yeu cau LLM viet lai mot lan truoc khi roi ve van ban dung san.
GUARDRAIL_REWRITE_EVENT = "guardrail-rewrite"
# Ngoai le da bi chan o exception handler.
ERROR_EVENT = "unhandled-error"

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
            self.metrics[metric] = round(self.metrics.get(metric, 0.0) + max(0.0, duration_ms), 3)
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
        return ", ".join(f"{name};dur={duration:.3f}" for name, duration in metrics)

    def _llm_summary(self, events: list[TimingEvent]) -> dict[str, object]:
        """Gom moi loi goi LLM thanh cac con so phang: so luot, ms, loi, token, tien.

        ## Nguon la event `llm-call` do callback o `get_llm()` phat ra

        Truoc day ham nay dem event `llm-explanation-call`, ma **chi
        `analyzer_node` phat ra**. Co BAY cho goi `get_llm()`: analyzer,
        guardrail, canonical Agent, and other LLM-backed services (nguoi khac them o
        PR #92) va hai service xu huong. Nen `llm_call_count` DEM THIEU sau
        trong bay cho, va `llm_error_count`
        — field ma ca lop quan sat ton tai vi no — sai theo dung cach do.

        Callback gan o `get_llm()` thi theo cau truc phu het, ke ca cho them sau
        nay. Doi lai: **con so nay se TANG so voi bang cu**. Do la sua sai, khong
        phai hoi quy — nhung ai so sanh so lieu truoc va sau ngay 27/08 can biet.

        Van giu nhanh du phong doc `llm-explanation-call`: trace cu trong DB va
        vai test dung truc tiep event do, va mat con so con te hon con so tang.

        ## Chi phi la UOC LUONG, va co the khong tinh duoc

        `llm_cost_usd` la `None` khi khong loi goi nao doc duoc gia (model chua
        co trong bang gia). KHONG tra 0.0 — 0 doc nhu mien phi chu khong nhu
        khong biet. `llm_unpriced_call_count` noi ro bao nhieu luot bi bo ngoai
        phep tinh, de mot bang gia cu khong am tham lam chi phi bao thap di.
        """

        calls = [event for event in events if event.name == LLM_CALL_EVENT]
        if not calls:
            calls = [event for event in events if event.name == "llm-explanation-call"]

        if not calls:
            return {
                "llm_call_count": 0,
                "llm_ms": None,
                "llm_error_count": 0,
                "llm_input_tokens": 0,
                "llm_output_tokens": 0,
                "llm_cost_usd": None,
                "llm_unpriced_call_count": 0,
            }

        input_tokens = 0
        output_tokens = 0
        cost_total = 0.0
        priced_any = False
        unpriced = 0

        for call in calls:
            call_in = int(call.attributes.get("input_tokens", 0) or 0)
            call_out = int(call.attributes.get("output_tokens", 0) or 0)
            input_tokens += call_in
            output_tokens += call_out

            if call.attributes.get("outcome") == "error":
                # Loi thi khong co token va khong co tien — nha cung cap khong
                # tinh phi mot lan goi that bai truoc khi sinh.
                continue

            model = str(call.attributes.get("model", "") or "")
            call_cost = llm_cost.cost_usd(model, call_in, call_out)
            if call_cost is None:
                # Chi tinh la "chua co gia" khi that su co token de tinh. Mot
                # luot 0 token thi khong co gi bi bo ngoai phep tinh.
                if call_in or call_out:
                    unpriced += 1
            else:
                cost_total += call_cost
                priced_any = True

        return {
            "llm_call_count": len(calls),
            "llm_ms": round(sum(call.duration_ms for call in calls), 3),
            "llm_error_count": sum(1 for call in calls if call.attributes.get("outcome") == "error"),
            "llm_input_tokens": input_tokens,
            "llm_output_tokens": output_tokens,
            "llm_cost_usd": round(cost_total, 6) if priced_any else None,
            "llm_unpriced_call_count": unpriced,
        }

    def _quality_summary(self, events: list[TimingEvent]) -> dict[str, object]:
        """Tin hieu chat luong va nhom loi — do duoc, khong suy dien.

        `guardrail_fallback_count` la tin hieu chat luong THAT duy nhat co the do
        o thoi diem nay: guardrail thay van ban cua LLM bang van ban dung san
        nghia la benh nhan nhan noi dung xuong cap, ma response van 200 va khong
        co ma loi nao. Do dung cai bay ma CLAUDE.md ghi lai.

        KHONG co "groundedness" o day. Do la con so can mot bo danh gia truc
        tuyen cham diem tung cau tra loi; bay gio chua co, va dat mot con so
        phan tram ve do dung y khoa ma khong do duoc la loai bia nguy hiem nhat.
        """

        error_events = [event for event in events if event.name == ERROR_EVENT]
        raw_type = str(error_events[-1].attributes.get("exception_type", "")) if error_events else ""

        return {
            "guardrail_fallback_count": sum(1 for event in events if event.name == GUARDRAIL_FALLBACK_EVENT),
            "guardrail_rewrite_count": sum(1 for event in events if event.name == GUARDRAIL_REWRITE_EVENT),
            "error_raw_type": raw_type or None,
            "error_type": error_taxonomy.classify_exception(raw_type) if raw_type else None,
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
            **self._quality_summary(raw_events),
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
