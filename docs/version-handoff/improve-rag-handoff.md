# RAG — Status-aware Selective Retrieval (kiến trúc hiện tại)

Tài liệu này giải thích kiến trúc RAG đang chạy trên nhánh `rag-improvement`
cho cả team: **mỗi tầng làm gì, dữ liệu đi đâu, và vì sao chọn cách này thay
vì cách khác**. Mục 0 tóm tắt đã trả lời/sửa gì theo nhận xét kiến trúc của
nhóm trưởng (`nhan-xet-rag.docx`); từ mục 1 trở đi là giải thích kiến trúc
hiện tại nói chung.

---

## 0. Đã trả lời nhận xét kiến trúc như thế nào

Sau khi nhóm trưởng nhận xét (`nhan-xet-rag.docx`), đã rà lại từng ý và sửa
trực tiếp trong code — không có ý nào bị bỏ qua:

| # | Nhận xét | Đã làm gì | Bằng chứng |
| --- | --- | --- | --- |
| 1 | Metadata-prong cho điểm 1.0 cứng, tin tưởng mù quáng vào nhãn, bỏ qua chất lượng nội dung thật | Sửa 2 lần: (a) length-taper — chunk quá ngắn bị loại, chunk vừa đủ dài không còn ăn trần điểm; (b) sau khi bị chỉ ra length ≠ quality, thêm **cross-check ngữ nghĩa** — điểm cuối = `min(length_ceiling, cosine_similarity(chunk, query))`, dùng lại embedding đã lưu sẵn trong Chroma (không tốn thêm API call) | `_metadata_score()` trong `medical_knowledge_retriever.py`; test `test_long_correctly_labeled_but_semantically_off_topic_metadata_chunk_is_capped` |
| 2 | Dedup bằng ngưỡng cứng 0.6 (containment) — rủi ro gộp nhầm 2 nguyên nhân khác nhau, hoặc bỏ sót 2 câu cùng ý khác chữ | **Bỏ hẳn** cơ chế này, không tinh chỉnh ngưỡng. Giờ chỉ dedup khi trùng y hệt từng chữ (exact-text) | Grep `src/services/medical_knowledge_retriever.py` không còn `SequenceMatcher`; test `test_reviewer_false_positive_pair_is_preserved` tái hiện đúng case nhận xét nêu |
| 3 | Chốt cứng `RETRIEVAL_MIN_SCORE=0.3`/`top_k=3` không chứng minh | Đo bằng thực nghiệm, không đoán: `eval/rag/adversarial_threshold_test.py` chèn rác thật (9 loại × 3 miền độc lập) cạnh nội dung thật, tìm ra ranh giới phân tách rồi mới chốt **0.8** (không phải 0.3). `top_k=3` xác nhận đủ dùng qua `eval/rag/retrieval_param_sweep.py` (tăng lên không giúp gì thêm). **Xem chi tiết đầy đủ và cách tái tạo tại `docs/version-handoff/retrieval-min-score-evidence.md`** | file evidence riêng nêu trên |
| 4 | `GENERATION_SAFETY_CONTRACT`/`STATUS_QUALIFIERS` viết tay 2 lần ở analyzer và guardrail — rủi ro drift | Gom về `src/services/medical_safety_assets.py`, cả 2 node cùng import. Khi verify lại phát hiện guardrail lúc đầu vẫn viết tay rule riêng và chưa gọi `ensure_reference_qualification()` sau rewrite — đã vá luôn | mục 5 bên dưới; test `test_safety_remediation.py` |
| 5 | Context length chưa giới hạn (nối chunk trực tiếp) | Thêm `context_budget.py::build_bounded_context` — ngân sách ký tự, không cắt giữa chunk, wire vào cả 3 nơi nối context | mục 5 "Context budget" bên dưới |

Ngoài 5 ý trên, quá trình verify lại (đọc code thật thay vì tin đã xong) còn
bắt được 2 lỗi không nằm trong bản nhận xét gốc nhưng nghiêm trọng:

