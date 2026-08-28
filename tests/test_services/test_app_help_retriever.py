"""Unit tests for AppHelpRetriever's section-hint promotion.

Found via manual UI testing: dense search reliably picks the right
FEATURE but sometimes the wrong SECTION within it — e.g. "Làm sao tải
phiếu xét nghiệm?" top-matched upload-analysis's "what is this feature
for" section over its own "steps" section, because both sections share
heavy vocabulary. These tests exercise the deterministic section
promotion (_section_hint + AppHelpRetriever._promote_section_hint)
against a fake VectorStore, so no real Chroma/embedding call is needed.
"""

from __future__ import annotations

from src.services.app_help_retriever import AppHelpRetriever, _section_hint


class _FakeVectorStore:
    """Chunk store keyed by feature -> {heading: text}. `search` always
    returns chunks in a FIXED (deliberately "wrong") order to simulate the
    real dense-search confusion; `get_by_metadata` does an exact lookup,
    mirroring Chroma's `where` filter semantics."""

    def __init__(self, chunks: list[dict]):
        self._chunks = chunks

    def search(self, query, *, k=5, filter=None, query_embedding=None):
        candidates = self._chunks
        if filter:
            feature = filter.get("feature")
            if feature:
                candidates = [c for c in candidates if c["feature"] == feature]
        candidates = candidates[:k]
        return {
            "documents": [[c["text"] for c in candidates]],
            "metadatas": [[c["metadata"] for c in candidates]],
            "distances": [[c["distance"] for c in candidates]],
            "ids": [[c["id"] for c in candidates]],
        }

    def get_by_metadata(self, *, filter, limit=None, include_embeddings=False):
        want_feature = None
        want_heading = None
        for clause in filter.get("$and", []):
            if "feature" in clause:
                want_feature = clause["feature"]
            if "heading" in clause:
                want_heading = clause["heading"]
        matches = [c for c in self._chunks if c["feature"] == want_feature and c["metadata"]["heading"] == want_heading]
        return {
            "documents": [c["text"] for c in matches],
            "metadatas": [c["metadata"] for c in matches],
            "ids": [c["id"] for c in matches],
        }


def _chunk(feature, heading, distance, text=None):
    return {
        "id": f"{feature}::{heading}",
        "feature": feature,
        "text": text or f"[{feature}/{heading}]",
        "distance": distance,
        "metadata": {
            "feature": feature,
            "role": "patient",
            "route": "/x",
            "heading": heading,
            "source_file": f"{feature}.md",
        },
    }


def test_section_hint_detects_step_and_where_intents():
    assert _section_hint("Làm sao tải phiếu xét nghiệm?") == "Các bước sử dụng?"
    assert _section_hint("hướng dẫn tôi dùng OCR") == "Các bước sử dụng?"
    assert _section_hint("Tôi sửa hồ sơ ở đâu?") == "Người dùng tìm ở đâu?"
    assert _section_hint("Tại sao phải xác nhận OCR?") is None


