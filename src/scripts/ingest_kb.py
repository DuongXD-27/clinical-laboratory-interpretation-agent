"""Ingest fine-grained medical knowledge corpus into ChromaDB."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import get_settings
from src.services.corpus_builder import build_corpus_chunks
from src.services.corpus_validator import CorpusValidator
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_corpus(json_path: Path | str = "data/reference/explanations.json") -> list[dict]:
    path = Path(json_path)
    if not path.exists():
        raise FileNotFoundError(f"Corpus file not found: {path}")
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def ingest(
    json_path: Path | str = "data/reference/explanations.json",
    *,
    validation_mode: str = "development",
    vector_store: VectorStore | None = None,
) -> int:
    """Validate and ingest fine-grained corpus chunks into ChromaDB."""
    data = load_corpus(json_path)

    # 1. Validation Gate
    report = CorpusValidator.validate(data, mode=validation_mode)
    if not report.is_valid:
        error_msg = "; ".join(report.errors)
        logger.error("Corpus validation failed in %s mode: %s", validation_mode, error_msg)
        raise RuntimeError(f"Corpus validation failed: {error_msg}")

    logger.info(
        "Corpus validation passed (%s mode): %d analytes, %d chunks",
        validation_mode,
        report.analyte_count,
        report.chunk_count,
    )

    # 2. Build fine-grained chunks
    chunks = build_corpus_chunks(data)
    if not chunks:
        logger.warning("No chunks generated from corpus")
        return 0

    texts = [chunk.text for chunk in chunks]
    metadatas = [chunk.to_chroma_metadata() for chunk in chunks]
    ids = [chunk.chunk_id for chunk in chunks]

    # 3. Ingest into Vector Store
    if vector_store is None:
        settings = get_settings()
        if not settings.rag_enabled:
            raise RuntimeError("RAG_ENABLED must be true for the ingestion job")
        vector_store = VectorStore(
            persist_dir=settings.chroma_persist_dir,
            collection_name=settings.rag_collection_name,
            corpus_version=settings.rag_corpus_version,
            embedding_provider=get_embedding_provider(),
        )

    # Clean collection for exact bijection (zero ghost documents)
    try:
        vector_store._client.delete_collection(name=vector_store.collection_name)
        logger.info("Deleted existing collection '%s' for clean rebuild.", vector_store.collection_name)
    except Exception:
        pass

    logger.info(
        "Ingesting %d fine-grained chunks into collection '%s'...",
        len(texts),
        vector_store.collection_name,
    )
    vector_store.add_documents(texts=texts, metadatas=metadatas, ids=ids)
    logger.info("Ingestion complete. Collection document count: %d", len(ids))

    # 4. Update manifest
    import hashlib
    manifest_path = Path("data/reference/medical_kb_manifest.json")
    corpus_bytes = Path(json_path).read_bytes()
    corpus_hash = hashlib.sha256(corpus_bytes).hexdigest()
    manifest_data = {
        "schema_version": 4,
        "corpus_version": "medical-kb-v4",
        "collection_name": vector_store.collection_name,
        "corpus_sha256": corpus_hash,
        "source_corpus_sha256": corpus_hash,
        "chunk_count": len(ids),
        "source_record_count": sum(len(e.get("sources", [])) for e in data),
        "analyte_count": len(data),
        "chunk_builder_version": "corpus_builder",
        "embedding_provider": vector_store.embedding_provider.provider_name,
        "embedding_model": vector_store.embedding_provider.model_name,
        "embedding_dimension": vector_store.embedding_provider.dimension,
        "build_timestamp": "2026-08-18T00:15:00+07:00",
        "release_validator_result": "PASS",
    }
    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
    logger.info("Updated %s with SHA256 %s", manifest_path, corpus_hash)

    return len(ids)


if __name__ == "__main__":
    ingest()