- **`status` chưa từng được truyền vào retriever** — `analyzer_node.py` gọi
  `retriever.retrieve()` thiếu `status=status`, khiến toàn bộ cơ chế
  status-aware note_type filtering (trái tim của kiến trúc này) **chưa từng
  chạy thật**, luôn chỉ lấy `description` bất kể trạng thái thật là gì. Đã
  sửa.
- **`retrieval_top_k` là dead config** — có trong `config.py` nhưng
  `analyzer_node.py` hardcode `limit=3`, không đọc setting. Đã sửa.

Đã VERIFY lại bằng kịch bản chạy thật (Chroma + embedding thật, không mock):
lấy đúng `high_note`/`low_note`/`critical_*_note` theo từng trạng thái, RAG
lỗi/rỗng vẫn fallback an toàn không crash, guardrail rewrite làm mất câu ranh
giới trạng thái thì bị tự chèn lại đúng. Toàn bộ test liên quan pass.

---

## 1. Bối cảnh: RAG nằm ở đâu trong pipeline

Sau khi một chỉ số xét nghiệm đã được phân loại trạng thái
(`normal`/`low`/`high`/`critical_low`/`critical_high`) bởi bước xử lý có cấu
trúc (không liên quan LLM), pipeline sinh giải thích chạy:

```
[Structured facts: analyte_id, status, value, unit — đã xác định, KHÔNG do LLM quyết định]
        │
        ▼
┌─ RAG (medical_knowledge_retriever.py) ────────────┐
│  lấy đoạn văn khớp đúng chỉ số + đúng trạng thái  │
└──────────────┬─────────────────────────────────────┘
               ▼
┌─ Generation (analyzer_node.py) ───────────────────┐
│  prompt = dữ liệu có cấu trúc + context RAG        │
│           + GENERATION_SAFETY_CONTRACT             │
│  → LLM → giải thích                                │
│  → ensure_reference_qualification() (deterministic)│
└──────────────┬─────────────────────────────────────┘
               ▼
┌─ Guardrail (guardrail_node.py) ───────────────────┐
│  MedicalSafetyValidator (regex + intent cục bộ)    │
│  vi phạm → LLM rewrite, grounded trên cùng          │
│  retrieved_contexts + GENERATION_SAFETY_CONTRACT    │
│  → ensure_reference_qualification() lại lần nữa     │
└──────────────────────────────────────────────────────┘
```

**Điểm quan trọng nhất của thiết kế này:** `retrieved_contexts` chỉ được RAG
sinh ra **một lần** (trong analyzer) rồi lưu vào state, dùng lại cho **cả hai
nơi** — analyzer (context để sinh giải thích) và guardrail (grounding khi phải
viết lại văn bản không an toàn). Guardrail không gọi lại RAG. Điều này đảm
bảo generation và guardrail luôn "nói cùng một nguồn tài liệu", tránh việc
guardrail tự bịa nội dung khi rewrite.

Cũng vì lý do này, `GENERATION_SAFETY_CONTRACT` (hợp đồng an toàn — những gì
NORMAL/HIGH/LOW/CRITICAL được phép và không được phép nói) và
`ensure_reference_qualification()` (đảm bảo câu xác nhận ranh giới trạng thái
luôn có mặt) nằm trong **một module dùng chung**
(`src/services/medical_safety_assets.py`), được cả analyzer và guardrail
import — không viết tay lại ở từng nơi.

---

## 2. Vì sao không dùng RAG "naive" (semantic search thuần)

Cách làm ngây thơ: mỗi chỉ số lưu **một blob văn bản tổng hợp**, truy vấn
bằng **semantic search thuần túy** trên toàn bộ blob đó. Ba lý do bỏ cách này:

| Vấn đề của RAG ngây thơ | Hệ quả thực tế |
| --- | --- |
| **Không hiểu trạng thái** — cùng WBC nhưng `high`/`low`/`normal` cần nội dung khác nhau, semantic search trả về cả blob chung | WBC cao mà giải thích lẫn cả câu "bình thường không gây triệu chứng" → sai lệch nguy hiểm về mặt y tế |
| **Retrieval không xác định** — query semantic đôi khi trả context không liên quan chỉ số đang xét | LLM sinh nội dung dựa trên tài liệu sai |
| **Không có cổng chặn chất lượng** — retrieval kém → LLM sinh kém, không có cơ chế rơi về nguồn tin cậy | Chất lượng giải thích phụ thuộc hoàn toàn vào độ may rủi của semantic search |

