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

    note_labels = {
        "description": "Giải thích cơ bản",
        "high_note": "Ý nghĩa khi tăng cao",
        "low_note": "Ý nghĩa khi giảm thấp",
        "critical_high_note": "Nguy kịch khi tăng cao",
        "critical_low_note": "Nguy kịch khi giảm thấp",
    }

    for item in data:
        indicator = item.get("name", "")
        # Derive stable id from name (matches analyte_catalog.py logic)
        indicator_id = indicator.lower().replace("-", "_").replace(" ", "_")

        for source_index, source in enumerate(item.get("sources", [])):
            if not isinstance(source, dict):
                continue
            url = str(source.get("url", "")).strip()
            for note_type, label in note_labels.items():
                note = str(source.get(note_type, "") or "").strip()
                if not note:
                    continue
                text_parts = [f"Chỉ số: {indicator}"]
                if item.get("metric"):
                    text_parts.append(f"Đơn vị: {item['metric']}")
                text_parts.append(f"{label}: {note}")
                full_text = "\n".join(text_parts)

                meta = {
                    "indicator": indicator,
                    "analyte_id": indicator_id,
                    "note_type": note_type,
                }
                if url:
                    meta["sources"] = json.dumps([url], ensure_ascii=False)

                doc_id = f"{indicator_id}::{note_type}::{source_index}"
                texts.append(full_text)
                metadatas.append(meta)
                ids.append(doc_id)

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
