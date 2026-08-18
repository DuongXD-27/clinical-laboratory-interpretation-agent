# coding=utf-8
import json
import logging
import unicodedata
from collections import defaultdict
from pathlib import Path
from src.config import get_settings
from src.services.context_budget import build_bounded_context
from src.services.embedding_provider import get_embedding_provider
from src.services.medical_knowledge_retriever import ChromaMedicalKnowledgeRetriever
from src.services.vector_store import VectorStore

RESULT_PATH = Path("eval/rag/retrieval_param_sweep.json")
REPORT_PATH = Path("eval/rag/retrieval_param_sweep.md")

MIN_SCORE_CANDIDATES = [0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85]
TOP_K_CANDIDATES = [1, 2, 3, 5]

_QUERY_TEXT = {
    "wbc": "B?ch c?u",
}

_NOTE_TO_STATUS = {
    "high_note": "high",
    "low_note": "low",
    "critical_high_note": "critical_high",
    "critical_low_note": "critical_low",
    "normal_note": "normal",
}

def _analyte_status_pairs(store: VectorStore) -> list[tuple[str, str]]:
    raw = store.get_collection(create_if_missing=False).get(include=["metadatas"])
    by_analyte: dict[str, set[str]] = defaultdict(set)
    for meta in raw.get("metadatas") or []:
        analyte_id = str(meta.get("analyte_id", ""))
        note_type = str(meta.get("note_type", ""))
        band_id = str(meta.get("band_id", ""))
        status = _NOTE_TO_STATUS.get(note_type)
        if band_id:
            status = band_id
        if analyte_id and status:
            by_analyte[analyte_id].add(status)
    pairs = [(analyte, status) for analyte, statuses in sorted(by_analyte.items()) for status in sorted(statuses)]
    return pairs

def get_primary_note(status: str) -> str:
    if "critical" in status:
        return f"{status}_note"
    if status in ["high", "low"]:
        return f"{status}_note"
    if status not in ["normal", "unknown"]:
        return "band_note"
    return "description"

def main() -> None:
    settings = get_settings()
    settings.retrieval_min_score = 0.0
    provider = get_embedding_provider()
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.rag_collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    retriever = ChromaMedicalKnowledgeRetriever(store)
    pairs = _analyte_status_pairs(store)
    max_k = max(TOP_K_CANDIDATES)

    candidates_by_pair: dict[tuple[str, str], list] = {}
    for analyte_id, status in pairs:
        critical_status = status if "critical" in status else None
        band_id = status if status not in ["normal", "low", "high", "critical_high", "critical_low", "unknown"] else None
        
        candidates = retriever.retrieve(
            query=_QUERY_TEXT.get(analyte_id, "Gi?i thích"),
            analyte_id=analyte_id,
            status="normal" if band_id else status,
            critical_status=critical_status,
            band_id=band_id,
            limit=10,
        )
        candidates_by_pair[(analyte_id, status)] = candidates

    sweep_results = []
    for min_score in MIN_SCORE_CANDIDATES:
        for top_k in TOP_K_CANDIDATES:
            fallback_count = 0
            hit_count = 0
            non_empty = 0
            total_chunks = 0
            total_ctx_chars = 0
            for analyte_id, status in pairs:
                chunks = [c for c in candidates_by_pair[(analyte_id, status)] if float(c.get("score", 0.0)) >= min_score][:top_k]
                if not chunks:
                    fallback_count += 1
                    continue
                non_empty += 1
                total_chunks += len(chunks)
                total_ctx_chars += len(build_bounded_context(chunks, max_chars=settings.max_analyzer_context_chars))
                primary_note = get_primary_note(status)
                if str(chunks[0].get("note_type", "")) == primary_note:
                    hit_count += 1

            total = len(pairs)
            sweep_results.append(
                {
                    "min_score": min_score,
                    "top_k": top_k,
                    "fallback_rate": round(fallback_count / total, 3),
                    "primary_hit_rate": round(hit_count / non_empty, 3) if non_empty else None,
                    "avg_chunks": round(total_chunks / non_empty, 2) if non_empty else 0,
                    "avg_context_chars": round(total_ctx_chars / non_empty, 1) if non_empty else 0,
                }
            )

    RESULT_PATH.write_text(json.dumps({"pairs_tested": len(pairs), "results": sweep_results}, indent=2, ensure_ascii=False))

    lines = [
        "# Retrieval parameter sweep (RETRIEVAL_MIN_SCORE x top_k)",
        "",
        f"Analyte/status pairs tested: {len(pairs)} (full curated corpus: {sorted({p[0] for p in pairs})})",
        "",
        "| min_score | top_k | fallback_rate | primary_hit_rate@1 | avg_chunks | avg_context_chars |",
        "|---|---|---|---|---|---|",
    ]
    for row in sweep_results:
        lines.append(
            f"| {row['min_score']} | {row['top_k']} | {row['fallback_rate']} | "
            f"{row['primary_hit_rate']} | {row['avg_chunks']} | {row['avg_context_chars']} |"
        )
    REPORT_PATH.write_text("\n".join(lines) + "\n")
    print(f"Wrote {RESULT_PATH} and {REPORT_PATH}")

if __name__ == "__main__":
    main()

