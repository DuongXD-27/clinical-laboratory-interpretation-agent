# RETRIEVAL_MIN_SCORE = 0.8 — evidence, not a guess

Nhận xét kiến trúc RAG (`nhan-xet-rag.docx`) chỉ ra: *"Chốt cứng
RETRIEVAL_MIN_SCORE = 0.3 và top_k = 3 mà chưa có chứng minh, rủi ro cao.
Không được mò các tham số quan trọng nhất của RAG."* Tài liệu này là chứng
minh cho giá trị `RETRIEVAL_MIN_SCORE` hiện tại (0.8), thay cho giá trị cũ
(0.3) — không đoán, có số liệu tái tạo được.

## Vì sao không thể chứng minh chỉ bằng corpus thật

`eval/rag/retrieval_param_sweep.py` sweep `min_score` từ 0.0 đến 0.5 trên
toàn bộ corpus thật (9 chỉ số, 35 tổ hợp trạng thái) — kết quả **giống hệt
nhau ở mọi mức**, vì điểm thấp nhất từng quan sát được trên corpus (nội dung
biên soạn thủ công, không nhiễu) là 0.764. Ngưỡng chưa từng "cắt" được gì vì
chưa có ứng viên nào đủ tệ để bị cắt — **không thể suy ra một giá trị tối ưu
từ một corpus không có rác**.

## Phương pháp: tạo rác thật, đo điểm thật

`eval/rag/adversarial_threshold_test.py` (chạy embedding thật, không mock)
chèn các đoạn văn rác được gắn nhãn **đúng** (`analyte_id` + `note_type`
khớp — nghĩa là sẽ lọt qua bước lọc metadata trong production) nhưng nội
dung sai/lạc đề/kém chất lượng, cạnh tranh trực tiếp với nội dung thật cho
**3 miền độc lập** (huyết học – WBC, thận – Creatinine, nội tiết – HbA1c) để
kết luận không bị lệ thuộc vào từ vựng của riêng 1 chỉ số.

9 loại rác được test: lạc đề hoàn toàn, sai chỉ số, nội dung chung chung
rỗng, gắn nhãn sai chiều (mislabeled), nhồi từ khóa, spam quảng cáo, khẳng
định sai/nguy hiểm về y tế, rác OCR, và nội dung ghép nửa đúng nửa sai.

## Kết quả (21 mẫu thật + 19 mẫu rác, 3 miền)

| | Khoảng điểm |
| --- | --- |
| Nội dung thật (3 miền) | [0.807, 0.903] — **sàn chung: 0.807** |
| Rác "bắt được" (7 loại × 3 miền) | tối đa **0.794** |
| Rác "không thể bắt" (2 loại × 3 miền: nhồi từ khóa, khẳng định sai) | từ **0.820** trở lên |

**Cửa sổ phân tách sạch: (0.794, 0.807)** — bất kỳ giá trị nào trong khoảng
này cho 0% mất nội dung thật + loại tối đa rác có thể loại được.

Quét toàn bộ ứng viên `min_score` qua 21 mẫu thật + 19 mẫu rác:

| min_score | Rác bị loại | Nội dung thật còn lại | Kết luận |
| --- | --- | --- | --- |
| 0.3 (giá trị cũ) | 0/19 | 21/21 | không lọc được gì |
| 0.5 | 1/19 | 21/21 | hầu như không lọc |
| 0.7 | 9/19 | 21/21 | lọc được nửa |
| 0.75 | 12/19 | 21/21 | lọc gần hết loại bắt được |
| **0.8** | **14/19** (100% loại bắt được) | **21/21** (0% mất) | **phân tách sạch** |
| 0.85 | 15/19 | 9/21 | **bắt đầu giết nhầm nội dung thật** |

0.8 là điểm **ngay dưới ngưỡng bắt đầu gây hại** (0.85 đã mất 12/21 nội dung
thật) — không phải chọn giữa khoảng an toàn một cách tùy tiện, mà chọn sát
biên trên để tối đa hóa khả năng lọc rác trong khi biên độ an toàn với nội
dung thật vẫn còn (0.807 > 0.8).

## Giới hạn đã biết — không phải lỗ hổng chưa vá, mà là giới hạn cấu trúc

