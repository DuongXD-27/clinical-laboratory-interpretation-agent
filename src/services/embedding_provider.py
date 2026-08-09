"""Embedding provider abstraction for optional medical-knowledge RAG."""

from __future__ import annotations

from functools import lru_cache
from typing import Protocol, runtime_checkable

from langchain_openai import OpenAIEmbeddings

from src.config import get_settings


class EmbeddingProviderError(Exception):
    """Raised when the configured external embedding provider is unavailable."""


@runtime_checkable
class EmbeddingProvider(Protocol):
    provider_name: str
    model_name: str
    dimension: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class OpenAIEmbeddingProvider:
    provider_name = "openai"

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        dimension: int,
        timeout_seconds: float,
    ) -> None:
        if not api_key:
            raise EmbeddingProviderError("OPENAI_API_KEY is required for OpenAI embeddings")
        self.model_name = model_name
        self.dimension = dimension
        self._client = OpenAIEmbeddings(
            api_key=api_key,
            model=model_name,
            dimensions=dimension,
            timeout=timeout_seconds,
            max_retries=1,
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._client.embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._client.embed_query(text)


@lru_cache(maxsize=1)
def get_embedding_provider() -> EmbeddingProvider:
    settings = get_settings()
    if settings.embedding_provider == "disabled":
        raise EmbeddingProviderError("embedding provider is disabled")
    if settings.embedding_provider == "openai":
        return OpenAIEmbeddingProvider(
            api_key=settings.openai_api_key,
            model_name=settings.embedding_model_name,
            dimension=settings.embedding_dimension,
            timeout_seconds=settings.embedding_timeout_seconds,
        )
    raise EmbeddingProviderError(
        f"unsupported embedding provider: {settings.embedding_provider}"
    )
