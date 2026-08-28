from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.services.langfuse_tracing import get_callback_handler
from src.services.llm_usage import LlmUsageCallback


def get_llm() -> BaseChatModel:
    """Model chat dung chung cho toan bo repo.

    Callback Langfuse duoc gan tai day chu khong rai o tung node: analyzer,
    guardrail, intent router, response composer va hai service xu huong deu goi
    qua dung ham nay, nen gan mot cho la phu het. Rai theo node thi lan sau ai
    them mot cho goi LLM moi la trace thieu ma khong ai biet.

    `callbacks` rong khi Langfuse chua cau hinh — LangChain nhan list rong binh
    thuong, khong can nhanh re rieng.
    """

    settings = get_settings()
    handler = get_callback_handler()
    # `LlmUsageCallback` LUON duoc gan, khong phu thuoc Langfuse: no la nguon duy
    # nhat cho `llm_call_count`, token va chi phi. Truoc day con so do suy tu
    # event ma chi `analyzer_node` phat ra, nen no dem thieu 5 trong 6 cho goi
    # LLM — xem `llm_usage.py`.
    callbacks: list[object] = [LlmUsageCallback()]
    if handler is not None:
        callbacks.append(handler)

    if settings.llm_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.model_name,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
            callbacks=callbacks,
        )
    # `streaming` CHI bat cho OpenAI, va chi khi cau hinh cho phep.
    #
    # Vi sao khong bat cho Gemini: `ChatGoogleGenerativeAI` KHONG co tham so
    # `stream_usage`, nen khong bao dam duoc token usage con nguyen o che do
    # stream. Mat token la mat luon chi phi — doi mot con so do luong lay mot
    # con so do luong khac la trao doi lo.
    #
    # `stream_usage=True` la bat buoc di kem: OpenAI chi tra usage o che do
    # stream khi duoc yeu cau ro (`stream_options.include_usage`). Thieu no thi
    # bat streaming se AM THAM lam token va chi phi ve 0.
    streaming = settings.llm_streaming_enabled
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
        max_tokens=settings.openai_max_tokens,
        callbacks=callbacks,
        streaming=streaming,
        stream_usage=True if streaming else None,
    )
