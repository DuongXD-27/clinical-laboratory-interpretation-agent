"""Unit tests for the status-aware selective retriever.

Validates the post-review behaviour: deterministic metadata prong with a
length taper, dense-prong competition, exact text-level dedup only (no fuzzy
content-dedup), the relevance gate, and the reviewer's false-positive pair
being preserved so no distinct cause is lost.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.services.medical_knowledge_retriever import (
    ChromaMedicalKnowledgeRetriever,
)

# Default vectors so existing tests (written before the semantic cross-check
# was added) keep their original meaning: every doc's embedding is aligned
# with the default query embedding (cosine similarity 1.0), so the length
# ceiling alone still determines the score unless a test overrides
# `embedding=` on `_doc()` to exercise the semantic cap explicitly.
_ALIGNED = (1.0, 0.0)
_ORTHOGONAL = (0.0, 1.0)


class FakeEmbeddingProvider:
    def __init__(self, query_vector: tuple[float, ...] = _ALIGNED) -> None:
        self.query_vector = list(query_vector)

    def embed_query(self, text: str) -> list[float]:
        return self.query_vector

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.query_vector for _ in texts]


class FakeVectorStore:
    def __init__(self, docs: list[dict]) -> None:
        # docs: list of {"text", "metadata", "embedding"} for all chunks in the collection.
        self._docs = docs
        self._search_ordering: list[str] = []
        self._last_filter: dict | None = None
        self._last_k: int | None = None
        self.embedding_provider = FakeEmbeddingProvider()

    def _matches(self, metadata: dict, filter: dict | None) -> bool:
        if filter is None:
            return True
        if "$and" in filter:
            return all(self._matches(metadata, clause) for clause in filter["$and"])
        for key, expected in filter.items():
            actual = metadata.get(key)
            if isinstance(expected, dict) and "$in" in expected:
                if actual not in expected["$in"]:
                    return False
            elif actual != expected:
                return False
        return True

    def get_by_metadata(self, *, filter, limit=None, include_embeddings=False):
        matched = [
            {"text": doc["text"], "metadata": doc["metadata"], "embedding": doc.get("embedding", list(_ALIGNED))}
            for doc in self._docs
            if self._matches(doc["metadata"], filter)
        ]
        if limit is not None:
            matched = matched[:limit]
        return {
            "documents": [m["text"] for m in matched],
            "metadatas": [m["metadata"] for m in matched],
            "ids": [],
            "embeddings": [m["embedding"] for m in matched] if include_embeddings else [],
        }

    def search(self, query, *, k, filter=None, query_embedding=None):
        # Deterministic fake: return docs matching filter in corpus order,
        # with a fixed cosine distance so scores are predictable.
        self._last_k = k
        matched = [doc for doc in self._docs if self._matches(doc["metadata"], filter)]
        matched = matched[:k]
        return {
            "documents": [[doc["text"] for doc in matched]],
            "metadatas": [[doc["metadata"] for doc in matched]],
            "distances": [[0.2 for _ in matched]],
            "ids": [[]],
        }


def _doc(
    text: str,
    *,
    note_type: str,
    source: str = "https://src.test",
    embedding: tuple[float, ...] = _ALIGNED,
) -> dict:
    return {
        "text": text,
        "metadata": {
            "indicator": "WBC",
            "analyte_id": "wbc",
            "note_type": note_type,
            "sources": f'["{source}"]',
        },
        "embedding": list(embedding),
    }


def _retriever(docs: list[dict]) -> tuple[ChromaMedicalKnowledgeRetriever, FakeVectorStore]:
    store = FakeVectorStore(docs)
    retriever = ChromaMedicalKnowledgeRetriever(store)
    return retriever, store


def _settings_stub(
    monkeypatch,
    *,
    min_score: float = 0.3,
    metadata_prong: bool = True,
    min_chunk_length: int = 30,
):
    settings = SimpleNamespace(
        metadata_prong_enabled=metadata_prong,
        retrieval_min_score=min_score,
        retrieval_top_k=3,
        metadata_min_chunk_length=min_chunk_length,
    )
    monkeypatch.setattr(
        "src.services.medical_knowledge_retriever.get_settings",
        lambda: settings,
    )
    return settings


def test_metadata_prong_returns_status_matching_chunks(monkeypatch):
    _settings_stub(monkeypatch)
    docs = [
        _doc(
            "WBC là viết tắt của White Blood Cell, tức bạch cầu, thành phần quan trọng của hệ miễn dịch",
            note_type="description",
        ),
        _doc(
            "Khi WBC tăng cao hơn mức bình thường, điều này có thể phản ánh bệnh lý viêm nhiễm hoặc bệnh máu ác tính",
            note_type="high_note",
        ),
        _doc("Khi WBC giảm thấp, tình trạng này có thể gặp khi nhiễm virus hoặc suy tủy xương", note_type="low_note"),
    ]
    retriever, store = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    note_types = [chunk["note_type"] for chunk in chunks]
    assert note_types == ["high_note", "description"]
    # Long deterministic metadata chunks keep the full score ceiling.
    assert all(chunk["score"] == 1.0 for chunk in chunks)


def test_low_status_prefers_low_note(monkeypatch):
    _settings_stub(monkeypatch)
    docs = [
        _doc(
            "WBC là viết tắt của White Blood Cell, tức bạch cầu, thành phần quan trọng của hệ miễn dịch",
            note_type="description",
        ),
        _doc(
            "Khi WBC tăng cao hơn mức bình thường, điều này có thể phản ánh bệnh lý viêm nhiễm hoặc bệnh máu ác tính",
            note_type="high_note",
        ),
        _doc("Khi WBC giảm thấp, tình trạng này có thể gặp khi nhiễm virus hoặc suy tủy xương", note_type="low_note"),
    ]
    retriever, _ = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="low",
        limit=2,
    )

    assert [chunk["note_type"] for chunk in chunks] == ["low_note", "description"]


def test_short_metadata_chunks_are_dropped(monkeypatch):
    _settings_stub(monkeypatch, min_chunk_length=30)
    docs = [
        _doc("WBC tăng", note_type="high_note", source="https://a.test"),
        _doc(
            "Khi WBC tăng cao hơn mức bình thường, điều này có thể phản ánh bệnh lý viêm nhiễm hoặc bệnh máu ác tính",
            note_type="high_note",
            source="https://b.test",
        ),
    ]
    retriever, _ = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    # The thin "WBC tăng" chunk is filtered out; only the substantial one stays.
    assert len(chunks) == 1
    assert "WBC tăng" not in [chunk["text"] for chunk in chunks]


def test_dense_rich_chunk_outranks_thin_metadata(monkeypatch):
    _settings_stub(monkeypatch, min_chunk_length=30)
    # Thin-but-valid metadata chunk (~38 chars, within [30, 60)) so its tapered
    # ceiling stays well below 1.0, letting a strong dense hit outrank it.
    thin_metadata = _doc(
        "Khi WBC tăng cao thường do viêm nhiễm",
        note_type="high_note",
        source="https://a.test",
    )
    rich_dense = _doc(
        "Khi WBC tăng cao hơn mức bình thường đồng nghĩa số lượng bạch cầu trong máu tăng. "
        "Điều này có thể phản ánh bệnh lý viêm nhiễm, bệnh máu ác tính hoặc các bệnh về bạch cầu. "
        "Ngoài ra thuốc corticosteroid và hút thuốc lá cũng có thể làm chỉ số này tăng",
        note_type="high_note",
        source="https://b.test",
    )
    retriever, store = _retriever([thin_metadata, rich_dense])
    original_search = store.search

    def fake_search(query, *, k, filter=None, query_embedding=None):
        result = original_search(query, k=k, filter=filter, query_embedding=query_embedding)
        # Dense prong finds the rich chunk at a very high score (distance 0.02).
        result["documents"] = [[rich_dense["text"]]]
        result["metadatas"] = [[rich_dense["metadata"]]]
        result["distances"] = [[0.02]]
        return result

    store.search = fake_search

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    # The dense hit (score 0.98) outranks the thin metadata chunk (< 1.0 ceiling).
    assert chunks[0]["text"] == rich_dense["text"]
    assert chunks[0]["score"] > chunks[1]["score"]


def test_exact_text_dedup_keeps_best_score(monkeypatch):
    _settings_stub(monkeypatch)
    docs = [
        _doc(
            "Khi WBC tăng cao hơn mức bình thường, điều này có thể phản ánh bệnh lý viêm nhiễm hoặc bệnh máu ác tính",
            note_type="high_note",
        ),
        _doc("WBC là gì", note_type="description"),
    ]
    retriever, store = _retriever(docs)
    original_search = store.search

    def fake_search(query, *, k, filter=None, query_embedding=None):
        result = original_search(query, k=k, filter=filter, query_embedding=query_embedding)
        # Make dense prong return the same high_note text at a weak score.
        result["documents"] = [[docs[0]["text"]]]
        result["metadatas"] = [[docs[0]["metadata"]]]
        result["distances"] = [[0.7]]
        return result

    store.search = fake_search

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    by_text = {chunk["text"]: chunk for chunk in chunks}
    # Exact text duplicate is collapsed once; the better (metadata) score wins.
    assert by_text[docs[0]["text"]]["score"] == 1.0


def test_reviewer_false_positive_pair_is_preserved(monkeypatch):
    _settings_stub(monkeypatch)
    # Reviewer's FP pair: two chunks share a long prefix but state DIFFERENT
    # causes. The previous fuzzy dedup collapsed them and lost one cause.
    docs = [
        _doc(
            "Tăng bạch cầu đa nhân trung tính thường do nhiễm trùng vi khuẩn cấp tính",
            note_type="high_note",
            source="https://a.test",
        ),
        _doc(
            "Tăng bạch cầu đa nhân trung tính thường do sử dụng thuốc Corticosteroid",
            note_type="high_note",
            source="https://b.test",
        ),
    ]
    retriever, _ = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=3,
    )

    texts = {chunk["text"] for chunk in chunks}
    # Both distinct causes must survive.
    assert len(texts) == 2
    assert any("nhiễm trùng vi khuẩn" in text for text in texts)
    assert any("Corticosteroid" in text for text in texts)


def test_relevance_gate_drops_weak_dense_chunks(monkeypatch):
    _settings_stub(monkeypatch, min_score=0.5, metadata_prong=False)
    # Dense prong only; metadata prong disabled to exercise the gate purely.
    long_text = "WBC là viết tắt của White Blood Cell, tức bạch cầu, thành phần quan trọng của hệ miễn dịch"
    docs = [_doc(long_text, note_type="description")]
    retriever, store = _retriever(docs)
    store.get_by_metadata = lambda filter=None, include_embeddings=False: {
        "documents": [[]],
        "metadatas": [[]],
        "ids": [[]],
    }
    store.search = lambda query, *, k, filter=None, query_embedding=None: {
        "documents": [[long_text]],
        "metadatas": [[docs[0]["metadata"]]],
        "distances": [[0.8]],
        "ids": [[]],
    }

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    # Distance 0.8 -> score 0.2, below the 0.5 gate -> empty -> fallback.
    assert chunks == []


def test_relevance_gate_passes_sufficient_score(monkeypatch):
    _settings_stub(monkeypatch, min_score=0.5, metadata_prong=False)
    long_text = "WBC là viết tắt của White Blood Cell, tức bạch cầu, thành phần quan trọng của hệ miễn dịch"
    docs = [_doc(long_text, note_type="description")]
    retriever, store = _retriever(docs)
    store.get_by_metadata = lambda filter=None, include_embeddings=False: {
        "documents": [[]],
        "metadatas": [[]],
        "ids": [[]],
    }
    store.search = lambda query, *, k, filter=None, query_embedding=None: {
        "documents": [[long_text]],
        "metadatas": [[docs[0]["metadata"]]],
        "distances": [[0.2]],
        "ids": [[]],
    }

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    assert len(chunks) == 1
    assert chunks[0]["score"] == 0.8


def test_normal_status_only_description(monkeypatch):
    _settings_stub(monkeypatch)
    docs = [
        _doc(
            "WBC là viết tắt của White Blood Cell, tức bạch cầu, thành phần quan trọng của hệ miễn dịch",
            note_type="description",
        ),
        _doc(
            "Khi WBC tăng cao hơn mức bình thường, điều này có thể phản ánh bệnh lý viêm nhiễm hoặc bệnh máu ác tính",
            note_type="high_note",
        ),
    ]
    retriever, _ = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="normal",
        limit=2,
    )

    assert [chunk["note_type"] for chunk in chunks] == ["description"]


def test_source_diversity_limits_one_chunk_per_source(monkeypatch):
    _settings_stub(monkeypatch)
    docs = [
        _doc(
            "Tăng bạch cầu nhẹ thường gặp trong phản ứng viêm nhiễm cấp tính do nhiễm trùng khu trú",
            note_type="high_note",
            source="https://a.test",
        ),
        _doc(
            "Bạch cầu tăng cao kéo dài có thể liên quan rối loạn tăng sinh tủy xương cần theo dõi",
            note_type="high_note",
            source="https://b.test",
        ),
        _doc(
            "Chỉ số WBC tăng vọt cần được bác sĩ đánh giá thêm trong bối cảnh lâm sàng cụ thể",
            note_type="high_note",
            source="https://c.test",
        ),
    ]
    retriever, _ = _retriever(docs)

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    sources = [chunk["source"] for chunk in chunks]
    assert len(set(sources)) == len(sources) == 2


def test_no_candidates_returns_empty(monkeypatch):
    _settings_stub(monkeypatch)
    retriever, _ = _retriever([])

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    assert chunks == []


def test_long_correctly_labeled_but_semantically_off_topic_metadata_chunk_is_capped(monkeypatch):
    """Reviewer's core complaint: label match alone must not buy a free 1.0.

    A metadata chunk long enough to clear the length ceiling, and correctly
    labeled `high_note`, but whose actual embedded content is semantically
    unrelated to the query (orthogonal vector, cosine similarity 0) must NOT
    keep the full score — length/label say nothing about whether the content
    is actually relevant. A genuinely on-topic dense hit must then win.
    """
    _settings_stub(monkeypatch, min_score=0.0, min_chunk_length=30)
    off_topic_long_metadata = _doc(
        "Đoạn văn này dài và đúng nhãn high_note nhưng nội dung thực tế không "
        "liên quan gì tới ý nghĩa lâm sàng của việc bạch cầu tăng cao ở đây.",
        note_type="high_note",
        source="https://a.test",
        embedding=_ORTHOGONAL,  # cosine similarity 0 with the default query embedding
    )
    on_topic_dense = _doc(
        "Khi WBC tăng cao hơn mức bình thường đồng nghĩa số lượng bạch cầu trong "
        "máu tăng, có thể phản ánh viêm nhiễm hoặc bệnh máu ác tính.",
        note_type="high_note",
        source="https://b.test",
        embedding=_ALIGNED,
    )
    retriever, store = _retriever([off_topic_long_metadata, on_topic_dense])
    original_search = store.search

    def fake_search(query, *, k, filter=None, query_embedding=None):
        result = original_search(query, k=k, filter=filter, query_embedding=query_embedding)
        result["documents"] = [[on_topic_dense["text"]]]
        result["metadatas"] = [[on_topic_dense["metadata"]]]
        result["distances"] = [[0.05]]
        return result

    store.search = fake_search

    chunks = retriever.retrieve(
        query="Ý nghĩa xét nghiệm WBC là gì?",
        analyte_id="wbc",
        status="high",
        limit=2,
    )

    by_text = {chunk["text"]: chunk for chunk in chunks}
    # The off-topic chunk is long and correctly labeled, but its score must be
    # capped near 0 by the semantic mismatch — not the 1.0 a pure length/label
    # check would have granted it.
    assert by_text[off_topic_long_metadata["text"]]["score"] < 0.1
    # The genuinely on-topic dense hit outranks it.
    assert chunks[0]["text"] == on_topic_dense["text"]
