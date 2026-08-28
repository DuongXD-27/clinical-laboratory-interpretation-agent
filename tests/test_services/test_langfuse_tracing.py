"""Lớp Langfuse: che dữ liệu, và không bao giờ làm chết đường chính.

Langfuse là đường phụ. Thiếu key, sai host, SDK ném lỗi, mạng đứt — mọi trường
hợp đều phải im lặng thoái lui. Bộ test này dựng từng trường hợp đó và kiểm
rằng `get_llm()` vẫn dựng được model, vì đó mới là thứ bệnh nhân phụ thuộc vào.

Nhóm test về che là nhóm quan trọng nhất: nó là điều kiện đã hứa khi chọn
phương án "chỉ gửi metadata". Prompt của app nhúng tên chỉ số, giá trị, đơn vị,
tuổi và giới tính bệnh nhân.
"""

from __future__ import annotations

import pytest

from src.config import get_settings
from src.services import langfuse_tracing
from src.services.langfuse_tracing import MASKED_PLACEHOLDER, _mask, scrub_status_message


@pytest.fixture(autouse=True)
def reset_langfuse():
    """Client được nhớ ở cấp module, phải xoá giữa các test đổi cấu hình."""

    langfuse_tracing.reset_for_tests()
    get_settings.cache_clear()
    yield
    langfuse_tracing.reset_for_tests()
    get_settings.cache_clear()


# --- Che dữ liệu -------------------------------------------------------------


def test_free_text_is_replaced_entirely():
    assert _mask(data="Glucose lúc đói 9.8 mmol/L, nữ 54 tuổi") == MASKED_PLACEHOLDER


def test_lab_values_inside_a_dict_do_not_survive():
    """Đúng hình dạng payload mà analyzer gửi cho LLM."""

    masked = _mask(
        data={
            "indicator_name": "Đường huyết lúc đói",
            "value": 9.8,
            "unit": "mmol/L",
            "patient_age": 54,
            "patient_gender": "female",
        }
    )

    assert all(value == MASKED_PLACEHOLDER for value in masked.values())
    serialised = str(masked)
    assert "9.8" not in serialised
    assert "54" not in serialised
    assert "Đường huyết" not in serialised


def test_measurement_keys_pass_through_so_the_trace_stays_useful():
    """Che hết sạch thì trace vô dụng. Vài khoá đo lường phải đi qua."""

    masked = _mask(
        data={
            "node": "analyzer",
            "duration_ms": 2143.5,
            "outcome": "success",
            "model": "gpt-4o-mini",
            "explanation": "Chỉ số của bạn cao hơn ngưỡng...",
        }
    )

    assert masked["node"] == "analyzer"
    assert masked["duration_ms"] == 2143.5
    assert masked["outcome"] == "success"
    assert masked["model"] == "gpt-4o-mini"
    assert masked["explanation"] == MASKED_PLACEHOLDER


def test_masking_is_an_allowlist_not_a_blocklist():
    """Khoá lạ phải bị che theo mặc định.

    Đây là tính chất then chốt. Danh sách CẤM sẽ rò ngay lần đầu ai đó thêm một
    trường mới vào prompt mà quên cập nhật nó — và không ai biết cho tới khi dữ
    liệu đã nằm trên máy chủ bên thứ ba. Danh sách CHO PHÉP thì trường mới nào
    cũng bị che cho tới khi có người cố ý mở.
    """

    masked = _mask(data={"truong_moi_ai_do_vua_them": "9.8 mmol/L"})

    assert masked["truong_moi_ai_do_vua_them"] == MASKED_PLACEHOLDER


def test_nested_lists_are_masked_too():
    """Chỉ số vào pipeline theo danh sách, không phải từng cái một."""

    masked = _mask(
        data=[
            {"indicator_name": "Kali", "value": 6.5},
            {"indicator_name": "LDL-C", "value": 5.5},
        ]
    )

    assert "Kali" not in str(masked)
    assert "6.5" not in str(masked)


# --- Bật/tắt -----------------------------------------------------------------