def test_promotes_steps_section_when_dense_search_picks_the_wrong_one():
    # Dense search (deliberately) ranks "what is this for" above "steps",
    # mirroring the real bug found in manual testing.
    store = _FakeVectorStore(
        [
            _chunk("upload-analysis", "Feature này dùng để làm gì?", distance=0.24),
            _chunk("upload-analysis", "Các bước sử dụng?", distance=0.27),
            _chunk("upload-analysis", "Người dùng tìm ở đâu?", distance=0.28),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.5, top_k=3)

    result = retriever.retrieve("Làm sao tải phiếu xét nghiệm?")

    assert result.matches[0].chunk_id == "upload-analysis::Các bước sử dụng?"


def test_promotes_where_section_for_a_pure_location_question():
    store = _FakeVectorStore(
        [
            _chunk("profile", "Các bước sử dụng?", distance=0.22),
            _chunk("profile", "Người dùng tìm ở đâu?", distance=0.26),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.5, top_k=2)

    result = retriever.retrieve("Tôi sửa hồ sơ ở đâu?")

    assert result.matches[0].chunk_id == "profile::Người dùng tìm ở đâu?"


def test_no_promotion_when_dense_search_already_picked_the_right_section():
    store = _FakeVectorStore(
        [
            _chunk("trends", "Các bước sử dụng?", distance=0.20),
            _chunk("trends", "Người dùng tìm ở đâu?", distance=0.26),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.5, top_k=2)

    result = retriever.retrieve("Làm sao xem xu hướng WBC?")

    assert result.matches[0].chunk_id == "trends::Các bước sử dụng?"


def test_no_promotion_when_question_has_no_step_or_where_cue():
    store = _FakeVectorStore(
        [
            _chunk("ocr-review", "Không làm được gì?", distance=0.20),
            _chunk("ocr-review", "Các bước sử dụng?", distance=0.26),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.5, top_k=2)

    result = retriever.retrieve("Tại sao phải xác nhận OCR?")

    assert result.matches[0].chunk_id == "ocr-review::Không làm được gì?"


def test_promotion_no_op_when_target_section_missing_for_the_feature():
    # Corpus files always have all 5 headings in practice, but the
    # promotion must degrade gracefully (keep dense ranking) if a lookup
    # ever comes up empty, rather than erroring or dropping the match.
    store = _FakeVectorStore(
        [
            _chunk("critical-alerts", "Feature này dùng để làm gì?", distance=0.24),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.5, top_k=1)

    result = retriever.retrieve("Làm sao xem cảnh báo khẩn cấp?")

    assert result.matches[0].chunk_id == "critical-alerts::Feature này dùng để làm gì?"


def test_section_hint_detects_what_intent():
    from src.services.app_help_retriever import _WHAT_HEADING

    assert _section_hint("Cảnh báo khẩn cấp nghĩa là gì?") == _WHAT_HEADING
    assert _section_hint("Chức năng OCR dùng để làm gì?") == _WHAT_HEADING


def test_deterministic_hint_bypasses_a_low_dense_score():
    # Regression: found via manual testing. "Tải phiếu ở đâu?" correctly
    # resolves feature via FEATURE_HINTS ("tai phieu o dau" ->
    # upload-analysis) but the dense score for every chunk in that feature
    # can legitimately fall below min_score for a short/vague phrasing —
    # a real question was fail-closed for no good reason. When BOTH the
    # feature and the section are resolved deterministically (curated
    # phrase + literal heading), no embedding score should be needed at
    # all — this test's store never even implements dense-search scoring
    # correctly (returns a huge distance = ~0 score) to prove the
    # deterministic path is what's actually taken, not a lucky pass.
    class _AlwaysLowScoreStore(_FakeVectorStore):
        def search(self, query, *, k=5, filter=None, query_embedding=None):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

    store = _AlwaysLowScoreStore(
        [
            _chunk("upload-analysis", "Người dùng tìm ở đâu?", distance=0.99),
        ]
    )
    retriever = AppHelpRetriever(vector_store=store, min_score=0.70, top_k=3)

    result = retriever.retrieve("Tải phiếu ở đâu?")

    assert result.has_match
    assert result.matches[0].chunk_id == "upload-analysis::Người dùng tìm ở đâu?"
    assert result.matches[0].score == 1.0  # deterministic-match sentinel


def test_no_deterministic_shortcut_without_both_hints():
    # Only a feature hint (no section cue) must still go through normal
    # dense search + threshold — the shortcut requires BOTH signals.
    class _AlwaysEmptyStore(_FakeVectorStore):
        def search(self, query, *, k=5, filter=None, query_embedding=None):
            return {"documents": [[]], "metadatas": [[]], "distances": [[]], "ids": [[]]}

    store = _AlwaysEmptyStore([_chunk("upload-analysis", "Người dùng tìm ở đâu?", distance=0.99)])
    retriever = AppHelpRetriever(vector_store=store, min_score=0.70, top_k=3)

    # "chuc nang ocr" is a feature hint (-> ocr-review) but has no
    # step/where/what cue, so no section_target — must not shortcut.
    result = retriever.retrieve("chức năng OCR")

    assert not result.has_match
