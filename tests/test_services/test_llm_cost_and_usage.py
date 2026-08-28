"""Token và chi phí LLM — bảng giá, bắt token ở `get_llm()`, và tổng hợp.

Test quan trọng nhất ở đây không phải phép nhân, mà là hai điều:

1. **Model chưa có giá trả `None`, không trả `0.0`.** `$0.00` đọc như miễn phí,
   `—` đọc như không biết. Trên một màn hình dùng để quyết định chuyện tiền thì
   nhầm hai thứ đó là nhầm đắt.
2. **Đếm phủ đủ sáu chỗ gọi LLM.** Con số cũ chỉ đếm `analyzer_node` nên nó
   thiếu năm chỗ; callback gắn ở `get_llm()` phủ theo cấu trúc.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage

from src.services import llm_cost
from src.services.llm_usage import LlmUsageCallback, _extract_token_usage
from src.services.request_timing import (
    RequestTiming,
    reset_current_timing,
    set_current_timing,
)
from src.services.trace_metrics import GROUP_AI, summarise_by_group

# --- bảng giá ----------------------------------------------------------------


def test_cost_matches_the_published_per_million_rate():
    # gpt-4o-mini: $0.15 / 1M input, $0.60 / 1M output.
    breakdown = llm_cost.compute_cost("gpt-4o-mini", 2400, 700)
    assert breakdown.input_usd == pytest.approx(0.00036)
    assert breakdown.output_usd == pytest.approx(0.00042)
    assert breakdown.total_usd == pytest.approx(0.00078)
    assert breakdown.priced is True


def test_longest_prefix_wins_so_mini_is_not_charged_as_the_full_model():
    """`gpt-4o-mini` phải thắng `gpt-4o`.

    Khớp tiền tố ngắn nhất thì mọi lời gọi mini bị tính giá bản đầy đủ và chi
    phí báo sai gấp mười lần — theo hướng đáng sợ, tức là sẽ có người tưởng hệ
    thống đang đốt tiền và đi tối ưu nhầm chỗ.
    """

    mini = llm_cost.resolve_price("gpt-4o-mini-2024-07-18")
    full = llm_cost.resolve_price("gpt-4o-2024-11-20")
    assert mini == (0.15, 0.60)
    assert full == (2.50, 10.00)
    assert mini != full


def test_real_model_names_with_version_suffixes_are_priced():
    assert llm_cost.cost_usd("gpt-4o-mini-2024-07-18", 1_000_000, 0) == pytest.approx(0.15)
    assert llm_cost.cost_usd("GPT-4O-MINI", 1_000_000, 0) == pytest.approx(0.15)


@pytest.mark.parametrize("model", ["", None, "model-chua-biet", "llama-3-70b"])
def test_unknown_model_returns_none_never_zero(model):
    """Đây là quyết định quan trọng nhất của module giá.

    Đổi `MODEL_NAME` sang một model chưa có trong bảng mà trả `0.0` thì dashboard
    hiện "chi phí hôm nay $0.00" — đọc như miễn phí, trong khi thực tế là KHÔNG
    BIẾT. `None` buộc lớp hiển thị phải chọn giữa dấu gạch và một cảnh báo, cả
    hai đều trung thực hơn.
    """

    assert llm_cost.cost_usd(model, 1_000_000, 1_000_000) is None
    breakdown = llm_cost.compute_cost(model, 5000, 5000)
    assert breakdown.priced is False
    assert breakdown.total_usd is None
    # Token vẫn giữ: chúng ĐO ĐƯỢC, chỉ mỗi giá là không.
    assert breakdown.input_tokens == 5000


def test_pricing_table_carries_the_date_it_was_updated():
    """Một bảng giá không có ngày thì không ai biết nó còn đúng hay không."""

    assert llm_cost.PRICING_UPDATED
    assert len(llm_cost.PRICING_UPDATED) == 10


def test_negative_token_counts_are_clamped():
    assert llm_cost.compute_cost("gpt-4o-mini", -5, -5).total_usd == 0.0


# --- rút token khỏi phản hồi -------------------------------------------------


def test_extracts_usage_from_openai_style_llm_output():
    response = SimpleNamespace(
        llm_output={
            "token_usage": {"prompt_tokens": 120, "completion_tokens": 34},
            "model_name": "gpt-4o-mini-2024-07-18",
        },
        generations=[],
    )
    assert _extract_token_usage(response) == (120, 34, "gpt-4o-mini-2024-07-18")


def test_extracts_usage_from_message_usage_metadata():
    """Nhà cung cấp khác đặt usage trên message chứ không ở `llm_output`.

    Thử lần lượt nhiều hình dạng thay vì tin vào một cái: đoán sai thì token về
    0 mà không ai biết, và 0 token đọc như "miễn phí" chứ không như "không đo
    được".
    """

    message = SimpleNamespace(
        usage_metadata={"input_tokens": 90, "output_tokens": 12},
        response_metadata={"model_name": "gemini-2.0-flash"},
    )
    response = SimpleNamespace(llm_output={}, generations=[[SimpleNamespace(message=message)]])
    assert _extract_token_usage(response) == (90, 12, "gemini-2.0-flash")


def test_missing_usage_returns_zeros_without_raising():
    response = SimpleNamespace(llm_output=None, generations=None)
    assert _extract_token_usage(response) == (0, 0, None)


# --- callback gắn ở get_llm() -------------------------------------------------


@pytest.mark.asyncio
async def test_callback_records_tokens_and_cost_for_a_real_langchain_call():
    """Đi qua LangChain thật (model giả) để chứng minh hook có chạy.

    Bản đầu tôi viết callback theo duck typing và nó nổ ngay lúc dựng client:
    `ChatGoogleGenerativeAI` là model pydantic, nó cưỡng chế
    `is-instance[BaseCallbackHandler]`. Test này đi qua đúng đường LangChain gọi
    hook nên nó bắt được loại lỗi đó, khác hẳn việc gọi thẳng `on_llm_end`.
    """

    timing = RequestTiming()
    token = set_current_timing(timing)
    try:
        for _ in range(2):
            llm = GenericFakeChatModel(
                messages=iter(
                    [
                        AIMessage(
                            content="xanh",
                            usage_metadata={
                                "input_tokens": 1200,
                                "output_tokens": 350,
                                "total_tokens": 1550,
                            },
                            response_metadata={"model_name": "gpt-4o-mini-2024-07-18"},
                        )
                    ]
                ),
                callbacks=[LlmUsageCallback()],
            )
            await llm.ainvoke("màu gì")
    finally:
        timing.finish()
        fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)
        reset_current_timing(token)

    assert fields["llm_call_count"] == 2
    assert fields["llm_input_tokens"] == 2400
    assert fields["llm_output_tokens"] == 700
    assert fields["llm_cost_usd"] == pytest.approx(0.00078)
    assert fields["llm_unpriced_call_count"] == 0


@pytest.mark.asyncio
async def test_callback_never_breaks_the_llm_call_when_it_fails(monkeypatch):
    """Lớp đếm hỏng thì lời gọi LLM vẫn phải trả về bình thường.

    Một lớp đo lường làm chết câu trả lời của bệnh nhân thì tệ hơn hẳn việc mất
    một dòng số liệu. Cùng nguyên tắc đã áp cho `record_trace`.
    """

    def _explode(*_args, **_kwargs):
        raise RuntimeError("lớp đếm hỏng")

    monkeypatch.setattr("src.services.llm_usage.add_timing_event", _explode)

    llm = GenericFakeChatModel(
        messages=iter([AIMessage(content="vẫn trả lời được")]),
        callbacks=[LlmUsageCallback()],
    )
    result = await llm.ainvoke("gì đó")
    assert result.content == "vẫn trả lời được"


def test_no_llm_call_reports_none_cost_not_zero():
    timing = RequestTiming()
    timing.finish()
    fields = timing.as_log_fields(method="GET", path="/health", status_code=200)
    assert fields["llm_call_count"] == 0
    assert fields["llm_cost_usd"] is None
    assert fields["llm_input_tokens"] == 0


def test_errored_call_is_counted_but_not_charged():
    """Lời gọi lỗi tính vào `llm_error_count` nhưng không tính tiền.

    Nhà cung cấp không tính phí một lần gọi thất bại trước khi sinh, nên cộng
    nó vào chi phí là báo cao hơn thực tế.
    """

    timing = RequestTiming()
    timing.add_event("llm-call", 10.0, outcome="error", input_tokens=0, output_tokens=0, model="")
    timing.add_event("llm-call", 20.0, outcome="ok", input_tokens=1000, output_tokens=100, model="gpt-4o-mini")
    timing.finish()
    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)

    assert fields["llm_call_count"] == 2
    assert fields["llm_error_count"] == 1
    assert fields["llm_cost_usd"] == pytest.approx(0.00021)


def test_unpriced_calls_are_counted_so_cost_is_not_silently_understated():
    timing = RequestTiming()
    timing.add_event("llm-call", 5.0, outcome="ok", input_tokens=1000, output_tokens=100, model="gpt-4o-mini")
    timing.add_event("llm-call", 5.0, outcome="ok", input_tokens=9000, output_tokens=900, model="model-la")
    timing.finish()
    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)

    # Chi phí chỉ gồm phần tính được...
    assert fields["llm_cost_usd"] == pytest.approx(0.00021)
    # ...và màn hình được cho biết nó đang thiếu một lượt.
    assert fields["llm_unpriced_call_count"] == 1
    # Token thì vẫn đủ cả hai, vì token đo được.
    assert fields["llm_input_tokens"] == 10000


def test_legacy_traces_still_report_a_call_count():
    """Trace cũ chỉ có `llm-explanation-call` — vẫn phải đếm được.

    Mất con số còn tệ hơn con số tăng.
    """

    timing = RequestTiming()
    timing.add_event("llm-explanation-call", 30.0, outcome="ok")
    timing.finish()
    fields = timing.as_log_fields(method="POST", path="/api/v1/analyze", status_code=200)
    assert fields["llm_call_count"] == 1


# --- tổng hợp theo nhóm ------------------------------------------------------


def _row(cost, *, tokens_in=1000, tokens_out=100, unpriced=0, calls=1):
    return SimpleNamespace(
        path="/api/v1/analyze",
        method="POST",
        duration_ms=4000.0,
        status_code=200,
        llm_call_count=calls,
        llm_error_count=0,
        llm_input_tokens=tokens_in,
        llm_output_tokens=tokens_out,
        llm_cost_usd=cost,
        llm_unpriced_call_count=unpriced,
    )


def test_group_totals_sum_tokens_and_cost():
    groups = summarise_by_group([_row(0.001), _row(0.002)])
    ai = groups[GROUP_AI]
    assert ai["input_tokens"] == 2000
    assert ai["output_tokens"] == 200
    assert ai["cost_usd"] == pytest.approx(0.003)
    assert ai["cost_per_call_usd"] == pytest.approx(0.0015)


def test_group_cost_is_none_when_nothing_could_be_priced():
    groups = summarise_by_group([_row(None, unpriced=1), _row(None, unpriced=1)])
    ai = groups[GROUP_AI]
    assert ai["cost_usd"] is None
    assert ai["cost_per_call_usd"] is None
    assert ai["unpriced_call_count"] == 2
    # Token vẫn cộng được — chúng đo được, chỉ mỗi giá là không.
    assert ai["input_tokens"] == 2000


def test_cost_per_call_divides_by_llm_calls_not_requests():
    """Một request `/analyze` có thể gọi LLM nhiều lần.

    Chia cho số request sẽ làm "chi phí mỗi lượt gọi" phồng lên theo số chỉ số
    trong phiếu, tức là con số nói về phiếu chứ không nói về LLM.
    """

    groups = summarise_by_group([_row(0.004, calls=4)])
    assert groups[GROUP_AI]["cost_per_call_usd"] == pytest.approx(0.001)


def test_callback_survives_bind_tools_so_agent_calls_are_counted():
    """`bind_tools` không được làm mất callback đếm.

    Canonical `orchestrator/agent.py` dùng
    `get_llm().bind_tools(tools)` — chỗ gọi LLM thứ BẢY. Nó được đếm mà không ai
    phải sửa gì, và đó chính là lý do việc đếm nằm ở `get_llm()` chứ không rải
    theo node: đếm theo node thì hôm nay đã lại thiếu một chỗ.

    Kiểm cấu trúc chứ không gọi mạng: khẳng định callback bên trong là **cùng
    một đối tượng**, không phải bản copy — copy thì event sẽ đi vào một chỗ khác
    và không ai phát hiện.
    """

    from langchain_core.tools import tool
    from langchain_openai import ChatOpenAI

    @tool
    def cong_cu_thu(x: str) -> str:
        """Công cụ chỉ dùng trong test."""
        return x

    callback = LlmUsageCallback()
    model = ChatOpenAI(
        model="gpt-4o-mini",
        api_key="sk-khong-dung-that",
        callbacks=[callback],
    )
    bound = model.bind_tools([cong_cu_thu])

    inner = getattr(bound, "bound", None)
    assert inner is not None, "bind_tools phải giữ model bên trong"
    inner_callbacks = list(getattr(inner, "callbacks", None) or [])
    assert any(cb is callback for cb in inner_callbacks), f"callback đếm bị mất sau bind_tools: {inner_callbacks}"
