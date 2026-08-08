"""Optional RAG retrieval for unstructured medical-knowledge documents."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Protocol

from src.agents.state import RetrievedChunk
from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MedicalKnowledgeRetrieverError(Exception):
    """Raised when optional medical-knowledge RAG cannot be used."""


class MedicalKnowledgeRetriever(Protocol):
    def retrieve(
        self,
        *,
        query: str,
        analyte_id: str,
        limit: int = 3,
    ) -> list[RetrievedChunk]: ...

    def readiness(self) -> dict[str, Any]: ...


class ChromaMedicalKnowledgeRetriever:
    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    def retrieve(
        self,
        *,
        query: str,
        analyte_id: str,
        limit: int = 3,
    ) -> list[RetrievedChunk]:
        result = self.vector_store.search(
            query,
            k=limit,
            filter={"analyte_id": analyte_id},
        )
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        chunks: list[RetrievedChunk] = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}
            raw_sources = metadata.get("sources", "[]") if metadata else "[]"
            try:
                sources = json.loads(raw_sources) if isinstance(raw_sources, str) else raw_sources
            except json.JSONDecodeError:
                sources = [raw_sources]
            chunks.append(
                {
                    "indicator_name": str(metadata.get("indicator", analyte_id)),
                    "text": str(text),
                    "source": str(sources[0]) if sources else "",
                    "sources": [str(source) for source in sources if str(source)],
                    "score": 1.0 - float(distances[index]) if index < len(distances) else 0.0,
                }
            )
        return chunks

    def readiness(self) -> dict[str, Any]:
        return self.vector_store.readiness()


@lru_cache(maxsize=1)
def get_medical_knowledge_retriever() -> MedicalKnowledgeRetriever:
    settings = get_settings()
    if not settings.rag_enabled:
        raise MedicalKnowledgeRetrieverError("medical-knowledge RAG is disabled")
    provider = get_embedding_provider()
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.rag_collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    return ChromaMedicalKnowledgeRetriever(store)


def get_rag_readiness() -> dict[str, Any]:
    settings = get_settings()
    if not settings.rag_enabled:
        return {"status": "disabled", "required": False}
    try:
        return {**get_medical_knowledge_retriever().readiness(), "required": False}
    except Exception as exc:
        logger.error("Optional RAG readiness check failed: %s", exc)
        return {
            "status": "unavailable",
            "required": False,
            "reason": "optional medical-knowledge retrieval is unavailable",
        }
