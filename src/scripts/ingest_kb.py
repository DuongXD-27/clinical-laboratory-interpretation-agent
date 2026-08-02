import json
import logging
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.services.vector_store import get_vector_store

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
        indicator_id = item["id"]

        # Build text representation for embedding
        text_parts = []
        text_parts.append(f"Chỉ số: {item.get('display_name', '')} ({item.get('indicator', '')} - {item.get('vietnamese_name', '')})")
        text_parts.append(f"Giải thích cơ bản: {item.get('simple_explanation', '')}")

        if "high_meaning" in item:
            text_parts.append(f"Ý nghĩa khi tăng cao: {item.get('high_meaning')}")
        if "low_meaning" in item:
            text_parts.append(f"Ý nghĩa khi giảm thấp: {item.get('low_meaning')}")

        full_text = "\n".join(text_parts)

        # Metadata
        meta = {
            "indicator": item.get("indicator", ""),
            "id": indicator_id
        }
        if "sources" in item:
            meta["sources"] = json.dumps(item["sources"], ensure_ascii=False)

        texts.append(full_text)
        metadatas.append(meta)
        ids.append(indicator_id)

    logger.info(f"Ingesting {len(texts)} documents into ChromaDB...")
    store = get_vector_store()

    try:
        store.add_documents(texts=texts, metadatas=metadatas, ids=ids)
        logger.info("Ingestion complete.")
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")

if __name__ == "__main__":
    ingest()
