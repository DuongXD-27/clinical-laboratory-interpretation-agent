"""Retrieval evaluation module for Phase B.

Evaluates:
- Real production MedicalKnowledgeRetriever against 206 frozen retrieval cases
- Recall@1, Recall@3, Recall@5, MRR
- Analyte precision, Note-type precision, Source precision
- Irrelevant chunk contamination / Cross-analyte contamination
- Numeric conflict handling
"""

from __future__ import annotations

import json
import time
from typing import Any

from src.services.analyte_resolver import canonical_analyte_id
from src.services.explanation_grounding import evidence_has_numeric_conflict
from src.services.medical_knowledge_retriever import (
    ChromaMedicalKnowledgeRetriever,
    get_medical_knowledge_retriever,
)


def evaluate_retrieval_case(case: dict[str, Any], retriever=None) -> dict[str, Any]:
    case_id = case["case_id"]
    domain = case.get("domain", "RETRIEVAL")
    analyte = case.get("analyte", "")
    inp = case["input"]
    exp = case["expected"]
    gold_version = case.get("gold_version", "VMEC_GOLDEN_SET_V1_FROZEN_2026-08-29")

    if retriever is None:
        retriever = get_medical_knowledge_retriever()

    query = inp.get("query_template", f"Giải thích chỉ số {analyte}")
    status = inp.get("status", "unknown")
    band_id = inp.get("band_id")
    critical_status = inp.get("critical_status")
    aid = canonical_analyte_id(analyte)

    req_rel = exp.get("REQUIRED_RELEVANT", [])
    acc_sup = exp.get("ACCEPTABLE_SUPPORT", [])
    irrelevant_info = exp.get("IRRELEVANT", {})
    irr_chunks = set(irrelevant_info.get("chunk_ids", []) if isinstance(irrelevant_info, dict) else irrelevant_info)

    started = time.perf_counter()
    passed = False
    primary_failure = None
    secondary_failures = []
    actual: dict[str, Any] = {}
    notes = ""

    try:
        # Retrieve up to 5 chunks using real production retriever
        chunks = retriever.retrieve(
            query=query,
            analyte_id=aid,
            status=status,
            band_id=band_id,
            critical_status=critical_status,
            limit=5,
        )

        retrieved_ids = [c.get("chunk_id", "") for c in chunks]
        retrieved_sources = [c.get("source_id", "") for c in chunks if c.get("source_id")]
        actual["retrieved_chunk_ids"] = retrieved_ids
        actual["retrieved_source_ids"] = retrieved_sources
        actual["retrieved_scores"] = [c.get("score", 0.0) for c in chunks]
        actual["retrieved_note_types"] = [c.get("note_type", "") for c in chunks]

        # Top 3 (standard production limit)
        top3_ids = retrieved_ids[:3]
        top1_ids = retrieved_ids[:1]

        # Metrics calculation
        # Hit@1
        hit_at_1 = bool(top1_ids and top1_ids[0] in req_rel)
        # Recall@1, 3, 5
        found_in_top1 = sum(1 for cid in req_rel if cid in top1_ids)
        found_in_top3 = sum(1 for cid in req_rel if cid in top3_ids)
        found_in_top5 = sum(1 for cid in req_rel if cid in retrieved_ids)

        recall_at_1 = (found_in_top1 / len(req_rel)) if req_rel else 1.0
        recall_at_3 = (found_in_top3 / len(req_rel)) if req_rel else 1.0
        recall_at_5 = (found_in_top5 / len(req_rel)) if req_rel else 1.0

        # MRR
        mrr = 0.0
        for rank, cid in enumerate(retrieved_ids, 1):
            if cid in req_rel:
                mrr = 1.0 / rank
                break

        # Precision metrics
        total_chunks = len(chunks)
        if total_chunks > 0:
            matching_analyte_count = sum(1 for c in chunks if aid in c.get("chunk_id", ""))
            analyte_precision = matching_analyte_count / total_chunks

            req_or_acc = set(req_rel) | set(acc_sup)
            relevant_note_count = sum(1 for cid in retrieved_ids if cid in req_or_acc)
            note_type_precision = relevant_note_count / total_chunks

            source_precision = sum(1 for c in chunks if bool(c.get("source_id") or c.get("source"))) / total_chunks
        else:
            analyte_precision = 0.0
            note_type_precision = 0.0
            source_precision = 0.0

        # Irrelevant contamination check
        contaminated_chunks = [cid for cid in top3_ids if cid in irr_chunks]
        actual["contaminated_chunks"] = contaminated_chunks

        # Conflict check if case has conflict policy
        conflict_policy = exp.get("numeric_conflict_policy")
        has_conflict = False
        if conflict_policy:
            has_conflict = evidence_has_numeric_conflict(chunks)
            actual["numeric_conflict_detected"] = has_conflict

        actual["hit_at_1"] = hit_at_1
        actual["recall_at_1"] = recall_at_1
        actual["recall_at_3"] = recall_at_3
        actual["recall_at_5"] = recall_at_5
        actual["mrr"] = mrr
        actual["analyte_precision"] = analyte_precision
        actual["note_type_precision"] = note_type_precision
        actual["source_precision"] = source_precision

        # Evaluation criteria for PASS:
        # At least one REQUIRED_RELEVANT chunk retrieved in Top 3, and no severe irrelevant contamination
        if found_in_top3 > 0 and len(contaminated_chunks) == 0 and analyte_precision >= 0.8:
            passed = True
        else:
            passed = False
            if len(contaminated_chunks) > 0:
                primary_failure = "RERANK_FAIL"
                notes = f"Irrelevant chunks contaminated Top-3: {contaminated_chunks}"
            elif analyte_precision < 0.8:
                primary_failure = "RETRIEVAL_FAIL"
                notes = f"Cross-analyte contamination in retrieval: analyte_precision={analyte_precision:.2f}"
            elif found_in_top3 == 0:
                primary_failure = "RETRIEVAL_FAIL"
                notes = f"No REQUIRED_RELEVANT chunk in Top-3 (top-3: {top3_ids}, req: {req_rel})"

    except Exception as exc:
        passed = False
        primary_failure = "SYSTEM_ERROR"
        notes = f"Retriever exception: {exc}"
        actual["error"] = str(exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "case_id": case_id,
        "gold_version": gold_version,
        "domain": domain,
        "layer": "L3_RETRIEVAL_RERANK",
        "input": inp,
        "expected": exp,
        "actual": actual,
        "passed": passed,
        "primary_failure": primary_failure if not passed else None,
        "secondary_failures": secondary_failures,
        "latency_ms": elapsed_ms,
        "llm_calls": 0,
        "sources_expected": req_rel + acc_sup,
        "sources_actual": actual.get("retrieved_chunk_ids", []),
        "notes": notes,
    }
