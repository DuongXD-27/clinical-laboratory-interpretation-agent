"""Safely rebuild the derived Chroma collection with current canonical IDs.

The authoritative explanation source is read-only. A temporary collection is
fully embedded and validated before it is swapped into the production
collection name. The old collection is retained under a backup name until
post-rebuild verification is complete.
"""

from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_settings
from src.services.analyte_catalog import get_analyte_catalog
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore


SOURCE = ROOT / "data" / "reference" / "explanations.json"
OUT_DIR = ROOT / "eval" / "rag"


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def source_sha256() -> str:
    return hashlib.sha256(SOURCE.read_bytes()).hexdigest().upper()


def collection_snapshot(collection, *, include_documents: bool = False) -> dict[str, Any]:
    include = ["metadatas"]
    if include_documents:
        include.append("documents")
    raw = collection.get(include=include)
    one = collection.get(limit=1, include=["embeddings"])
    embeddings = one.get("embeddings")
    inspected_dimension = (
        len(embeddings[0])
        if embeddings is not None and len(embeddings)
        else None
    )
    result: dict[str, Any] = {
        "collection": collection.name,
        "document_count": collection.count(),
        "collection_metadata": collection.metadata or {},
        "inspected_embedding_dimension": inspected_dimension,
        "ids": raw.get("ids") or [],
        "metadatas": raw.get("metadatas") or [],
    }
    if include_documents:
        result["documents"] = raw.get("documents") or []
    return result


def build_payload() -> tuple[list[str], list[dict[str, Any]], list[str]]:
    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 9:
        raise RuntimeError(f"expected 9 explanation records, found {len(data) if isinstance(data, list) else 'non-list'}")

    catalog = get_analyte_catalog()
    texts: list[str] = []
    metadatas: list[dict[str, Any]] = []
    ids: list[str] = []
    for item in data:
        indicator = str(item.get("name", "")).strip()
        definition = catalog.resolve(indicator)
        if definition is None or definition.indicator != indicator:
            raise RuntimeError(f"canonical ID is ambiguous or missing for {indicator!r}")

        text_parts = [f"Chỉ số: {indicator}"]
        high_notes = [
            source["high_note"]
            for source in item.get("sources", [])
            if isinstance(source, dict) and source.get("high_note")
        ]
        low_notes = [
            source["low_note"]
            for source in item.get("sources", [])
            if isinstance(source, dict) and source.get("low_note")
        ]
        if high_notes:
            text_parts.append(f"Ý nghĩa khi tăng cao: {high_notes[0]}")
        if low_notes:
            text_parts.append(f"Ý nghĩa khi giảm thấp: {low_notes[0]}")

        sources = [
            str(source["url"])
            for source in item.get("sources", [])
            if isinstance(source, dict) and source.get("url")
        ]
        metadata: dict[str, Any] = {
            "indicator": indicator,
            "analyte_id": definition.analyte_id,
        }
        if sources:
            metadata["sources"] = json.dumps(sources, ensure_ascii=False)

        texts.append("\n".join(text_parts))
        metadatas.append(metadata)
        ids.append(definition.analyte_id)

    if len(ids) != len(set(ids)):
        raise RuntimeError(f"duplicate canonical document IDs: {ids}")
    return texts, metadatas, ids


def main() -> None:
    settings = get_settings()
    provider = get_embedding_provider()
    collection_name = settings.rag_collection_name
    temp_name = f"{collection_name}__canonical_rebuild_tmp"
    backup_name = f"{collection_name}__pre_canonical_fix_backup"

    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    client = store._client
    existing_names = {collection.name for collection in client.list_collections()}
    if collection_name not in existing_names:
        raise RuntimeError(f"source collection {collection_name!r} does not exist")
    conflicts = {temp_name, backup_name} & existing_names
    if conflicts:
        raise RuntimeError(f"refusing to overwrite rebuild collections: {sorted(conflicts)}")

    original = client.get_collection(name=collection_name)
    before = {
        "captured_at": now(),
        "source_file": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": source_sha256(),
        "configured_embedding_provider": provider.provider_name,
        "configured_embedding_model": provider.model_name,
        "configured_embedding_dimension": provider.dimension,
        "openai_api_key_available": bool(settings.openai_api_key.strip()),
        "state": collection_snapshot(original),
    }
    write_json(OUT_DIR / "canonical_reconciliation_before.json", before)

    texts, metadatas, ids = build_payload()
    temp_store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=temp_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    try:
        temp_store.add_documents(texts=texts, metadatas=metadatas, ids=ids)
    except Exception as exc:
        write_json(
            OUT_DIR / "canonical_reconciliation_failure.json",
            {
                "failed_at": now(),
                "phase": "temporary_collection_embedding",
                "embedding_api_items_requested": len(texts),
                "embedding_failures": len(texts),
                "reason": str(exc),
                "original_collection_preserved": True,
            },
        )
        raise

    temp = client.get_collection(name=temp_name)
    temp_state = collection_snapshot(temp, include_documents=True)
    if temp_state["document_count"] != 9:
        raise RuntimeError(f"temporary rebuild count changed unexpectedly: {temp_state['document_count']}")
    if set(temp_state["ids"]) != set(ids):
        raise RuntimeError(f"temporary rebuild IDs differ: {temp_state['ids']} vs {ids}")
    if temp_state["inspected_embedding_dimension"] != provider.dimension:
        raise RuntimeError(
            "temporary rebuild embedding dimension differs: "
            f"{temp_state['inspected_embedding_dimension']} vs {provider.dimension}"
        )

    original.modify(name=backup_name)
    try:
        temp.modify(name=collection_name)
    except Exception:
        client.get_collection(name=backup_name).modify(name=collection_name)
        raise

    rebuilt = client.get_collection(name=collection_name)
    after_state = collection_snapshot(rebuilt, include_documents=True)
    if after_state["document_count"] != 9 or set(after_state["ids"]) != set(ids):
        failed_name = f"{collection_name}__failed_swap"
        rebuilt.modify(name=failed_name)
        client.get_collection(name=backup_name).modify(name=collection_name)
        raise RuntimeError("post-swap validation failed; original collection restored")

    after = {
        "captured_at": now(),
        "source_file": str(SOURCE.relative_to(ROOT)).replace("\\", "/"),
        "source_sha256": source_sha256(),
        "embedding_provider": provider.provider_name,
        "embedding_model": provider.model_name,
        "embedding_dimension": provider.dimension,
        "embedding_api_items_generated": len(texts),
        "embedding_failures": 0,
        "expected_ids": ids,
        "backup_collection": backup_name,
        "state": after_state,
    }
    write_json(OUT_DIR / "canonical_reconciliation_after.json", after)
    print(f"FIX_METHOD=REBUILD_INDEX")
    print(f"EMBEDDING_API_ITEMS_GENERATED={len(texts)}")
    print("EMBEDDING_FAILURES=0")
    print(f"CHROMA_DOCUMENT_COUNT_BEFORE={before['state']['document_count']}")
    print(f"CHROMA_DOCUMENT_COUNT_AFTER={after_state['document_count']}")
    print("POST_REBUILD_IDS=" + ",".join(after_state["ids"]))
    print(f"BACKUP_COLLECTION={backup_name}")


if __name__ == "__main__":
    main()