**Nguyên tắc thay thế:** tận dụng **status đã được phân loại có cấu trúc** ở
bước trước pipeline để chọn đúng loại tài liệu trước khi search — biến "tìm
gần nghĩa" thành "lấy đúng nhãn, rồi mới xếp hạng lại bằng ngữ nghĩa".

---

## 3. Chuẩn bị dữ liệu — vì sao chunk theo `note_type`

Nguồn: `data/reference/explanations.json`. Mỗi chỉ số (`indicator`) có nhiều
nguồn (`sources[]`); mỗi nguồn có các trường `description`, `high_note`,
`low_note`, `critical_high_note`, `critical_low_note`.

`src/scripts/ingest_kb.py` tách mỗi `(chỉ số × nguồn × note_type)` thành
**một chunk riêng**, id dạng `{analyte_id}::{note_type}::{source_index}`:

```
wbc::high_note::0   → "Ý nghĩa khi tăng cao" của WBC, từ nguồn 0
wbc::description::1 → "Giải thích cơ bản" của WBC, từ nguồn 1
```

Metadata mỗi chunk:

| field | ý nghĩa |
| --- | --- |
| `indicator` | tên hiển thị (vd "WBC") |
| `analyte_id` | slug id dùng để filter (vd `wbc`) |
| `note_type` | `description` / `high_note` / `low_note` / `critical_high_note` / `critical_low_note` |
| `sources` | JSON-encoded URL nguồn gốc |

**Vì sao tách nhỏ thay vì 1 blob/chỉ số:** tách theo `note_type` cho phép
lấy **đúng đoạn văn ứng với trạng thái kết quả** bằng metadata filter, không
cần lấy cả blob rồi lọc lại bằng LLM hay heuristic.

### Bảng ánh xạ status → note_type (`_STATUS_NOTE_TYPES`)

Đây là "trí thông minh có cấu trúc" của retriever:

| Status | note_type ưu tiên | fallback cùng lấy |
| --- | --- | --- |
| `high` | `high_note` | `description` |
| `low` | `low_note` | `description` |
| `critical_high` | `critical_high_note` | `high_note`, `description` |
| `critical_low` | `critical_low_note` | `low_note`, `description` |
| `normal` / `unknown` | `description` | — |

`description` luôn đi kèm làm ngữ cảnh nền trung tính bên cạnh note đúng
trạng thái.

---

## 4. Retriever — 4 tầng xử lý (`ChromaMedicalKnowledgeRetriever.retrieve()`)

```
[analyte_id, status, query]
        │
        ▼
┌─ Query transformation ────────────────────────────┐
│  câu hỏi được viết lại theo trạng thái            │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ Candidate generation (2 nhánh song song) ────────┐
│  a) Metadata-prong: lookup deterministic theo nhãn │
│  b) Dense-prong: semantic search                   │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ Fusion + rerank ──────────────────────────────────┐
│  dedup exact-text, xếp hạng, giới hạn top_k,       │
│  đa dạng nguồn                                     │
└──────────────┬──────────────────────────────────────┘
               ▼
┌─ Relevance gate ───────────────────────────────────┐
│  loại chunk điểm thấp → có thể trả về rỗng          │
└──────────────────────────────────────────────────────┘
```

### 4a. Query transformation (`_status_query`)

- `high`/`critical_high` → *"...Khi kết quả tăng cao, ý nghĩa và nguyên nhân
  là gì?"*
- `low`/`critical_low` → *"...Khi kết quả giảm thấp, ý nghĩa và nguyên nhân
  là gì?"*
- còn lại → *"Giải thích chung về ý nghĩa của chỉ số này."*

