"""Smoke test: ChromaDB local setup + embed 1-2 đoạn văn bản thật.

Chạy: pytest tests/test_embed.py -v -s
(hoặc: python -m pytest tests/test_embed.py -v -s)

Test này KHÔNG mock — dùng đúng VectorStore thật (src/services/vector_store.py),
đúng HuggingFaceEmbeddings (BAAI/bge-m3) mà project đang cấu hình, để xác nhận
pipeline embed thật sự chạy được end-to-end (add + persist + query),
không chỉ là "import không lỗi".
"""

import shutil
import tempfile

import pytest

from src.services.vector_store import VectorStore

SAMPLE_TEXTS = [
    "ChromaDB là một vector database mã nguồn mở, dùng để lưu trữ và truy vấn embedding.",
    "Retrieval-Augmented Generation (RAG) kết hợp tìm kiếm tài liệu với sinh văn bản của LLM.",
]


@pytest.fixture
def temp_store():
    """Dùng thư mục persist tạm thời, riêng biệt với data/chroma thật của project,
    để test không đụng vào / không làm bẩn dữ liệu thật đang có."""
    tmp_dir = tempfile.mkdtemp(prefix="chroma_test_")
    store = VectorStore(persist_dir=tmp_dir, collection_name="test_embed_smoke")
    yield store
    shutil.rmtree(tmp_dir, ignore_errors=True)


def test_chromadb_setup_and_embed_two_passages(temp_store):
    """AC: ChromaDB local setup xong + embed thử được ít nhất 1-2 đoạn."""
    ids = ["doc-1", "doc-2"]
    metadatas = [{"source": "test"}, {"source": "test"}]

    # 1. Add — chạy embedding model thật (BAAI/bge-m3) + ghi vào ChromaDB thật
    temp_store.add_documents(texts=SAMPLE_TEXTS, metadatas=metadatas, ids=ids)

    # 2. Verify đã persist đúng số lượng — đây là bằng chứng embed thật sự
    #    thành công, không chỉ gọi hàm mà không lỗi.
    collection = temp_store.get_collection()
    count = collection.count()
    assert count == 2, f"Kỳ vọng 2 embedding đã lưu, thực tế: {count}"

    # 3. Query thử — đảm bảo có thể tìm lại đúng đoạn liên quan nhất
    result = temp_store.search("vector database lưu embedding là gì?", k=1)
    assert result["documents"], "Query không trả về kết quả nào"
    top_doc = result["documents"][0][0]
    assert "ChromaDB" in top_doc, (
        f"Kỳ vọng câu hỏi về vector database khớp với đoạn nói về ChromaDB, "
        f"nhưng lại khớp với: {top_doc!r}"
    )

    print(f"\n[OK] Đã embed {count} đoạn, query trả về đúng đoạn liên quan nhất.")
