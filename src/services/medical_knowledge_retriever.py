"""Optional RAG retrieval for unstructured medical-knowledge documents.

Implements status-aware selective retrieval: a deterministic metadata-prong
(driven by the already-classified structured status) is fused with a dense
semantic prong, then a relevance gate drops low-confidence chunks so the
pipeline falls back to the curated explanation when retrieval is weak.

Design decisions after the RAG architecture review:
- No fuzzy content-dedup. The previous containment-based dedup could not
  reliably separate "same idea, different words" from "different causes sharing
  a prefix", so it risked dropping distinct medical content. Only exact
  text-level dedup is applied during fusion.
- Metadata chunks are scored with a length taper AND a semantic cross-check
  (cosine similarity between the chunk's stored embedding and the query
  embedding) so a chunk that merely carries the right label but is long,
  off-topic or low-quality does not keep the deterministic score ceiling.
  Label match alone is no longer trusted as a proxy for content quality.
- RETRIEVAL_MIN_SCORE=0.8 is evidence-based, not a guess. The real curated
  corpus alone can't prove a value (every genuine candidate scores >= 0.76,
  so the gate never binds on it — see eval/rag/retrieval_param_sweep.py).
  Adversarial testing across 3 domains (eval/rag/adversarial_threshold_test.py)
  found a real, reproducible boundary: genuine content floor 0.807, and
  synthetic junk consistently splits into a "catchable" band topping out at
  0.794 (off-topic, wrong-indicator, mislabeled, spam, OCR-garbage, mixed
  content) and a "structurally uncatchable" band starting at 0.820
  (keyword-stuffed and confidently-wrong-but-fluent text — these score
  *above* the genuine floor, so no threshold value can catch them without
  also rejecting real content). 0.8 sits in the proven clean-separation
  window (0.794, 0.807): zero genuine-content loss, maximum catchable-junk
  rejection. See docs/audit/evidence/retrieval-min-score-evidence.md for the
  full write-up, including why the uncatchable band is not a tuning gap —
  it's why GENERATION_SAFETY_CONTRACT + MedicalSafetyValidator downstream
  exist: a relevance-similarity gate can never substitute for a factuality/
  safety check. Re-run the adversarial script whenever the knowledge base
  grows or changes provider/model, since the boundary is corpus- and
  embedding-model-specific.
- top_k (default 3): primary_hit_rate@1 is 1.0 at every tested value on the
  real corpus and larger top_k only adds context chars with no accuracy
  gain (eval/rag/retrieval_param_sweep.md) — kept at 3.
- Fusion ranking (`_fuse`) sorts by semantic score first, and only falls
  back to the status-derived note-type tier as a tie-break within a 0.02
  score bucket. Golden Set V1 (eval/full_system_v1) found the previous
  tier-first ordering let a merely status-matching `description`/`high_note`
  chunk outrank a `limitation_note`/`preanalytic_note` chunk the query
  embedding scored higher — the query embedding already generalizes across
  how the question is phrased, so trusting score first (instead of adding a
  keyword-based intent detector) fixes this without a brittle keyword list.
  The 0.02 bucket width comes from the RETRIEVAL_MIN_SCORE score geometry
  above (genuine floor 0.807 vs. closest catchable-junk ceiling 0.794, a
  ~0.013 gap): wide enough to still break genuine near-ties, narrow enough
  that a real relevance gap is never masked by the tier.
"""

from __future__ import annotations

import json
import logging
import unicodedata
from functools import lru_cache
from typing import Any, Protocol

from src.agents.state import RetrievedChunk
from src.config import get_settings
from src.services.embedding_provider import get_embedding_provider
from src.services.vector_store import VectorStore

logger = logging.getLogger(__name__)


class MedicalKnowledgeRetrieverError(Exception):
    """Raised when optional medical-knowledge RAG cannot be used."""