**Vì sao:** kênh metadata đã biết chính xác trạng thái qua nhãn, nhưng kênh
dense (semantic) vẫn cần một câu hỏi "nói đúng trạng thái" — nếu hỏi chung
chung, semantic search trộn lẫn nội dung tăng/giảm/bình thường.

### 4b. Candidate generation — 2 nhánh song song

**Metadata-prong (kênh chính)** — lookup deterministic bằng
`vector_store.get_by_metadata()`, **không tốn embedding call**:

```python
where = {"$and": [{"analyte_id": analyte_id},
                  {"note_type": {"$in": note_types}}]}
```

Điểm số (`_metadata_score`) **không còn là 1.0 cứng cho mọi chunk khớp nhãn**
— gồm 2 lớp, lấy giá trị **nhỏ hơn**:

1. **Length-taper**: chunk quá ngắn (< `METADATA_MIN_CHUNK_LENGTH`, mặc định
   30 ký tự sau khi bỏ dấu) bị **loại thẳng**, không vào candidate pool.
   Chunk dài ≥ 2× ngưỡng tối thiểu → trần 1.0. Chunk "vừa đủ dài" → điểm
   trong [0.9, 1.0).
2. **Cross-check ngữ nghĩa**: cosine similarity giữa embedding đã lưu sẵn
   của chunk (từ lúc ingest, không tốn thêm API call) và embedding câu hỏi
   (dùng chung với kênh dense-prong, chỉ embed 1 lần cho cả 2 kênh).

`score = min(length_ceiling, semantic_similarity)`.

**Vì sao cần cả 2 lớp:** length-taper chỉ chặn được chunk *quá ngắn để có
nội dung thật* (case "Chỉ số tăng" 3 chữ trong nhận xét). Nhưng độ dài không
phải là chất lượng — một chunk dài, đúng nhãn, nhưng **lạc đề hoặc sai** vẫn
qua được lớp 1. Lớp cross-check ngữ nghĩa chặn thêm trường hợp này: nếu nội
dung thực sự (qua embedding) không liên quan tới câu hỏi, điểm bị hạ xuống
đúng mức độ liên quan thật, không còn ăn trần chỉ vì khớp nhãn. Xem thêm giới
hạn của cách này (không bắt được nội dung sai nhưng viết trôi chảy đúng chủ
đề) tại `docs/version-handoff/retrieval-min-score-evidence.md`.

**Dense-prong (kênh bổ sung)** — semantic search với câu hỏi từ 4a, filter
`analyte_id` + `note_type` đúng trạng thái, `k = max(top_k*2, số note_type
của status)`. Điểm = `1.0 - cosine_distance`.

**Vì sao vẫn cần kênh này dù đã có kênh chắc chắn:** metadata-prong chỉ đúng
khi dữ liệu ingest **đầy đủ**. Nếu một chỉ số chưa có `high_note`, kênh
metadata "bó tay" — dense-prong cứu bằng cách tìm nội dung nói về "tăng cao"
theo nghĩa. Đây là lớp lưới an toàn, không phải kênh chính.

### 4c. Fusion + rerank (`_fuse`)

1. **Dedup exact-text**: một chunk có thể trúng cả 2 kênh (cùng text) — giữ
   bản có score cao hơn. **Không có fuzzy content-dedup** (đã bỏ hẳn — xem
   mục 6).
2. **Relevance gate**: loại chunk có `score < RETRIEVAL_MIN_SCORE` (mặc định
   **0.8** — giá trị đo bằng thực nghiệm, xem `retrieval-min-score-evidence.md`,
   không phải đoán). Nếu tất cả bị loại → trả về `[]` (không có gợi ý sai
   lệch nào tốt hơn việc trả rỗng).
3. **Sắp xếp**: ưu tiên `note_type` khớp đúng status trước, sau đó theo
   score, sau đó theo độ dài nội dung (chunk dài hơn ở vị trí ngang điểm được
   ưu tiên — nội dung giàu thông tin hơn).
4. **Đa dạng nguồn**: mỗi nguồn (URL) tối đa 1 chunk trong lượt chọn chính —
   tránh một website lấn hết top-k. Nếu chưa đủ `top_k`, vòng lấp đầy thứ hai
   cho phép trùng nguồn.
