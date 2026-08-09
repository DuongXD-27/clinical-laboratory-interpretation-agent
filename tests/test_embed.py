"""Vector repository contract tests without loading a local transformer model."""

from __future__ import annotations

import pytest

from src.services.vector_store import VectorStore, VectorStoreError


class FakeEmbeddingProvider:
    provider_name = "fake"
    model_name = "fake-medical-v1"
    dimension = 3

    @staticmethod
    def _embed(text: str) -> list[float]:
        lowered = text.lower()
        if "vector" in lowered or "chroma" in lowered:
            return [1.0, 0.0, 0.0]
        return [0.0, 1.0, 0.0]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


def make_store(tmp_path, provider=None):
    return VectorStore(
        persist_dir=str(tmp_path),
        collection_name="medical_kb_test",
        corpus_version="test-corpus-v1",
        embedding_provider=provider or FakeEmbeddingProvider(),
    )


def test_chromadb_add_and_filtered_query(tmp_path):
    store = make_store(tmp_path)
    store.add_documents(
        texts=[
            "ChromaDB stores vector embeddings.",
            "Glucose is a laboratory analyte.",
        ],
        metadatas=[
            {"analyte_id": "wbc", "indicator": "WBC", "sources": "[]"},
            {"analyte_id": "glucose", "indicator": "Glucose", "sources": "[]"},
        ],
        ids=["doc-1", "doc-2"],
    )

    result = store.search("vector database", k=1, filter={"analyte_id": "wbc"})

    assert store.get_collection().count() == 2
    assert result["documents"][0] == ["ChromaDB stores vector embeddings."]


def test_collection_metadata_mismatch_fails_with_clear_error(tmp_path):
    store = make_store(tmp_path)
    store.get_collection()

    incompatible_provider = FakeEmbeddingProvider()
    incompatible_provider.model_name = "different-model"
    incompatible = make_store(tmp_path, incompatible_provider)

    with pytest.raises(VectorStoreError, match="metadata mismatch"):
        incompatible.get_collection()


def test_provider_returning_wrong_dimension_is_rejected(tmp_path):
    provider = FakeEmbeddingProvider()
    provider.embed_documents = lambda texts: [[1.0, 0.0] for _ in texts]
    store = make_store(tmp_path, provider)

    with pytest.raises(VectorStoreError, match="unexpected dimension"):
        store.add_documents(
            texts=["document"],
            metadatas=[{"analyte_id": "wbc"}],
            ids=["doc-1"],
        )
