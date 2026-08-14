# Version 3 Kickoff — VMEC-05 (bản cập nhật)

**Ngày bắt đầu:** 12:00 — 07/08/2026
**Ngày kết thúc:** 17:00 — 08/08/2026

---

## 0. Phụ lục điều chỉnh phạm vi — 07/08/2026

PO điều chỉnh `release/v3.0` để hoàn thiện ngay OCR confidence Review Gate, thay
cho quyết định dời sang V4 ở bản kickoff ban đầu. Lý do: OCR không được công bố
khi bước xác nhận mới chỉ tồn tại ở frontend và backend chưa thể cưỡng chế xác
nhận riêng cho confidence thấp.

- OCR được chốt là **Nâng cao nhưng làm sớm**, không đổi thành phạm vi Cơ bản.
- Bổ sung `/ocr/confirm`, review token ngắn hạn, xác nhận mọi dòng và xác nhận
  tăng cường khi confidence `< 0.7`.
- Patient Portal và Doctor Portal dùng chung UI Review.
- Guardrail validator chuyển sang kiểm tra tại chỗ Regex + luật ý định, giữ đúng
  một lượt LLM retry trước Template Library.
- Tài liệu quyết định: `docs/product-requirements/prd-v3.md` và ADR-007.

Phụ lục này có hiệu lực cao hơn các dòng cũ nói confidence gate “dời sang V4”.

---

## 1. Ràng buộc an toàn cố định

- TUYỆT ĐỐI KHÔNG chẩn đoán, không kết luận nguyên nhân, không đề nghị điều trị.
- Chỉ giải thích chỉ số LÀ GÌ và Ý NGHĨA CHUNG.
- Luôn khuyến cáo gặp bác sĩ. Grounded trên nguồn, chống bịa.
- Chỉ số nguy kịch phải cảnh báo khẩn, có gate xác nhận thủ công — **độc lập
  hoàn toàn với trạng thái approved/pending ở Reference Checker** (áp dụng
  cho CẢ Kali và LDL-C, xem mục 4.1).
- Bảo mật PHI. **KHÔNG dùng dữ liệu bệnh nhân thật dưới bất kỳ hình thức nào
  ở V3** — quyết định đạo đức, không phải kỹ thuật.
- **OCR public**: mở, kèm 4 lớp bảo vệ (consent gate chặn cứng + ảnh mẫu sẵn
  + không lưu ảnh gốc + feature flag) — xem phần quyết định phía trên. Dương
  xác nhận cuối trước khi công bố link.

---

## 2. Bản đồ trạng thái 9 chỉ số

| Chỉ số | Reference Checker | Critical Detector | RAG (explanations.json) | RAGAS |
|---|---|---|---|---|
| WBC | ✅ Approved | — | ✅ | ✅ đo |
| RBC | ✅ Approved | — | ✅ | ✅ đo |
| Glucose | ✅ Approved | ✅ `<3.0` hoặc `>27.8` | ✅ | ✅ đo |
| Creatinine | ✅ Approved | — | ✅ | ✅ đo |
| **Kali (Potassium)** | ⏳ Pending | ✅ `<2.5` hoặc `>6.5` | ✅ | ❌ loại |
| **LDL-C** | ⏳ Pending | ✅ `>4.91` | ✅ | ❌ loại |
| HGB | ⏳ Pending | — | ✅ | ❌ loại |
| HDL-C | ⏳ Pending | — | ✅ | ❌ loại |
| HbA1c | ⏳ Pending | — | ✅ | ❌ loại |

→ 4/9 approved hoàn toàn. 5/9 pending ở Reference Checker, nhưng **2 trong 5
(Kali, LDL-C) đã được Critical Detector bảo vệ độc lập** — đúng 2/3 chỉ số
cốt lõi từ đề bài gốc (Glucose, LDL-C, Kali).

---

## 3. Quyết định kiến trúc đã chốt (không đổi)

- Orchestration: LangGraph, guardrail luôn cuối cùng.
- Đơn vị đo: `mmol/L` toàn hệ thống.
- **Critical-Value Detection tách biệt hoàn toàn khỏi Reference Checker**
  (`adr-003`) — chính thiết kế này giúp Kali VÀ LDL-C vẫn cảnh báo khẩn được
  dù đang pending ở phần "normal reference". Không sửa kiến trúc này, chỉ
  verify bằng test ở mục 4.1.
