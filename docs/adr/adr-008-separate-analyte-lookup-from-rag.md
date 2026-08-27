# ADR-008: Tách lookup chỉ số chuẩn khỏi RAG tài liệu y khoa

**Ngày:** 2026-08-08  
**Trạng thái:** Accepted  
**Phạm vi:** `release/v3.0`

## Bối cảnh

Triển khai trước đây dùng `BAAI/bge-m3` trong tiến trình FastAPI để semantic search
trên tập dữ liệu chỉ có chín chỉ số xét nghiệm. Model được tải khi `/analyze` chạy và
làm vượt giới hạn RAM của Railway. Thiết kế này đồng thời trộn hai loại dữ liệu:

1. dữ liệu có cấu trúc và có tính quyết định: mã/alias, đơn vị, khoảng tham chiếu,
   trạng thái và critical threshold;
2. dữ liệu phi cấu trúc, chỉ dùng để bổ sung ngữ cảnh: tài liệu và nguồn y khoa.

Lookup loại (1) không phải bài toán semantic search. Tuy nhiên loại (2) vẫn cần một
pipeline RAG thật để đáp ứng PLO3 và làm phong phú lời giải thích có nguồn.

## Quyết định

### Luồng authoritative

- `ReferenceRepository` và `AnalyteCatalog` thực hiện lookup xác định theo key/alias.
- Range, status, unit và critical không phụ thuộc embedding, vector store hoặc LLM.
- Mỗi analyte mới phải qua range flag, confidence, source priority và test biên trước
  khi được approve.
- Curated explanation tối thiểu và nguồn đã duyệt là fallback bắt buộc.

### Luồng RAG tùy chọn

- RAG chỉ truy xuất tài liệu y khoa phi cấu trúc để làm giàu giải thích/câu hỏi.
- Embedding dùng `EmbeddingProvider`; production ưu tiên API ngoài, không tải model
  transformer local trong FastAPI.
- `MedicalKnowledgeRetriever` tách khỏi code phân loại và được lọc metadata theo
  `analyte_id` trước khi lấy context.
- URL nguồn do LLM tự sinh không được trả ra; chỉ chấp nhận nguồn từ catalog hoặc
  metadata của tài liệu retrieved.

### Versioning và compatibility

Mỗi collection lưu metadata:

- `schema_version`;
- `embedding_provider`;
- `embedding_model`;
- `embedding_dimension`;
- `corpus_version`.

Metadata không khớp làm ingestion/CI thất bại rõ ràng. Runtime coi RAG là optional:
vô hiệu hóa riêng RAG, ghi log và dùng curated fallback; không làm sập auth, OCR hoặc
`/analyze`. Khi đổi model phải tạo collection version mới rồi chuyển sang sau khi
ingest/eval thành công, không trộn vector khác dimension trong collection cũ.

## Hệ quả

- Mở rộng số analyte không làm tăng tải embedding và không buộc reindex corpus.
- `/analyze` vẫn trả kết quả an toàn khi provider, mạng hoặc ChromaDB hỏng.
- `sentence-transformers` và BGE-M3 được loại khỏi dependency production, giảm image,
  cold start và peak RAM.
- Embedding API loại bỏ RAM model nhưng vector index vẫn có chi phí tài nguyên. Khi
  corpus lớn, cần chuyển vector store sang service riêng/managed thay vì giữ HNSW lớn
  trong cùng tiến trình FastAPI.
- RAGAS/PLO3 phải đánh giá retrieved context thật từ corpus phi cấu trúc; test lookup
  analyte không được dùng làm bằng chứng chất lượng RAG.

## Tiêu chí kiểm chứng

- Tắt RAG hoặc mô phỏng timeout/mismatch vẫn cho `/analyze` hoàn tất bằng fallback.
- Collection khác model/dimension bị từ chối với thông báo rõ ở ingestion/test.
- Mọi range/status/critical giữ nguyên dù context RAG thay đổi hoặc rỗng.
- Deployment smoke test xác nhận request không restart container và peak RAM nằm dưới
  replica limit.
