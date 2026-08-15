import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ingest():
    json_path = Path("data/reference/explanations.json")
    if not json_path.exists():
        logger.error(f"File not found: {json_path}")
        return

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    texts = []
    metadatas = []
    ids = []

    for item in data:
        indicator = item.get("name", "")
        # Derive stable id from name (matches analyte_catalog.py logic)
        indicator_id = indicator.lower().replace("-", "_").replace(" ", "_")

        # Build text representation for embedding
        text_parts = [f"Chỉ số: {indicator}"]

        # Collect descriptions, high/low notes from all sources (new schema)
        descriptions = [
            src["description"]
            for src in item.get("sources", [])
            if isinstance(src, dict) and src.get("description")
        ]
        high_notes = [
            src["high_note"]
            for src in item.get("sources", [])
            if isinstance(src, dict) and src.get("high_note")
        ]
        low_notes = [
            src["low_note"]
            for src in item.get("sources", [])
            if isinstance(src, dict) and src.get("low_note")
        ]

        if descriptions:
            text_parts.append(f"Giải thích cơ bản: {descriptions[0]}")
        if high_notes:
            text_parts.append(f"Ý nghĩa khi tăng cao: {high_notes[0]}")
        if low_notes:
            text_parts.append(f"Ý nghĩa khi giảm thấp: {low_notes[0]}")

        full_text = "\n".join(text_parts)

        # Metadata
        source_urls = [
            src["url"]
            for src in item.get("sources", [])
            if isinstance(src, dict) and src.get("url")
        ]
        meta = {
            "indicator": indicator,
            "analyte_id": indicator_id,
        }
        if source_urls:
            meta["sources"] = json.dumps(source_urls, ensure_ascii=False)

        texts.append(full_text)
        metadatas.append(meta)
        ids.append(indicator_id)

    logger.info(f"Ingesting {len(texts)} documents into ChromaDB...")
    settings = get_settings()
    if not settings.rag_enabled:
        raise RuntimeError("RAG_ENABLED must be true for the ingestion job")
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.rag_collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=get_embedding_provider(),
    )

    try:
        store.add_documents(texts=texts, metadatas=metadatas, ids=ids)
        logger.info("Ingestion complete.")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")

if __name__ == "__main__":
    ingest()