5. Giới hạn `RETRIEVAL_TOP_K` (mặc định 3, cấu hình được, đọc từ
   `settings.retrieval_top_k` trong `analyzer_node.py`).

**Vì sao đa dạng nguồn:** giải thích trả ra kèm `sources` — nếu mọi chunk
cùng một nguồn, người dùng thấy "1 nguồn lặp lại 3 lần" thay vì nhiều tham
chiếu độc lập.

---

## 5. Generation + Guardrail — grounding dùng chung

### Analyzer (`analyzer_node.py::process_single_indicator`)

```python
chunks = await _retrieve_optional_context(retriever, rag_semaphore,
                                           analyte_id, name, status)
rag_context = build_bounded_context(chunks, max_chars=settings.max_analyzer_context_chars)
context = rag_context or curated_explanation   # RAG optional — luôn có fallback
```

- Prompt nhận `context` bọc trong `<context>...</context>` +
  `GENERATION_SAFETY_CONTRACT` ở cuối prompt.
- LLM **chỉ được dùng thông tin trong context** — không chẩn đoán, không suy
  đoán nguyên nhân, không kê đơn.
- `sources` trả về **chỉ lấy từ metadata chunk hoặc catalog** — không bao giờ
  tin URL do LLM tự sinh ra (chặn hallucinated source).