def test_disabled_without_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()

    assert langfuse_tracing.is_configured() is False
    assert langfuse_tracing.get_client() is None
    assert langfuse_tracing.get_callback_handler() is None


def test_half_a_key_pair_counts_as_disabled(monkeypatch):
    """Một nửa cặp key không phải "bật một nửa".

    Gửi thiếu key chỉ tạo ra một dòng lỗi xác thực cho mỗi lần gọi LLM, tốn
    thời gian mà không thu được trace nào.
    """

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-chi-co-mot-nua")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()

    assert langfuse_tracing.is_configured() is False


def test_client_is_built_once_and_reused(monkeypatch):
    calls = []

    class FakeLangfuse:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)

    first = langfuse_tracing.get_client()
    second = langfuse_tracing.get_client()

    assert first is second
    assert len(calls) == 1


def test_mask_function_is_handed_to_the_sdk_when_masking_is_on(monkeypatch):
    """Che phải do SDK áp, không phải do chỗ gọi nhớ áp.

    Nếu để từng chỗ gọi tự che thì chỉ cần một chỗ quên là dữ liệu bệnh nhân đi
    ra ngoài, và không có test nào bắt được chỗ quên đó.
    """

    captured = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)

    langfuse_tracing.get_client()

    assert captured["mask"] is not None
    assert captured["mask"](data="giá trị nhạy cảm") == MASKED_PLACEHOLDER


def test_masking_can_be_turned_off_deliberately(monkeypatch):
    captured = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_MASK_PAYLOADS", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)

    langfuse_tracing.get_client()

    assert captured["mask"] is None


# --- Đường phụ không được làm chết đường chính -------------------------------


def test_broken_sdk_does_not_stop_the_llm_from_being_built(monkeypatch):
    """Trường hợp đáng sợ nhất: Langfuse hỏng làm chết luôn phần giải thích."""

    def _explode(**_kwargs):
        raise RuntimeError("Langfuse sập")

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-khong-dung-that")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", _explode)

    assert langfuse_tracing.get_client() is None
    assert langfuse_tracing.get_callback_handler() is None

    from src.services.llm import get_llm

    assert get_llm() is not None


def test_get_llm_works_with_langfuse_switched_off(monkeypatch):
    """Tắt Langfuse thì không gắn handler Langfuse, nhưng `get_llm` vẫn chạy.

    Test này trước đây khẳng định `not model.callbacks` — tức `callbacks` rỗng
    hoàn toàn. Khẳng định đó **không còn đúng và cố ý không còn đúng**:
    `LlmUsageCallback` giờ LUÔN được gắn, không phụ thuộc Langfuse, vì nó là
    nguồn duy nhất cho `llm_call_count`, token và chi phí. Trước đó `llm_call_count`
    suy từ event mà chỉ `analyzer_node` phát ra, nên nó đếm thiếu năm trong sáu
    chỗ gọi LLM.

    Nên test được viết lại để khẳng định đúng thứ nó vốn muốn nói — "tắt Langfuse
    không làm hỏng `get_llm`, và không có handler Langfuse nào bị gắn" — thay vì
    một chi tiết phụ về độ dài danh sách. Đây là đổi hợp đồng có chủ ý, không
    phải nới lỏng test cho nó xanh: phần khẳng định về Langfuse còn chặt hơn
    trước, và thêm hẳn một khẳng định mới về callback đếm.
    """

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-khong-dung-that")
    get_settings.cache_clear()

    from src.services.llm import get_llm
    from src.services.llm_usage import LlmUsageCallback

    model = get_llm()

    assert model is not None

    callbacks = list(model.callbacks or [])
    # Không handler Langfuse nào — đây là điều test này tồn tại để kiểm.
    assert not any(type(cb).__module__.startswith("langfuse") for cb in callbacks), (
        f"Langfuse đã tắt mà vẫn gắn handler: {callbacks}"
    )

    # Và callback đếm thì luôn có, đúng một cái.
    assert sum(isinstance(cb, LlmUsageCallback) for cb in callbacks) == 1


