from langchain_core.language_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI

from src.config import get_settings
from src.services.langfuse_tracing import get_callback_handler


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
    callbacks = [handler] if handler is not None else []

    if settings.llm_provider == "gemini":
        return ChatGoogleGenerativeAI(
            model=settings.model_name,
            google_api_key=settings.google_api_key,
            temperature=settings.llm_temperature,
            timeout=settings.llm_timeout_seconds,
            max_retries=1,
            callbacks=callbacks,
        )
    return ChatOpenAI(
        model=settings.model_name,
        api_key=settings.openai_api_key,
        temperature=settings.llm_temperature,
        timeout=settings.llm_timeout_seconds,
        max_retries=1,
        max_tokens=settings.openai_max_tokens,
        callbacks=callbacks,
    )
