"""Chroma vector repository with explicit embedding compatibility metadata."""

from __future__ import annotations

import logging
from typing import Any

import chromadb
from chromadb.config import Settings as ChromaSettings
from chromadb.errors import NotFoundError

from src.services.embedding_provider import EmbeddingProvider

logger = logging.getLogger(__name__)

COLLECTION_SCHEMA_VERSION = "2"


class VectorStoreError(Exception):
    """Raised when vector storage, embeddings or collection metadata are unsafe."""


class VectorStore:
    def __init__(
        self,
        *,
        persist_dir: str,
        collection_name: str,
        corpus_version: str,
        embedding_provider: EmbeddingProvider,
    ) -> None:
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self.corpus_version = corpus_version
        self.embedding_provider = embedding_provider
        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise VectorStoreError(
                f"cannot initialize ChromaDB at '{persist_dir}': {exc}"
            ) from exc

    @property
    def expected_metadata(self) -> dict[str, str | int]:
        return {
            "hnsw:space": "cosine",
            "schema_version": COLLECTION_SCHEMA_VERSION,
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimension": self.embedding_provider.dimension,
            "corpus_version": self.corpus_version,
        }

    def get_collection(self, *, create_if_missing: bool = True):
        try:
            collection = self._client.get_collection(name=self.collection_name)
        except NotFoundError:
            if not create_if_missing:
                raise VectorStoreError(
                    f"collection '{self.collection_name}' does not exist; run the ingestion job first"
                ) from None
            try:
                collection = self._client.create_collection(
                    name=self.collection_name,
                    metadata=self.expected_metadata,
                )
            except Exception as exc:
                raise VectorStoreError(
                    f"cannot create collection '{self.collection_name}': {exc}"
                ) from exc
        except Exception as exc:
            raise VectorStoreError(
                f"cannot get collection '{self.collection_name}': {exc}"
            ) from exc
        self._validate_collection_metadata(collection.metadata or {})
        return collection

    def _validate_collection_metadata(self, actual: dict[str, Any]) -> None:
        mismatches = {
            key: {"expected": expected, "actual": actual.get(key)}
            for key, expected in self.expected_metadata.items()
            if actual.get(key) != expected
        }
        if mismatches:
            details = ", ".join(
                f"{key}={values['actual']!r} (expected {values['expected']!r})"
                for key, values in mismatches.items()
            )
            raise VectorStoreError(
                f"collection '{self.collection_name}' metadata mismatch: {details}. "
                "Create and ingest a new versioned collection; do not mix embeddings."
            )

    def add_documents(
        self,
        texts: list[str],
        metadatas: list[dict[str, Any]],
        ids: list[str],
    ) -> None:
        if not (len(texts) == len(metadatas) == len(ids)):
            raise VectorStoreError(
                "texts, metadatas and ids must have the same length: "
                f"{len(texts)}, {len(metadatas)}, {len(ids)}"
            )
        collection = self.get_collection()
        try:
            embeddings = self.embedding_provider.embed_documents(texts)
        except Exception as exc:
            logger.exception("Failed to embed %d medical documents", len(texts))
            raise VectorStoreError(f"document embedding failed: {exc}") from exc
        self._validate_embedding_dimensions(embeddings)
        try:
            collection.upsert(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids,
            )
        except Exception as exc:
            logger.exception("Failed to write %d embeddings to ChromaDB", len(texts))
            raise VectorStoreError(f"cannot write embeddings to ChromaDB: {exc}") from exc

    def get_by_metadata(
        self,
        *,
        filter: dict[str, Any],
        limit: int | None = None,
        include_embeddings: bool = False,
    ) -> dict[str, Any]:
        """Deterministic metadata lookup without embedding a query.

        Returns documents/metadatas matching the metadata filter, ordered by
        Chroma's internal ordering. Used by the metadata-prong of the
        status-aware retriever where relevance is already decided by
        structured status, so no semantic search is required.

        ``include_embeddings`` returns each chunk's embedding as stored at
        ingest time (no extra embedding call), so callers can cross-check a
        deterministic metadata match against actual content similarity
        instead of trusting the label alone.
        """
        collection = self.get_collection(create_if_missing=False)
        if collection.count() == 0:
            return {"documents": [], "metadatas": [], "ids": [], "embeddings": []}
        include = ["documents", "metadatas"]
        if include_embeddings:
            include.append("embeddings")
        try:
            result = collection.get(
                where=filter,
                limit=limit,
                include=include,
            )
        except Exception as exc:
            logger.exception("Failed to fetch ChromaDB documents by metadata")
            raise VectorStoreError(f"cannot fetch ChromaDB documents by metadata: {exc}") from exc
        raw_embeddings = result.get("embeddings") if include_embeddings else None
        return {
            "documents": list(result.get("documents") or []),
            "metadatas": list(result.get("metadatas") or []),
            "ids": list(result.get("ids") or []),
            "embeddings": (
                [[float(value) for value in embedding] for embedding in raw_embeddings]
                if raw_embeddings is not None
                else []
            ),
        }

    def search(
        self,
        query: str,
        *,
        k: int = 5,
        filter: dict[str, Any] | None = None,
        query_embedding: list[float] | None = None,
    ) -> dict[str, Any]:
        """Semantic search. Pass a precomputed ``query_embedding`` to avoid
        re-embedding the same query text (e.g. when a caller already embedded
        it to cross-check other candidates); otherwise ``query`` is embedded
        here."""
        collection = self.get_collection(create_if_missing=False)
        if collection.count() == 0:
            return {
                "documents": [[]],
                "metadatas": [[]],
                "distances": [[]],
                "ids": [[]],
            }
        if query_embedding is None:
            try:
                query_embedding = self.embedding_provider.embed_query(query)
            except Exception as exc:
                logger.exception("Failed to embed medical query")
                raise VectorStoreError(f"query embedding failed: {exc}") from exc
        self._validate_embedding_dimensions([query_embedding])
        try:
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=min(k, collection.count()),
                where=filter,
            )
        except Exception as exc:
            logger.exception("Failed to query ChromaDB")
            raise VectorStoreError(f"cannot query ChromaDB: {exc}") from exc

    def readiness(self) -> dict[str, Any]:
        collection = self.get_collection(create_if_missing=False)
        return {
            "status": "ready" if collection.count() else "empty",
            "collection": self.collection_name,
            "document_count": collection.count(),
            "embedding_provider": self.embedding_provider.provider_name,
            "embedding_model": self.embedding_provider.model_name,
            "embedding_dimension": self.embedding_provider.dimension,
            "corpus_version": self.corpus_version,
        }

    def _validate_embedding_dimensions(self, embeddings: list[list[float]]) -> None:
        invalid = [len(embedding) for embedding in embeddings if len(embedding) != self.embedding_provider.dimension]
        if invalid:
            raise VectorStoreError(
                "embedding provider returned an unexpected dimension: "
                f"{invalid[0]} (expected {self.embedding_provider.dimension})"
            )

    def delete_collection(self) -> None:
        try:
            self._client.delete_collection(self.collection_name)
        except ValueError:
            pass