def test_flush_is_safe_when_langfuse_is_off(monkeypatch):
    """Shutdown gọi flush vô điều kiện; tắt Langfuse không được làm hỏng shutdown."""

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    get_settings.cache_clear()

    langfuse_tracing.flush()  # không được ném gì


def test_flush_swallows_sdk_errors(monkeypatch):
    class FakeLangfuse:
        def __init__(self, **kwargs):
            pass

        def flush(self):
            raise RuntimeError("mất mạng lúc shutdown")

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)

    langfuse_tracing.flush()  # không được ném gì


# --- Làm sạch thông báo lỗi ---------------------------------------------------
#
# Nhóm này ra đời từ một vụ rò đo được thật, không phải từ suy đoán: một lời gọi
# LLM hỏng đẩy nguyên `Error code: 401 - {'error': {'message': 'Incorrect API key
# provided: AIzaSyBD***...'}}` lên máy chủ Langfuse. `_mask()` không cứu được vì
# nó chỉ chạy trên input/output.


def test_provider_error_body_is_dropped_but_the_code_survives():
    """Giữ phần đáng xem, bỏ phần nguy hiểm.

    `Error code: 401` là thứ cần để biết hỏng vì cái gì. Thân JSON phía sau mới
    là chỗ nhắc lại một phần API key, và với lỗi kiểm duyệt nội dung thì nó nhắc
    lại cả prompt — tức là cả giá trị xét nghiệm.
    """

    raw = "Error code: 401 - {'error': {'message': 'Incorrect API key provided: AIzaSyBD***7Mzc'}}"

    cleaned = scrub_status_message(raw)

    assert cleaned == "Error code: 401"
    assert "AIzaSy" not in cleaned
    assert "Incorrect API key" not in cleaned


def test_key_shaped_tokens_are_redacted_even_without_a_json_body():
    """Lưới an toàn cho thông báo lỗi không có dấu ngoặc để cắt."""

    for raw, fragment in [
        ("Loi nhac thang key sk-proj-ABCDEFGH1234 giua cau", "sk-proj"),
        ("Google tra ve AIzaSyBD9xKqLm trong loi", "AIzaSy"),
        ("LangSmith tu choi lsv2-pt-abcdefgh", "lsv2"),
    ]:
        cleaned = scrub_status_message(raw)
        assert fragment not in cleaned, raw
        assert "[redacted]" in cleaned


def test_ordinary_error_messages_pass_through_unharmed():
    assert scrub_status_message("Connection timeout after 30s") == "Connection timeout after 30s"


def test_empty_message_never_becomes_an_empty_span_field():
    assert scrub_status_message("") == "[loi khong ro]"


def test_very_long_message_is_capped():
    cleaned = scrub_status_message("x" * 500)

    assert len(cleaned) <= 130
    assert cleaned.endswith("...")


def test_scrubbing_runs_even_when_masking_is_switched_off(monkeypatch):
    """Tắt che nghĩa là "cho tôi xem prompt lúc dev", không bao giờ nghĩa là
    "cho phép lộ credential". Nên `mask_otel_spans` luôn được gắn."""

    captured = {}

    class FakeLangfuse:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "pk-lf-test")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "sk-lf-test")
    monkeypatch.setenv("LANGFUSE_MASK_PAYLOADS", "false")
    get_settings.cache_clear()
    monkeypatch.setattr("langfuse.Langfuse", FakeLangfuse)

    langfuse_tracing.get_client()

    assert captured["mask"] is None
    assert captured["mask_otel_spans"] is not None


def test_scrubbing_handler_falls_back_when_sdk_changes(monkeypatch):
    """`_get_error_level_and_status_message` là method private của SDK.

    Nâng cấp Langfuse mà nó đổi tên thì phải lui về handler gốc chứ không nổ —
    mất một lớp làm sạch còn hơn mất toàn bộ trace.
    """

    class HandlerWithoutTheHook:
        def __init__(self, *a, **k):
            pass

    monkeypatch.setattr("langfuse.langchain.CallbackHandler", HandlerWithoutTheHook)

    handler = langfuse_tracing._build_scrubbing_handler()

    assert isinstance(handler, HandlerWithoutTheHook)
