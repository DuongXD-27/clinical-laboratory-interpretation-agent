"""Đếm lời gọi LLM, token và thời gian — gắn một chỗ ở `get_llm()`.

## Vì sao phải là callback, không phải đếm ở từng node

`llm_call_count` trước đây suy từ event `llm-explanation-call` mà **chỉ
`analyzer_node` phát ra**. Runtime hiện có các chỗ gọi `get_llm()` sau:

    analyzer_node.py                         <- duy nhất chỗ được đếm
    guardrail_node.py
    orchestrator/agent.py
    trend_explanation_service.py
    section_trend_explanation_service.py

Canonical Agent dùng `get_llm().bind_tools(tools)` và được đếm tự động mà không
cần một đường đo riêng. Đếm theo node sẽ tiếp tục bỏ sót consumer mới.

Nên con số "27 lượt gọi LLM" trên màn admin **đếm thiếu**, và `llm_error_count`
— field mà cả lớp quan sát tồn tại vì nó — sai theo đúng cách đó. Với mỗi lượt
Agent có thể thực hiện nhiều lượt lập kế hoạch và gọi tool trong một turn.

Đặt việc đếm vào callback gắn ở `get_llm()` thì theo cấu trúc nó phủ mọi chỗ
**và mọi chỗ thêm sau này**. Cùng lý do Langfuse callback được gắn đúng ở đó:
rải theo node là bảo đảm lần sau ai thêm một chỗ gọi mới thì số liệu thiếu mà
không ai biết.

## Không bao giờ được làm hỏng lời gọi LLM

Mọi hook ở đây nuốt lỗi. Một lớp đếm làm chết câu trả lời của bệnh nhân thì tệ
hơn hẳn việc mất một dòng số liệu. Cùng nguyên tắc đã áp cho `record_trace`.
"""

from __future__ import annotations

import logging
import time
from typing import Any
from uuid import UUID

from langchain_core.callbacks import BaseCallbackHandler

from src.services.request_timing import LLM_CALL_EVENT, add_timing_event

logger = logging.getLogger(__name__)


def _extract_token_usage(response: Any) -> tuple[int, int, str | None]:
    """Rút (input, output, model) từ `LLMResult`, chịu được mọi hình dạng.

    LangChain đặt usage ở nhiều chỗ tuỳ phiên bản và tuỳ nhà cung cấp:
    `llm_output["token_usage"]`, `llm_output["usage_metadata"]`, hoặc trên
    `generation.message.usage_metadata`. Thử lần lượt thay vì tin vào một hình
    dạng — đoán sai thì token về 0 mà không ai biết, và 0 token đọc như "miễn
    phí" chứ không như "không đo được".
    """

    llm_output = getattr(response, "llm_output", None) or {}
    model = llm_output.get("model_name") or llm_output.get("model")

    for key in ("token_usage", "usage_metadata", "usage"):
        usage = llm_output.get(key)
        if isinstance(usage, dict):
            prompt = usage.get("prompt_tokens", usage.get("input_tokens", 0))
            completion = usage.get("completion_tokens", usage.get("output_tokens", 0))
            if prompt or completion:
                return int(prompt or 0), int(completion or 0), model

    # Chưa thấy ở `llm_output`: tìm trên từng generation.
    for batch in getattr(response, "generations", None) or []:
        for generation in batch or []:
            message = getattr(generation, "message", None)
            usage = getattr(message, "usage_metadata", None)
            if isinstance(usage, dict):
                prompt = usage.get("input_tokens", 0)
                completion = usage.get("output_tokens", 0)
                if prompt or completion:
                    meta = getattr(message, "response_metadata", None) or {}
                    return (
                        int(prompt or 0),
                        int(completion or 0),
                        model or meta.get("model_name") or meta.get("model"),
                    )

    return 0, 0, model


class LlmUsageCallback(BaseCallbackHandler):
    """Callback LangChain ghi mỗi lời gọi LLM thành một event đo lường.

    PHẢI kế thừa `BaseCallbackHandler`. Bản đầu tôi viết theo duck typing với
    lý do "LangChain nhận bất cứ đối tượng nào có đúng method hook" — sai:
    `ChatGoogleGenerativeAI` là model pydantic và nó cưỡng chế
    `is-instance[BaseCallbackHandler]`, nên lời gọi `get_llm()` nổ ngay lúc dựng
    client. Phát hiện bằng một lời gọi LLM thật trước khi xây gì lên trên.
    """

    raise_error = False

    def __init__(self) -> None:
        super().__init__()
        # Khoá theo `run_id` của LangChain: nhiều lời gọi có thể chạy song song
        # trong cùng một request (analyzer gọi cho từng chỉ số), nên một biến
        # `started_at` duy nhất sẽ trộn thời gian của chúng vào nhau.
        self._started: dict[str, float] = {}

    # --- hook ---------------------------------------------------------------

    def on_llm_start(self, serialized: Any, prompts: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        self._mark_start(run_id)

    def on_chat_model_start(self, serialized: Any, messages: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        self._mark_start(run_id)

    def on_llm_end(self, response: Any, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        try:
            duration_ms = self._take_duration(run_id)
            input_tokens, output_tokens, model = _extract_token_usage(response)
            add_timing_event(
                LLM_CALL_EVENT,
                duration_ms,
                outcome="ok",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                model=model or "",
            )
        except Exception:
            # Nuốt: một lớp đếm không được phép làm chết câu trả lời của bệnh nhân.
            logger.warning("llm_usage_callback_failed", exc_info=True)

    def on_llm_error(self, error: BaseException, *, run_id: UUID | None = None, **kwargs: Any) -> None:
        try:
            duration_ms = self._take_duration(run_id)
            # KHÔNG ghi nội dung `error` vào event: thông báo lỗi của nhà cung
            # cấp đã từng mang theo một phần API key. Chỉ ghi loại ngoại lệ.
            add_timing_event(
                LLM_CALL_EVENT,
                duration_ms,
                outcome="error",
                input_tokens=0,
                output_tokens=0,
                model="",
                error_type=type(error).__name__,
            )
        except Exception:
            logger.warning("llm_usage_callback_failed", exc_info=True)

    # --- nội bộ -------------------------------------------------------------

    def _mark_start(self, run_id: UUID | None) -> None:
        try:
            self._started[str(run_id)] = time.perf_counter()
        except Exception:
            logger.warning("llm_usage_callback_failed", exc_info=True)

    def _take_duration(self, run_id: UUID | None) -> float:
        started = self._started.pop(str(run_id), None)
        if started is None:
            # Không thấy `on_*_start` (callback gắn giữa luồng, hoặc run_id khác
            # nhau giữa start và end): vẫn ghi lời gọi với 0ms thay vì bỏ hẳn.
            # Mất thời lượng còn hơn mất cả lượt gọi khỏi số liệu.
            return 0.0
        return round((time.perf_counter() - started) * 1000, 3)


__all__ = ["LLM_CALL_EVENT", "LlmUsageCallback"]