class MedicalKnowledgeRetriever(Protocol):
    def retrieve(
        self,
        *,
        query: str,
        analyte_id: str,
        status: str = "unknown",
        band_id: str | None = None,
        critical_status: str | None = None,
        limit: int = 3,
    ) -> list[RetrievedChunk]: ...

    def readiness(self) -> dict[str, Any]: ...


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).strip()


def _cosine_similarity(a: list[float], b: list[float]) -> float:
    """Cosine similarity, matching the collection's `hnsw:space: cosine`
    convention so this is directly comparable to the dense-prong's
    `1 - distance` score."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(y * y for y in b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return max(0.0, dot / (norm_a * norm_b))


class ChromaMedicalKnowledgeRetriever:
    def __init__(self, vector_store: VectorStore) -> None:
        self.vector_store = vector_store

    def _status_query(self, query: str, status: str, critical_status: str | None) -> str:
        crit = str(critical_status or "").lower().strip()
        stat = str(status or "").lower().strip()
        if crit == "critical_high" or stat == "high":
            return f"{query}. Khi kết quả tăng cao, ý nghĩa và nguyên nhân là gì?"
        if crit == "critical_low" or stat == "low":
            return f"{query}. Khi kết quả giảm thấp, ý nghĩa và nguyên nhân là gì?"
        return f"{query}. Giải thích chung về ý nghĩa của chỉ số này."

    def _metadata_chunk(
        self,
        text: str,
        metadata: dict[str, Any],
        *,
        analyte_id: str,
        score: float,
        chunk_id: str = "",
    ) -> RetrievedChunk:
        raw_sources = metadata.get("sources", "[]")
        try:
            sources = json.loads(raw_sources) if isinstance(raw_sources, str) else raw_sources
        except json.JSONDecodeError:
            sources = [raw_sources] if raw_sources else []
        sources = [str(source) for source in sources if str(source)]
        return {
            "indicator_name": str(metadata.get("indicator", analyte_id)),
            "chunk_id": str(chunk_id or metadata.get("chunk_id") or ""),
            "text": str(text),
            "source": str(sources[0]) if sources else "",
            "sources": sources,
            "score": score,
            "note_type": str(metadata.get("note_type", "")),
            "source_id": str(metadata.get("source_id", "")),
            "source_title": str(metadata.get("source_title", "")),
            "organization": str(metadata.get("organization", "")),
            "source_url": str(metadata.get("source_url", "")),
            "source_section": str(metadata.get("source_section", "")),
        }

    def _metadata_score(
        self,
        text: str,
        *,
        min_chunk_length: int,
        chunk_embedding: list[float] | None = None,
        query_embedding: list[float] | None = None,
    ) -> float:
        """Length-tapered ceiling, capped by semantic relevance to the query.

        Length alone only catches chunks too thin to carry real content; it
        says nothing about whether a long, correctly-labeled chunk actually
        answers the query. The label match is a deterministic hint, not proof
        of quality, so the final score is the *minimum* of the length ceiling
        and the cosine similarity between the chunk's stored embedding and
        the query embedding (same scale as the dense-prong's `1 - distance`
        score) — a long but off-topic/low-quality chunk gets capped down to
        its real semantic relevance instead of keeping the full ceiling.
        When embeddings are unavailable, falls back to the length ceiling
        alone (graceful degradation, not silent failure).
        """
        length = len(_normalized_text(text))
        if length >= min_chunk_length * 2:
            length_ceiling = 1.0
        else:
            span = max(1, min_chunk_length)
            length_ceiling = 0.9 + 0.1 * (length - min_chunk_length) / span

        if chunk_embedding is None or query_embedding is None:
            return length_ceiling
        semantic_score = _cosine_similarity(chunk_embedding, query_embedding)
        return min(length_ceiling, semantic_score)

    def _metadata_prong(
        self,
        *,
        analyte_id: str,
        min_chunk_length: int,
        query_embedding: list[float] | None,
        allowed_note_types: list[str],
        prohibited_notes: set[str],
        clean_bid: str | None,
    ) -> list[RetrievedChunk]:
        try:
            result = self.vector_store.get_by_metadata(
                filter={
                    "$and": [
                        {"analyte_id": analyte_id},
                        {"note_type": {"$in": allowed_note_types}},
                    ]
                },
                include_embeddings=query_embedding is not None,
            )
        except Exception as exc:
            logger.error("Metadata-prong retrieval failed for %s: %s", analyte_id, exc)
            return []
        documents = result.get("documents") or []
        metadatas = result.get("metadatas") or []
        embeddings = result.get("embeddings") or []
        ids = result.get("ids") or []
        chunks: list[RetrievedChunk] = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}

            note_type = str(metadata.get("note_type") or "").strip()
            chunk_band_id = str(metadata.get("band_id") or "").strip() or None

            # 1. Enforce critical decoupling
            if note_type in prohibited_notes:
                continue

            # 2. If filtering for specific band, reject other band notes
            if clean_bid and note_type == "band_note" and chunk_band_id != clean_bid:
                continue

            text = str(text)
            if len(_normalized_text(text)) < min_chunk_length:
                continue
            chunk_embedding = embeddings[index] if index < len(embeddings) else None
            # GRQ-004 Fix 1 (scoped label trust): when clean_bid is set it was
            # resolved deterministically from authoritative reference bounds,
            # so an exact note_type+band_id metadata match is a deterministic
            # hit, not an embedding coincidence. Such chunks keep the length
            # ceiling WITHOUT the semantic cap. The cap stays fully in force
            # for every other chunk, so off-topic or low-quality content still
            # cannot ride a correct label past the relevance gate.
            exact_deterministic_band = bool(clean_bid) and note_type == "band_note"
            chunks.append(
                self._metadata_chunk(
                    text,
                    metadata,
                    analyte_id=analyte_id,
                    score=self._metadata_score(
                        text,
                        min_chunk_length=min_chunk_length,
                        chunk_embedding=None if exact_deterministic_band else chunk_embedding,
                        query_embedding=query_embedding,
                    ),
                    chunk_id=str(ids[index]) if index < len(ids) else "",
                )
            )
        return chunks

    def _dense_prong(
        self,
        *,
        status_query: str,
        query_embedding: list[float] | None,
        analyte_id: str,
        k: int,
        allowed_note_types: list[str],
        prohibited_notes: set[str],
        clean_bid: str | None,
    ) -> list[RetrievedChunk]:
        try:
            result = self.vector_store.search(
                status_query,
                k=k,
                filter={
                    "$and": [
                        {"analyte_id": analyte_id},
                        {"note_type": {"$in": allowed_note_types}},
                    ]
                },
                query_embedding=query_embedding,
            )
        except Exception as exc:
            logger.error("Dense-prong retrieval failed for %s: %s", analyte_id, exc)
            return []
        documents = (result.get("documents") or [[]])[0]
        metadatas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]
        ids = (result.get("ids") or [[]])[0]
        chunks: list[RetrievedChunk] = []
        for index, text in enumerate(documents):
            metadata = metadatas[index] if index < len(metadatas) else {}

            note_type = str(metadata.get("note_type") or "").strip()
            chunk_band_id = str(metadata.get("band_id") or "").strip() or None

            # 1. Enforce critical decoupling
            if note_type in prohibited_notes:
                continue

            # 2. If filtering for specific band, reject other band notes
            if clean_bid and note_type == "band_note" and chunk_band_id != clean_bid:
                continue

            score = 1.0 - float(distances[index]) if index < len(distances) else 0.0
            chunks.append(
                self._metadata_chunk(
                    text,
                    metadata,
                    analyte_id=analyte_id,
                    score=score,
                    chunk_id=str(ids[index]) if index < len(ids) else "",
                )
            )
        return chunks

    def _fuse(
        self,
        candidates: list[RetrievedChunk],
        *,
        primary_note: str,
        limit: int,
        min_score: float,
        min_chunk_length: int,
    ) -> list[RetrievedChunk]:
        if not candidates:
            return []

        # Exact text-level dedup only, keeping the best score. Fuzzy
        # content-dedup is intentionally omitted (see module docstring).
        by_text: dict[str, RetrievedChunk] = {}
        for chunk in candidates:
            text = str(chunk.get("text", ""))
            if not text:
                continue
            # Thin chunks carry too little content to ground the LLM safely;
            # drop them regardless of which prong produced them.
            if len(_normalized_text(text)) < min_chunk_length:
                continue
            existing = by_text.get(text)
            if existing is None or float(chunk.get("score", 0.0)) > float(existing.get("score", 0.0)):
                by_text[text] = chunk

        # Relevance gate: drop weak hits regardless of prong.
        passed = [chunk for chunk in by_text.values() if float(chunk.get("score", 0.0)) >= min_score]
        if not passed:
            return []

        # Rank by semantic score FIRST, note-type tier only as a tie-break.
        #
        # `primary_note` is derived purely from the deterministic clinical
        # status (normal -> description, high -> high_note, ...); it carries
        # no signal about what the user's question actually asks for. Giving
        # it priority over `score` used to let a merely status-matching
        # `description`/`high_note` chunk outrank a `limitation_note` or
        # `preanalytic_note` chunk that the query embedding shows is the
        # far better semantic match (e.g. "xét nghiệm này có hạn chế gì,
        # cần chuẩn bị gì trước khi lấy máu?") — the query embedding already
        # generalizes across phrasing, so trusting it more fixes this without
        # a brittle keyword list.
        #
        # The bucket width below (0.02) is chosen from the score geometry
        # already documented for RETRIEVAL_MIN_SCORE: genuine-content floor
        # is 0.807 and the closest catchable-junk ceiling is 0.794, a ~0.013
        # gap. 0.02 keeps the tier tie-break active only when two chunks are
        # closer than that natural corpus gap (i.e. genuinely tied), while
        # anything wider is treated as a real relevance difference and score
        # wins outright. Re-validate with eval/rag/retrieval_param_sweep.py
        # style analysis if the corpus or embedding model changes.
        _TIER_TIE_BUCKET = 0.02
        base_note = primary_note.replace("critical_", "") if primary_note.startswith("critical_") else None
        passed.sort(
            key=lambda chunk: (
                -round(float(chunk.get("score", 0.0)) / _TIER_TIE_BUCKET),
                0
                if str(chunk.get("note_type", "")) == primary_note
                else (1 if base_note and str(chunk.get("note_type", "")) == base_note else 2),
                -float(chunk.get("score", 0.0)),
                -len(_normalized_text(str(chunk.get("text", "")))),
            )
        )

        selected: list[RetrievedChunk] = []
        seen_sources: set[str] = set()
        for chunk in passed:
            source = str(chunk.get("source", ""))
            if source and source in seen_sources:
                continue
            selected.append(chunk)
            if source:
                seen_sources.add(source)
            if len(selected) >= limit:
                break

        if len(selected) < limit:
            for chunk in passed:
                if chunk in selected:
                    continue
                selected.append(chunk)
                if len(selected) >= limit:
                    break
        return selected

    def retrieve(
        self,
        *,
        query: str,
        analyte_id: str,
        status: str = "unknown",
        band_id: str | None = None,
        critical_status: str | None = None,
        limit: int = 3,
    ) -> list[RetrievedChunk]:
        settings = get_settings()
        status_query = self._status_query(query, status, critical_status)

        norm_status = str(status or "normal").lower().strip()
        norm_crit = str(critical_status or "none").lower().strip()
        clean_bid = str(band_id).strip() if band_id else None

        allowed_note_types: list[str] = []
        primary_note = "description"
        if norm_crit == "critical_high":
            allowed_note_types = [
                "critical_high_note",
                "high_note",
                "description",
                "limitation_note",
                "preanalytic_note",
            ]
            primary_note = "critical_high_note"
        elif norm_crit == "critical_low":
            allowed_note_types = ["critical_low_note", "low_note", "description", "limitation_note", "preanalytic_note"]
            primary_note = "critical_low_note"
        elif clean_bid:
            allowed_note_types = ["band_note", "description", "limitation_note", "preanalytic_note"]
            primary_note = "band_note"
        elif norm_status == "high":
            allowed_note_types = ["high_note", "description", "limitation_note", "preanalytic_note"]
            primary_note = "high_note"
        elif norm_status == "low":
            allowed_note_types = ["low_note", "description", "limitation_note", "preanalytic_note"]
            primary_note = "low_note"
        else:
            allowed_note_types = ["description", "limitation_note", "preanalytic_note"]

        prohibited_notes: set[str] = set()
        if norm_crit not in {"critical_high", "critical_low"}:
            prohibited_notes.add("critical_high_note")
            prohibited_notes.add("critical_low_note")

        # Embed the query once and share it between both prongs: the
        # dense-prong uses it for the actual vector search, and the
        # metadata-prong uses it to cross-check a label match against real
        # content similarity instead of trusting the label alone. If this
        # fails, both prongs degrade gracefully (dense re-embeds internally;
        # metadata falls back to length-only scoring) rather than crashing.
        try:
            query_embedding = self.vector_store.embedding_provider.embed_query(status_query)
        except Exception as exc:
            logger.error("Query embedding failed for %s: %s", analyte_id, exc)
            query_embedding = None

        candidates: list[RetrievedChunk] = []

        if settings.metadata_prong_enabled:
            candidates.extend(
                self._metadata_prong(
                    analyte_id=analyte_id,
                    min_chunk_length=settings.metadata_min_chunk_length,
                    query_embedding=query_embedding,
                    allowed_note_types=allowed_note_types,
                    prohibited_notes=prohibited_notes,
                    clean_bid=clean_bid,
                )
            )

        dense_k = max(limit * 2, len(allowed_note_types))
        candidates.extend(
            self._dense_prong(
                status_query=status_query,
                query_embedding=query_embedding,
                analyte_id=analyte_id,
                k=dense_k,
                allowed_note_types=allowed_note_types,
                prohibited_notes=prohibited_notes,
                clean_bid=clean_bid,
            )
        )

        return self._fuse(
            candidates,
            primary_note=primary_note,
            limit=limit,
            min_score=settings.retrieval_min_score,
            min_chunk_length=settings.metadata_min_chunk_length,
        )

    def readiness(self) -> dict[str, Any]:
        return self.vector_store.readiness()


@lru_cache(maxsize=1)
def get_medical_knowledge_retriever() -> MedicalKnowledgeRetriever:
    settings = get_settings()
    if not settings.rag_enabled:
        raise MedicalKnowledgeRetrieverError("medical-knowledge RAG is disabled")
    provider = get_embedding_provider()
    store = VectorStore(
        persist_dir=settings.chroma_persist_dir,
        collection_name=settings.rag_collection_name,
        corpus_version=settings.rag_corpus_version,
        embedding_provider=provider,
    )
    return ChromaMedicalKnowledgeRetriever(store)


def get_rag_readiness() -> dict[str, Any]:
    settings = get_settings()
    if not settings.rag_enabled:
        return {"status": "disabled", "required": False}
    try:
        return {**get_medical_knowledge_retriever().readiness(), "required": False}
    except Exception as exc:
        logger.error("Optional RAG readiness check failed: %s", exc)
        return {
            "status": "unavailable",
            "required": False,
            "reason": "optional medical-knowledge retrieval is unavailable",
        }
