from langchain_google_genai import ChatGoogleGenerativeAI

from src.config import get_settings


def get_llm() -> ChatGoogleGenerativeAI:
    settings = get_settings()
    return ChatGoogleGenerativeAI(
        model=settings.model_name,
        google_api_key=settings.google_api_key,
        temperature=settings.llm_temperature,
        request_timeout=settings.llm_timeout_seconds,
        retries=1,
    )