- Guardrail: 3 lớp, Validator = Regex + Semantic Similarity + LLM Retry +
  Template Library. Embedding model sắp đổi (mục 5).
- RAG Rerank: đã chốt kỹ thuật LLM-based rerank (dùng lại Gemini Flash chấm
  điểm top-k thay vì thêm model nặng) — **chưa triển khai trong V3**, để
  dành V4.
- **MỚI — phát hiện kỹ thuật quan trọng**: `questions_for_doctor` truyền vào
  Guardrail luôn là `[]`. Nghĩa là toàn bộ đoạn code `rewrite_questions_with_llm()`
  trong `guardrail_node.py` chưa từng chạy thật — vì chưa có node nào sinh
  câu hỏi thật cả. Đây là **việc làm mới hoàn toàn** (greenfield), không phải
  "đã có sẵn 1 phần" như bản kickoff trước giả định. Ghi nhận là nợ kỹ
  thuật rõ ràng giữa lúc thiết kế state/guardrail và lúc thực thi node —
  không sửa trong V3 (vẫn là stretch goal, xem mục 6), nhưng khi làm ở
  version sau, Duy cần build node `generate_questions` từ đầu, không chỉnh sửa gì.

---

## 4. Mục tiêu & DoD của Version 3

### Ưu tiên #1 — Hoàn thiện trọn vẹn nhóm chỉ số máu (9/9), theo đúng thứ tự an toàn

**4.1. P0 — BẮT BUỘC LÀM TRƯỚC TIÊN: Test bảo vệ Critical Detector cho Kali + LDL-C**
- Viết/verify test xác nhận Critical Detector bắt đúng ngưỡng Kali
  (`<2.5`/`>6.5`) và LDL-C (`>4.91`) trong MỌI trường hợp, không phụ thuộc
  trạng thái pending ở Reference Checker.
- Đây là việc phải xong trước khi đụng vào bất kỳ thay đổi approve nào —
  bảo vệ đúng 2 chỉ số nguy kịch cốt lõi của đề bài gốc.

**4.2. P1 — Approve Kali + LDL-C ở Reference Checker (normal path)**
- Kali và LDL-C: sử dụng trực tiếp record đã được curate/import vào dataset
  canonical, đồng thời giữ nguyên kiểm tra unit và điều kiện áp dụng.
- Đây là 2/9 chỉ số quan trọng nhất vì vừa thuộc bộ 3 core V1, vừa có
  critical protection — ưu tiên cao hơn hẳn nhóm 4.3.

**4.3. P2 — Approve HGB, HDL-C, HbA1c (nếu còn thời gian sau 4.1+4.2)**
- Rủi ro an toàn thấp hơn (không có ngưỡng nguy kịch riêng, không ảnh
  hưởng Gate 3), nhưng cần thiết để đạt đúng nghĩa "trọn vẹn 9/9".
- Có thể chia song song 3 người/3 chỉ số cùng lúc — hợp với năng lực vibe
  coding của team.
- Nếu không kịp trong 29h: chấp nhận dừng ở 6/9 hoặc 7/9 approved, miễn
  4.1 và 4.2 đã xong — đây là kết quả tối thiểu chấp nhận được, không phải
  thất bại.

**4.4. Song song, không dồn cuối: Test case biên + cập nhật PRD**
- Mỗi chỉ số vừa approved → viết ngay test case biên (dưới/trong/trên
  ngưỡng), không đợi xong hết mới viết.
- PRD ghi rõ: chỉ Kali và LDL-C có mức "critical", còn lại (WBC, RBC, HGB,
  Glucose, HDL-C, HbA1c, Creatinine) chỉ có "abnormal".

### Ưu tiên #2 — Deploy mượt mà, ổn định qua link công khai

**4.5. Tách lookup chỉ số khỏi RAG và bỏ BGE-M3 khỏi API runtime** — khoảng
tham chiếu/trạng thái/critical dùng lookup xác định; RAG chỉ làm giàu tài liệu y khoa
phi cấu trúc qua embedding provider ngoài. Xem ADR-008. Thay đổi này xử lý gốc rễ
nguyên nhân crash Railway/Render free-tier mà không loại bỏ bằng chứng PLO3.

