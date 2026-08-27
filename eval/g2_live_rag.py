"""Evidence-only live RAG sanity check for the current VMEC configuration."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import httpx
from g2_execute import BASE_URL, ROOT, call_analyze, guest_headers, utc_now, write_json

from src.config import get_settings
from src.services.medical_knowledge_retriever import (
    get_medical_knowledge_retriever,
    get_rag_readiness,
)


def main() -> None:
    settings = get_settings()
    readiness = get_rag_readiness()
    retriever = get_medical_knowledge_retriever()
    probes = [
        ("WBC", "wbc", "Ý nghĩa xét nghiệm WBC khi kết quả ở mức normal"),
        (
            "Potassium",
            "potassium",
            "Ý nghĩa xét nghiệm Potassium khi kết quả ở mức normal",
        ),
        (
            "Fasting plasma glucose",
            "fasting_plasma_glucose",
            "Ý nghĩa xét nghiệm Fasting plasma glucose khi kết quả ở mức low",
        ),
    ]
    retrievals = []
    for analyte, analyte_id, query in probes:
        chunks = retriever.retrieve(query=query, analyte_id=analyte_id, limit=3)
        stored = retriever.vector_store.get_collection(create_if_missing=False).get(
            ids=[analyte_id], include=["metadatas"]
        )
        stored_metadatas = stored.get("metadatas") or []
        retrievals.append(
            {
                "analyte": analyte,
                "analyte_id": analyte_id,
                "query": query,
                "chunk_count": len(chunks),
                "stored_document_ids": stored.get("ids") or [],
                "stored_analyte_ids": [metadata.get("analyte_id") for metadata in stored_metadatas],
                "stored_indicators": [metadata.get("indicator") for metadata in stored_metadatas],
                "chunks": [
                    {
                        "text_excerpt": str(chunk.get("text", ""))[:600],
                        "source": chunk.get("source", ""),
                        "sources": chunk.get("sources", []),
                        "score": chunk.get("score"),
                    }
                    for chunk in chunks
                ],
            }
        )

    negative_retrievals = []
    for analyte_id in ("glucose", "kali", "unknown_analyte"):
        chunks = retriever.retrieve(
            query="Unsupported identifier isolation check",
            analyte_id=analyte_id,
            limit=3,
        )
        negative_retrievals.append(
            {
                "analyte_id": analyte_id,
                "chunk_count": len(chunks),
                "returned_analyte_ids": [chunk.get("analyte_id") for chunk in chunks if chunk.get("analyte_id")],
            }
        )

    payload = {
        "patient_age": 35,
        "patient_gender": "male",
        "test_date": "2026-08-15",
        "language": "vi",
        "indicators": [{"name": "WBC", "value": 7.0, "unit": "10^9/L"}],
    }
    with httpx.Client(timeout=120.0) as client:
        api_result = call_analyze(client, guest_headers(client), payload)

    api_body = api_result.get("actual_response") or {}
    artifact = {
        "timestamp": utc_now(),
        "configuration": {
            "rag_enabled": settings.rag_enabled,
            "collection": settings.rag_collection_name,
            "corpus_version": settings.rag_corpus_version,
            "embedding_provider": readiness.get("embedding_provider"),
            "embedding_model": readiness.get("embedding_model"),
        },
        "readiness": readiness,
        "retrievals": retrievals,
        "negative_retrievals": negative_retrievals,
        "api_probe": {
            "endpoint": f"{BASE_URL}/api/v1/analyze",
            "request": payload,
            "request_id": api_result.get("request_id"),
            "status_code": api_result.get("status_code"),
            "timing_record": api_result.get("timing_record"),
            "final_response": api_body,
            "response_schema_exposes_retrieved_contexts": (
                isinstance(api_body, dict) and "retrieved_contexts" in api_body
            ),
        },
        "live_retrieval_verified": (
            settings.rag_enabled
            and readiness.get("status") == "ready"
            and all(item["chunk_count"] > 0 for item in retrievals)
            and all(item["chunk_count"] == 0 for item in negative_retrievals)
        ),
        "limitations": [
            "AnalyzeResponse does not expose the internal retrieved_contexts field.",
            "This sanity artifact verifies one filtered live retrieval per selected analyte; it is not a relevance benchmark.",
            "No RAG_ENABLED=false API A/B run was performed; this artifact is a live retrieval sanity check, not a RAGAS score.",
        ],
    }
    write_json(ROOT / "eval" / "rag" / "live_rag_sanity.json", artifact)
    print(f"CHROMA_STATUS={readiness.get('status')}")
    print(f"CHROMA_DOCUMENT_COUNT={readiness.get('document_count')}")
    for item in retrievals:
        print(f"RAG_{item['analyte_id'].upper()}_CHUNKS={item['chunk_count']}")
    print(f"API_STATUS={api_result.get('status_code')}")
    print(f"LIVE_RAG_RETRIEVAL_VERIFIED={str(artifact['live_retrieval_verified']).upper()}")


if __name__ == "__main__":
    main()
