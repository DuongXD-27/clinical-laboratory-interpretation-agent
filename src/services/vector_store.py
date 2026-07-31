import logging
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from langchain_huggingface import HuggingFaceEmbeddings

from src.config import get_settings

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """Lỗi khi thao tác với vector store (embedding hoặc ChromaDB)."""


class VectorStore:
    def __init__(
        self,
        persist_dir: str,
        collection_name: str = "medical_kb",
        device: str | None = None,
    ):
        self.persist_dir = persist_dir
        self.collection_name = collection_name
        # device: ưu tiên tham số truyền vào (test/override), fallback settings
        # (config qua .env: EMBEDDING_DEVICE=cpu|cuda|mps) thay vì hardcode "cpu".
        self.device = device or get_settings().embedding_device
        try:
            self._client = chromadb.PersistentClient(
                path=persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Không khởi tạo được ChromaDB PersistentClient tại '{persist_dir}': {exc}"
            ) from exc

        try:
            self._embeddings = HuggingFaceEmbeddings(
                model_name="BAAI/bge-m3",
                model_kwargs={"device": self.device},
                encode_kwargs={"normalize_embeddings": True},
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Không load được embedding model BAAI/bge-m3 (device={self.device}): {exc}"
            ) from exc

    def get_collection(self):
        try:
            return self._client.get_or_create_collection(
                name=self.collection_name,
                metadata={"hnsw:space": "cosine"},
            )
        except Exception as exc:
            raise VectorStoreError(
                f"Không lấy/tạo được collection '{self.collection_name}': {exc}"
            ) from exc

    def add_documents(
        self, texts: list[str], metadatas: list[dict], ids: list[str]
    ):
        if not (len(texts) == len(metadatas) == len(ids)):
            raise VectorStoreError(
                "texts, metadatas, ids phải cùng độ dài — nhận được "
                f"{len(texts)}, {len(metadatas)}, {len(ids)}"
            )

        collection = self.get_collection()

        try:
            embeddings = self._embeddings.embed_documents(texts)
        except Exception as exc:
            logger.exception("Loi khi embed %d documents", len(texts))
            raise VectorStoreError(f"Embedding thất bại: {exc}") from exc

        try:
            collection.add(
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
                ids=ids,
            )
        except Exception as exc:
            # Bat loi pho bien: dimension mismatch (doi model embedding giua
            # cac lan add), duplicate id, disk/permission loi khi ghi persist.
            logger.exception("Loi khi ghi %d embeddings vao ChromaDB", len(texts))
            raise VectorStoreError(f"Ghi vào ChromaDB thất bại: {exc}") from exc

    def search(self, query: str, k: int = 5, filter: dict | None = None):
        collection = self.get_collection()

        try:
            query_embedding = self._embeddings.embed_query(query)
        except Exception as exc:
            logger.exception("Loi khi embed query: %r", query)
            raise VectorStoreError(f"Embedding câu truy vấn thất bại: {exc}") from exc

        try:
            return collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=filter,
            )
        except Exception as exc:
            logger.exception("Loi khi query ChromaDB")
            raise VectorStoreError(f"Truy vấn ChromaDB thất bại: {exc}") from exc

    def delete_collection(self):
        try:
            self._client.delete_collection(self.collection_name)
        except ValueError:
            pass


@lru_cache
def get_vector_store() -> VectorStore:
    settings = get_settings()
    return VectorStore(persist_dir=settings.chroma_persist_dir)