2 loại rác **không thể** bị bất kỳ ngưỡng nào chặn, vì điểm của chúng cao
hơn cả sàn nội dung thật ở **cả 3 miền**:

- **Nhồi từ khóa** (`keyword_stuffed`) — lặp lại đúng từ khóa nhiều lần,
  gần như không có nội dung thật. Điểm: 0.90 (WBC), 0.97 (Creatinine), 0.87
  (HbA1c).
- **Khẳng định sai/nguy hiểm nhưng viết trôi chảy, đúng chủ đề**
  (`contradictory_dangerous`) — ví dụ "WBC tăng cao là bình thường, không
  cần lo lắng". Điểm: 0.83 (WBC), 0.91 (Creatinine), 0.79 (HbA1c).

**Lý do:** cosine similarity đo "câu này có nói cùng chủ đề với câu hỏi
không" — không đo "câu này có đúng sự thật không". Một câu sai hoàn toàn về
y khoa nhưng đúng từ vựng, đúng ngữ pháp, đúng chủ đề vẫn "giống nghĩa" với
câu hỏi. **Đây không phải khoảng trống cần tinh chỉnh thêm tham số** — nó là
lý do vì sao `GENERATION_SAFETY_CONTRACT` (hợp đồng an toàn khi sinh câu
trả lời) và `MedicalSafetyValidator` (kiểm tra nội dung câu khẳng định ở
guardrail) tồn tại như lớp bảo vệ độc lập, không phụ thuộc vào retrieval
score. Retrieval score chỉ là bộ lọc **độ liên quan**, không bao giờ được
coi là bộ lọc **an toàn/đúng sự thật**.

## Rủi ro dư (đã quan sát khi verify, chưa xảy ra thật)

Sau khi đổi sang 0.8, verify lại pipeline thật (`analyzer_node`, query đúng
format production `"Ý nghĩa xét nghiệm {name} khi kết quả ở mức {status}"`)
phát hiện 2 điều đáng ghi chú:

1. **Metadata-prong không còn hoàn toàn miễn nhiễm với cách diễn đạt câu
   hỏi.** Trước khi có cross-check ngữ nghĩa, kênh metadata luôn cho điểm
   1.0 bất kể query viết thế nào (chỉ dựa vào nhãn). Giờ điểm phụ thuộc một
   phần vào embedding của câu hỏi — dùng query quá chung chung (không nêu
   tên chỉ số) có thể làm giảm điểm dù nhãn khớp hoàn toàn đúng. Đã test
   với query đúng format production thì không sao (mục trên), nhưng đây là
   một trade-off có thật của việc thêm cross-check, cần nhớ khi đổi cách
   dựng câu query trong `analyzer_node.py`.
2. **`hba1c/critical_high` có biên an toàn rất mỏng**: điểm đo được là
   0.805–0.806, chỉ cách ngưỡng 0.8 khoảng 0.005–0.006. Nếu embedding model
   đổi version, hoặc cách viết câu hỏi thay đổi nhẹ, tổ hợp này có nguy cơ
   rơi xuống dưới ngưỡng và trigger fallback — không nguy hiểm (fallback về
   curated explanation vẫn an toàn) nhưng đáng theo dõi. Nên đưa
   `hba1c/critical_high` vào danh sách ưu tiên khi re-run
   `retrieval_param_sweep.py` sau này.

## Khi nào cần chạy lại

- Corpus thay đổi đáng kể (thêm nguồn ít kiểm soát chất lượng hơn, ví dụ
  crawl tự động thay vì biên soạn tay).
- Đổi embedding model/provider (`EMBEDDING_PROVIDER`, `EMBEDDING_MODEL_NAME`)
  — ranh giới điểm số là đặc thù theo model, không tổng quát hóa được sang
  model khác.
- Đổi cách dựng câu query trong `analyzer_node.py`/`_status_query` — cross-check
  ngữ nghĩa phụ thuộc một phần vào cách diễn đạt câu hỏi (xem mục "Rủi ro dư").

```
python -m eval.rag.retrieval_param_sweep       # có rơi vào fallback không, trên corpus thật
python -m eval.rag.adversarial_threshold_test  # ranh giới phân tách rác/thật
```