- `ensure_reference_qualification()` chạy **sau** khi có kết quả LLM (hoặc
  fallback), đảm bảo câu ranh giới trạng thái (vd "nằm trong khoảng tham
  chiếu được hệ thống sử dụng") luôn có mặt — không thay nội dung LLM đã
  sinh, chỉ chèn thêm nếu thiếu.
- Nếu RAG không khả dụng (disabled, lỗi Chroma, embedding lỗi) →
  `_retrieve_optional_context` bắt exception, trả `[]`, `context` rơi về
  `curated_explanation` (dữ liệu tĩnh có sẵn) — **pipeline không bao giờ sập
  vì RAG**.

### Guardrail (`guardrail_node.py`)

- `MedicalSafetyValidator` (regex + intent-rule cục bộ, không cần LLM) kiểm
  tra mọi văn bản hiển thị cho người dùng (summary, explanation, tên chỉ số,
  câu hỏi cho bác sĩ, disclaimer).
- Nếu vi phạm → 1 lần rewrite bằng LLM, prompt gồm:
  - Yêu cầu thủ tục riêng của guardrail (giữ thông tin có trong context, bỏ
    chẩn đoán, không suy đoán nguyên nhân, không thêm kiến thức mới, chỉ trả
    về đoạn đã sửa).
  - `GENERATION_SAFETY_CONTRACT` — **cùng văn bản với analyzer**, import từ
    `medical_safety_assets.py`, không viết tay lại.
  - Context grounding lấy từ `retrieved_contexts` đã lưu trong state (lọc
    theo `indicator_name`, giới hạn bằng `max_guardrail_context_chars`) —
    **không gọi lại RAG**.
- Output rewrite phải pass lại `MedicalSafetyValidator`; nếu vẫn vi phạm hoặc
  rỗng → rơi về template an toàn cố định (`templates.fallback_explanation`).
- Nếu rewrite pass validator → `ensure_reference_qualification()` chạy lại
  trên kết quả rewrite (cùng hàm dùng ở analyzer) — đảm bảo LLM rewrite không
  vô tình làm mất câu ranh giới trạng thái đã có.
- Nếu LLM guardrail không khả dụng (lỗi tải model) → rơi thẳng về template an
  toàn, không thử rewrite mù.

**Vì sao RAG gắn với guardrail:** rewrite bằng LLM mà không có grounding sẽ
tự bịa lại nội dung. Dùng chung `retrieved_contexts` với analyzer đảm bảo nội
dung sửa lại vẫn bám đúng tài liệu đã tin cậy — không tạo ra một nguồn sự
thật thứ hai.

### Context budget (`context_budget.py::build_bounded_context`)

Cả 3 nơi nối context (analyzer, guardrail `grounding_context_for`, guardrail
`summary_context`) đều đi qua hàm này:

- Nối các chunk theo thứ tự đã xếp hạng cho tới khi chạm `max_chars`.
- **Không bao giờ cắt giữa một chunk** — chunk hoặc được giữ nguyên vẹn hoặc
  bị bỏ hoàn toàn.
- Chunk đầu tiên (liên quan nhất) luôn được giữ dù một mình nó đã vượt ngân
  sách — tránh trường hợp context rỗng hoàn toàn vì ngân sách quá nhỏ.

`RetrievedChunk` (kiểu dữ liệu lưu trong `state.retrieved_contexts`):
`{indicator_name, text, source, sources, score, note_type}`.

---

## 6. Vì sao chọn công nghệ / thiết kế này

| Quyết định | Vì sao (so với phương án khác) |
| --- | --- |
| **ChromaDB + metadata filter (`where`)** | Corpus nhỏ (81 chunk, 9 analyte hiện tại) nên không cần hệ vector đắt đỏ; Chroma hỗ trợ lọc metadata trước khi search — nền tảng cho kênh deterministic |
| **Gemini embeddings (API ngoài, có cả nhánh OpenAI)** | Không tải model embedding local: giảm RAM/cold-start khi deploy, không cần GPU. `EMBEDDING_PROVIDER` cấu hình được (`disabled`/`openai`/`gemini`) |
| **2 kênh song song (metadata + dense)** | Metadata-prong chính xác tuyệt đối nhưng phụ thuộc dữ liệu ingest đầy đủ; dense-prong linh hoạt nhưng có thể lệch chủ đề → kết hợp cả hai, không tin tuyệt đối một kênh |
| **Metadata score = length-taper + cross-check ngữ nghĩa (không phải 1.0 cứng)** | Tránh một nhãn đúng nhưng nội dung nghèo nàn/lạc đề luôn thắng một dense-hit giàu nội dung — bài học từ review kiến trúc, sửa 2 lần sau khi length-taper một mình bị chỉ ra là chưa đủ (độ dài ≠ chất lượng) |
| **Chỉ dedup exact-text, KHÔNG fuzzy content-dedup** | Từng dùng containment-matching (ngưỡng 0.6) để gộp "chunk trùng ý" — bị bỏ vì không phân biệt tin cậy được giữa "cùng ý khác chữ" và "khác nguyên nhân chung tiền tố câu"; rủi ro xóa oan tài liệu cao hơn lợi ích gọn context |
| **Relevance gate (`score ≥ RETRIEVAL_MIN_SCORE=0.8`)** | RAG là enrichment, không phải nguồn tin cậy duy nhất — chặn rác trước khi vào LLM, rơi về curated explanation khi retrieval yếu. 0.8 đo bằng thực nghiệm (adversarial test 3 miền), không phải đoán — xem `retrieval-min-score-evidence.md` |
| **`RetrievedChunk` lưu vào state, dùng lại cho guardrail** | Một lần retrieve dùng cho cả generation lẫn guardrail grounding — không gọi lại RAG ở guardrail, đảm bảo cùng một nguồn tài liệu cho cả sinh văn lẫn sửa văn |
| **`medical_safety_assets.py` dùng chung** | `GENERATION_SAFETY_CONTRACT`/`STATUS_QUALIFIERS`/`ensure_reference_qualification` là văn bản an toàn y tế — nếu để mỗi node viết tay một bản sẽ drift khi sửa một bên mà quên bên kia (rủi ro cao hơn bug thường vì liên quan an toàn) |
| **Context budget (char-based, không cắt giữa chunk)** | Đơn giản, không cần thêm dependency đo token; đủ để chặn context tràn ra prompt trong khi vẫn giữ câu văn trọn vẹn |

---

## 7. Cấu hình liên quan (`src/config.py`, `.env.example`)

| Biến | Mặc định | Ý nghĩa |
| --- | --- | --- |
| `RAG_ENABLED` | `false` (env dev đang bật `true`) | Bật/tắt RAG toàn bộ |
| `RAG_COLLECTION_NAME` | `medical_kb_v2` | Tên collection Chroma (versioned — không trộn embedding giữa các version) |
| `RAG_CORPUS_VERSION` | `medical-kb-v2` | Ghi vào metadata collection, đối chiếu khi mở lại collection |
| `EMBEDDING_PROVIDER` | `disabled` | `disabled` / `openai` / `gemini` |
| `EMBEDDING_MODEL_NAME`, `EMBEDDING_DIMENSION`, `EMBEDDING_TIMEOUT_SECONDS` | — | Cấu hình model embedding |
| `RETRIEVAL_MIN_SCORE` | `0.8` | Ngưỡng relevance gate. **Giá trị này được chứng minh bằng thực nghiệm, không phải đoán** — xem đầy đủ cách đo, số liệu và giới hạn tại **`docs/version-handoff/retrieval-min-score-evidence.md`** (tóm tắt: sàn điểm nội dung thật đo được là 0.807 trên 3 miền độc lập, 0.8 là ngưỡng an toàn tối đa trước khi bắt đầu mất nội dung thật) |
| `RETRIEVAL_TOP_K` | `3` | Số chunk tối đa trả về mỗi lần retrieve |
| `METADATA_PRONG_ENABLED` | `true` | Bật/tắt kênh metadata |
| `METADATA_MIN_CHUNK_LENGTH` | `30` | Chunk ngắn hơn ngưỡng này (sau khi bỏ dấu) bị loại khỏi candidate pool |
| `MAX_ANALYZER_CONTEXT_CHARS` | `4000` | Ngân sách context cho prompt sinh giải thích |
| `MAX_GUARDRAIL_CONTEXT_CHARS` | `3000` | Ngân sách context cho prompt rewrite của guardrail |

`VectorStore` kiểm tra metadata collection (`embedding_provider`,
`embedding_model`, `embedding_dimension`, `corpus_version`, `schema_version`)
mỗi lần mở collection — nếu không khớp cấu hình hiện tại thì raise lỗi ngay,
bắt buộc tạo collection version mới thay vì âm thầm trộn vector từ 2 model
khác nhau.

---

## 8. Giới hạn đã biết / việc chưa làm

- **Reranking / Context Compression bậc cao** — chưa triển khai (nhận xét
  kiến trúc liệt kê đây là gợi ý tùy chọn, cần cân nhắc chi phí thêm). Context
  budget hiện tại (mục 5) là giải pháp cơ bản đủ dùng cho corpus hiện tại.
- **Cross-check ngữ nghĩa không bắt được nội dung sai nhưng viết trôi chảy,
  đúng chủ đề** (vd "WBC tăng cao là bình thường, không cần lo") hoặc nội
  dung nhồi từ khóa — cả 2 loại này đo được điểm **cao hơn** cả sàn nội dung
  thật ở mọi miền đã test, nên không ngưỡng nào chặn được mà không giết nhầm
  nội dung thật. Đây là giới hạn cấu trúc, không phải lỗ hổng cần tinh chỉnh
  thêm — lớp chặn thật sự cho việc này là `GENERATION_SAFETY_CONTRACT` +
  `MedicalSafetyValidator` ở guardrail. Chi tiết:
  `docs/version-handoff/retrieval-min-score-evidence.md`.
- **`hba1c/critical_high` có biên an toàn mỏng** so với ngưỡng 0.8 (chỉ cách
  ~0.005-0.006) — không nguy hiểm (rơi về fallback vẫn an toàn) nhưng nên
  theo dõi khi đổi embedding model hoặc cách viết query.
- **LLM sinh chính (`get_llm()` trong `src/services/llm.py`) vẫn dùng
  OpenAI** — tài liệu review trước từng đề xuất chuyển sang Gemini
  (`gemini-3.5-flash-lite`) nhưng chưa áp dụng cho generation chính (chỉ
  embedding đã chuyển được sang Gemini). Trong môi trường dev hiện tại key
  OpenAI là placeholder nên pipeline luôn rơi về curated fallback khi test.
