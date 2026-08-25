"""Dense-only retriever for the App Help knowledge base.

Unlike ``medical_knowledge_retriever.py`` (status/band-aware, tightly
coupled to the 35-locked-analyte schema), App Help queries are stateless
free-text lookups against a small, static markdown corpus — there is no
analyte/status/band concept here, so a single dense (embedding) search
against a dedicated ``VectorStore`` collection is enough.

Fail-closed by design: below ``min_score`` nothing is returned, so callers
must never invent a route/button when the corpus has no real answer for the
question (see yeu-cau-vu.txt AH-10/AH-12 — this is the enforcement point
for that requirement).
"""

from __future__ import annotations

from dataclasses import dataclass

from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore


class AppHelpRetrieverError(Exception):
    """Raised when the App Help RAG is disabled or unavailable."""


@dataclass(frozen=True)
class AppHelpChunkMatch:
    chunk_id: str
    text: str
    feature: str
    role: str
    route: str
    heading: str
    source_file: str
    score: float


@dataclass(frozen=True)
class AppHelpRetrievalResult:
    query: str
    matches: list[AppHelpChunkMatch]

    @property
    def has_match(self) -> bool:
        return len(self.matches) > 0


_KNOWN_ROLE_VALUES = {"patient", "doctor"}


def _matches_role(chunk_role: str, requester_role: str | None) -> bool:
    if requester_role is None or requester_role not in _KNOWN_ROLE_VALUES:
        return True
    allowed = {token.strip() for token in chunk_role.split(",")}
    return requester_role in allowed


class AppHelpRetriever:
    def __init__(self, *, vector_store: VectorStore, min_score: float, top_k: int) -> None:
        self._vector_store = vector_store
        self._min_score = min_score
        self._top_k = top_k

    def retrieve(self, query: str, *, requester_role: str | None = None) -> AppHelpRetrievalResult:
        raw = self._vector_store.search(query, k=self._top_k)
        documents = (raw.get("documents") or [[]])[0]
        metadatas = (raw.get("metadatas") or [[]])[0]
        distances = (raw.get("distances") or [[]])[0]
        ids = (raw.get("ids") or [[]])[0]

        matches: list[AppHelpChunkMatch] = []
        for index, document in enumerate(documents):
            score = 1.0 - float(distances[index]) if index < len(distances) else 0.0
            if score < self._min_score:
                continue
            metadata = metadatas[index] if index < len(metadatas) else {}
            matches.append(
                AppHelpChunkMatch(
                    chunk_id=ids[index] if index < len(ids) else "",
                    text=document,
                    feature=str(metadata.get("feature", "")),
                    role=str(metadata.get("role", "")),
                    route=str(metadata.get("route", "")),
                    heading=str(metadata.get("heading", "")),
                    source_file=str(metadata.get("source_file", "")),
                    score=score,
                )
            )

        # Role is a soft signal, not a hard filter: a doctor asking about a
        # patient-only workflow should still get the real answer (with a
        # role-aware caveat composed by the caller), not silence. Only
        # reorder so same-role content ranks first.
        matches.sort(key=lambda match: (not _matches_role(match.role, requester_role), -match.score))
        return AppHelpRetrievalResult(query=query, matches=matches)


def get_app_help_retriever() -> AppHelpRetriever:
    settings = get_settings()
    if not settings.app_help_rag_enabled:
        raise AppHelpRetrieverError("App Help RAG is disabled")
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.app_help_collection_name,
        corpus_version=settings.app_help_corpus_version,
        embedding_provider=get_embedding_provider(),
    )
    return AppHelpRetriever(
        vector_store=store,
        min_score=settings.app_help_retrieval_min_score,
        top_k=settings.app_help_retrieval_top_k,
    )
