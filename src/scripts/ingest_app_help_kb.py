"""Ingest the App Help markdown corpus into its own ChromaDB collection.

Mirrors ``ingest_kb.py``'s validate -> build -> wipe-collection ->
add_documents -> manifest flow, but reads from
``data/app_how_to_use/*.md`` instead of the medical
``data/reference/explanations.json``, and writes into a distinct
collection (``settings.app_help_collection_name``) so it never mixes with
``medical_kb_v4`` (VectorStore hard-fails on collection metadata mismatch,
which is the intended guardrail here — see vector_store.py).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import get_settings
from src.services.app_help_corpus_builder import (
    NON_CORPUS_FILES,
    AppHelpCorpusError,
    build_corpus_chunks,
)
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Case-sensitive, whole-word: these are only real stub markers when written
# in the conventional all-caps style ("TODO", "COMING SOON"). Content that
# merely mentions the English loanword "placeholder" in lowercase (e.g.
# describing a form field's placeholder text) must not be rejected — unlike
# the medical corpus (JSON, no natural-language false positives), this
# corpus is Vietnamese prose mixing English UI terms.
PROHIBITED_PLACEHOLDER_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(term)}\b")
    for term in ("TODO", "TBD", "COMING SOON", "PLACEHOLDER", "LOREM IPSUM")
)


def _validate_no_placeholders(chunks: list) -> None:
    for chunk in chunks:
        for pattern in PROHIBITED_PLACEHOLDER_PATTERNS:
            if pattern.search(chunk.text):
                raise AppHelpCorpusError(
                    f"chunk {chunk.chunk_id!r} contains prohibited placeholder text: {pattern.pattern!r}"
                )


def corpus_sha256(corpus_dir: Path | str) -> str:
    """SHA-256 over every corpus .md file, sorted by name, CRLF-normalized.

    Same rationale as ``ingest_kb.corpus_sha256``: normalize line endings so
    the pin doesn't depend on the checkout machine's autocrlf setting.
    """
    directory = Path(corpus_dir)
    hasher = hashlib.sha256()
    for path in sorted(directory.glob("*.md")):
        if path.name in NON_CORPUS_FILES:
            continue
        hasher.update(path.name.encode("utf-8"))
        hasher.update(path.read_bytes().replace(b"\r\n", b"\n"))
    return hasher.hexdigest()


def _to_chroma_metadata(chunk) -> dict[str, str]:
    return {
        "feature": chunk.feature,
        "role": chunk.role,
        "route": chunk.route,
        "section": chunk.section,
        "heading": chunk.heading,
        "source_file": chunk.source_file,
    }


def ingest(
    corpus_dir: Path | str | None = None,
    *,
    vector_store: VectorStore | None = None,
    manifest_path: Path | str = "data/app_how_to_use/app_help_kb_manifest.json",
) -> int:
    settings = get_settings()
    corpus_dir = Path(corpus_dir or settings.app_help_corpus_dir)

    chunks = build_corpus_chunks(corpus_dir)
    _validate_no_placeholders(chunks)
    logger.info("App Help corpus validation passed: %d chunks from %s", len(chunks), corpus_dir)

    texts = [chunk.text for chunk in chunks]
    metadatas = [_to_chroma_metadata(chunk) for chunk in chunks]
    ids = [chunk.chunk_id for chunk in chunks]

    if vector_store is None:
        if not settings.app_help_rag_enabled:
            raise RuntimeError("APP_HELP_RAG_ENABLED must be true for the ingestion job")
        vector_store = VectorStore(
            persist_dir=settings.chroma_persist_dir,
            collection_name=settings.app_help_collection_name,
            corpus_version=settings.app_help_corpus_version,
            embedding_provider=get_embedding_provider(),
        )

    try:
        vector_store._client.delete_collection(name=vector_store.collection_name)
        logger.info("Deleted existing collection '%s' for clean rebuild.", vector_store.collection_name)
    except Exception:
        pass

    logger.info(
        "Ingesting %d App Help chunks into collection '%s'...",
        len(texts),
        vector_store.collection_name,
    )
    vector_store.add_documents(texts=texts, metadatas=metadatas, ids=ids)
    logger.info("Ingestion complete. Collection document count: %d", len(ids))

    manifest_path = Path(manifest_path)
    corpus_hash = corpus_sha256(corpus_dir)
    manifest_data = {
        "schema_version": 1,
        "corpus_version": settings.app_help_corpus_version,
        "collection_name": vector_store.collection_name,
        "corpus_dir": str(corpus_dir),
        "corpus_sha256": corpus_hash,
        "chunk_count": len(ids),
        "source_file_count": len({chunk.source_file for chunk in chunks}),
        "chunk_builder_version": "app_help_corpus_builder",
        "embedding_provider": vector_store.embedding_provider.provider_name,
        "embedding_model": vector_store.embedding_provider.model_name,
        "embedding_dimension": vector_store.embedding_provider.dimension,
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    logger.info("Updated %s with SHA256 %s", manifest_path, corpus_hash)

    return len(ids)


if __name__ == "__main__":
    ingest()
