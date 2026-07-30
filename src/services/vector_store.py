from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import get_settings


class VectorStore:
    def __init__(self, persist_dir: str, collection_name: str = "medical_kb"):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        self._embeddings = HuggingFaceEmbeddings(
            model_name="BAAI/bge-m3",
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )

    def get_collection(self):
        return self._client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )

    def add_documents(
        self, texts: list[str], metadatas: list[dict], ids: list[str]
    ):
        collection = self.get_collection()
        embeddings = self._embeddings.embed_documents(texts)
        collection.add(
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
            ids=ids,
        )

    def search(self, query: str, k: int = 5, filter: dict | None = None):
        collection = self.get_collection()
        query_embedding = self._embeddings.embed_query(query)
        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=filter,
        )
        return results

    def delete_collection(self):
        try:
            self._client.delete_collection(self.collection_name)
        except ValueError:
            pass


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(persist_dir=settings.chroma_persist_dir)