**4.6. Chốt URL production thật + CORS đúng domain** — cập nhật
`.env.example`/`README.md`.

**4.7. Triển khai 4 lớp bảo vệ OCR cho public** (theo quyết định đầu bài):
consent gate chặn cứng, ảnh mẫu sẵn có, không lưu ảnh gốc, feature flag.

**4.8. Smoke test bằng người ngoài thật** — không chỉ dev tự test localhost.

### Nếu còn thời gian (không bắt buộc, không chặn release)

- Unit Conversion (mg/dL ↔ mmol/L) — optional, cần Vũ review vì đụng schema.
- Bắt đầu build `generate_questions` node thật (greenfield, xem mục 3) —
  chỉ làm sau khi 2 ưu tiên chính chạy hoàn hảo, đúng ý bạn.
- Mở rộng RAGAS 12 test case sang các chỉ số mới approved, nếu 4.3 xong sớm.

---

## 5. Phạm vi KHÔNG làm ở version này

- Không tự động bỏ qua review cho OCR confidence cao. Confidence-based gate đã
  được đưa vào V3 theo phụ lục mục 0; mọi dòng vẫn phải được xác nhận thủ công.
- Không đo RAGAS production RAG, không triển khai RAG rerank thật (đã chốt
  kỹ thuật, chưa code).
- Không làm Memory/checkpointer, HITL bác sĩ ghi chú, đa ngôn ngữ.
- Không chuyển guardrail sang LLM-as-judge.
- Không nhận/lưu dữ liệu bệnh nhân thật dưới bất kỳ hình thức nào.
- Không xây pipeline PHI de-identification đầy đủ (chọn hướng chặn dữ liệu
  thật bằng consent + ephemeral storage thay vì xây de-id ngay bây giờ).

---

## 6. Known issues đang cố ý để đó

- PHI de-identification pipeline chưa xây — chấp nhận được vì đã chặn dữ
  liệu thật bằng 4 lớp bảo vệ OCR (mục 4.7), không phải bỏ ngỏ.
- `questions_for_doctor` luôn rỗng, code rewrite trong guardrail chưa từng
  chạy thật — xác nhận là việc làm mới hoàn toàn, để dành sau khi 2 ưu
  tiên chính V3 xong.
- Nếu 4.3 (HGB/HDL-C/HbA1c) không kịp trong 29h: chấp nhận pending tiếp,
  miễn 4.1+4.2 đã xong.
- RAG rerank đã chốt kỹ thuật, chưa triển khai — dời V4.
- Unit Conversion — lần dời thứ 3 nếu không kịp làm, cần mốc cứng ở V4.
- Hybrid OCR giảm rủi ro nhưng không loại bỏ hoàn toàn khả năng người dùng
  cố ý tải ảnh thật — rủi ro tồn dư đã được nêu rõ, chấp nhận có ý thức,
  không phải bị bỏ sót.

---

## 7. Phân công Version 3

| Thành viên | Việc chính |
|---|---|
| **Dương** | 4.1 (test bảo vệ Critical Detector Kali+LDL-C, làm đầu tiên); duyệt ADR nếu nới tiêu chí LDL-C (4.2); đổi embedding model (4.5, phối hợp Duy); xác nhận cuối chính sách OCR public (4.7) |
| **Vũ** | Review mọi thay đổi graph/state phát sinh từ việc approve 5 chỉ số; review Unit Conversion nếu làm; giữ quyền quyết định RAG rerank (đã chốt, chưa triển khai) |
| **Tuấn** | 4.2 (xử lý nguồn dữ liệu Kali+LDL-C); 4.3 (xử lý HGB/HDL-C/HbA1c song song); 4.4 (test case biên + PRD) |
| **Duy** | 4.5 (đổi embedding, phối hợp Dương); 4.6 (URL+CORS); 4.7 (build consent gate + ephemeral storage + feature flag); 4.8 (smoke test); nếu còn giờ: bắt đầu `generate_questions` thật |

---
