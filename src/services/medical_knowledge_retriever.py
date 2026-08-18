"""Status-gated, band-aware and critical-isolated medical knowledge retriever."""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Protocol

from src.agents.state import RetrievedChunk
from src.config import get_settings
from src.services.analyte_resolver import canonical_analyte_id
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
        status: str = "normal",
        band_id: str | None = None,
        critical_status: str | None = None,
        limit: int = 3,
    ) -> list[RetrievedChunk]: ...

    def readiness(self) -> dict[str, Any]: ...


class ChromaMedicalKnowledgeRetriever:
    """Retrieves grounded explanatory notes with strict status and critical decoupling."""

    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    def retrieve(
        self,
        *,
        query: str,
        analyte_id: str,
        status: str = "normal",
        band_id: str | None = None,
        critical_status: str | None = None,
        limit: int = 3,
    ) -> list[RetrievedChunk]:
        clean_aid = canonical_analyte_id(analyte_id)
        if not clean_aid:
            return []

        norm_status = str(status or "normal").lower().strip()
        norm_crit = str(critical_status or "none").lower().strip()
        clean_bid = str(band_id).strip() if band_id else None

        # Build allowed target note priorities based on frozen contract
        allowed_note_types: list[str] = []
        if norm_crit == "critical_high":
            allowed_note_types = ["critical_high_note", "high_note", "description", "limitation_note", "preanalytic_note"]
        elif norm_crit == "critical_low":
            allowed_note_types = ["critical_low_note", "low_note", "description", "limitation_note", "preanalytic_note"]
        elif clean_bid:
            allowed_note_types = ["band_note", "description", "limitation_note", "preanalytic_note"]
        elif norm_status == "high":
            allowed_note_types = ["high_note", "description", "limitation_note", "preanalytic_note"]
        elif norm_status == "low":
            allowed_note_types = ["low_note", "description", "limitation_note", "preanalytic_note"]
        else:
            # normal, unknown, or neutral
            allowed_note_types = ["description", "limitation_note", "preanalytic_note"]

        # ABSOLUTE CRITICAL DECOUPLING:
        # If critical_status is not critical_high/critical_low, critical notes are strictly PROHIBITED.
        prohibited_notes: set[str] = set()
        if norm_crit not in {"critical_high", "critical_low"}:
            prohibited_notes.add("critical_high_note")
            prohibited_notes.add("critical_low_note")

        # Query ChromaDB with analyte_id metadata filter
        try:
            result = self.vector_store.search(
                query,
                k=max(limit * 2, 10),
                filter={"analyte_id": clean_aid},
            )
        except Exception as exc:
            logger.warning("ChromaDB search failed for analyte '%s': %s", clean_aid, exc)
            return []

        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        candidates: list[dict[str, Any]] = []

        for index, text in enumerate(documents):
            meta = metadatas[index] if index < len(metadatas) else {}
            note_type = str(meta.get("note_type") or "").strip()
            chunk_band_id = str(meta.get("band_id") or "").strip() or None

            # 1. Enforce critical decoupling
            if note_type in prohibited_notes:
                continue

            # 2. If filtering for specific band, reject other band notes
            if clean_bid and note_type == "band_note" and chunk_band_id != clean_bid:
                continue

            # 3. Check if note_type is in allowed types
            if note_type and allowed_note_types and note_type not in allowed_note_types:
                continue

            raw_sources = meta.get("sources", "[]") if meta else "[]"
            try:
                sources = json.loads(raw_sources) if isinstance(raw_sources, str) and raw_sources.startswith("[") else []
            except Exception:
                sources = []
            if not sources:
                source_val = str(meta.get("source_url") or meta.get("source_id") or "")
                if source_val:
                    sources = [source_val]

            dist = float(distances[index]) if index < len(distances) else 1.0
            score = 1.0 - dist

            # Compute match priority score
            priority = 999
            if clean_bid and note_type == "band_note" and chunk_band_id == clean_bid:
                priority = 0
            elif norm_crit == "critical_high" and note_type == "critical_high_note":
                priority = 0
            elif norm_crit == "critical_low" and note_type == "critical_low_note":
                priority = 0
            elif norm_status == "high" and note_type == "high_note":
                priority = 1
            elif norm_status == "low" and note_type == "low_note":
                priority = 1
            elif note_type == "description":
                priority = 2
            elif note_type in {"preanalytic_note", "limitation_note"}:
                priority = 3

            candidates.append({
                "chunk": {
                    "indicator_name": str(meta.get("indicator", clean_aid)),
                    "text": str(text),
                    "source": str(sources[0]) if sources else "",
                    "sources": [str(s) for s in sources if str(s)],
                    "score": max(score, 0.0),
                },
                "priority": priority,
                "score": score,
                "note_type": note_type,
            })

        # Sort candidates primarily by status/note priority, then by semantic score
        candidates.sort(key=lambda item: (item["priority"], -item["score"]))

        # Return top_k unique chunks (deduplicated by text)
        retrieved: list[RetrievedChunk] = []
        seen_texts: set[str] = set()
        for cand in candidates:
            chunk_obj = cand["chunk"]
            txt = chunk_obj["text"].strip()
            if txt and txt not in seen_texts:
                seen_texts.add(txt)
                retrieved.append(chunk_obj)
                if len(retrieved) >= limit:
                    break

        return retrieved

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
