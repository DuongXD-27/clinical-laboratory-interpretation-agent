# Version Kickoff Template — VMEC-05

Dùng đầu mỗi version, dán vào tin nhắn ĐẦU TIÊN khi mở chat mới với AI 
(chat thường hoặc AI coding). Đi cặp với `version-handoff-template.md` 
(dùng cuối version). Không cần dán hết nếu chat AI coding đã đọc được 
trực tiếp các file trong repo (`docs/architecture/`, `explanations.json`...) 
— nhưng vẫn nên dán phần 1 (ràng buộc an toàn) dù AI có đọc được file, vì 
đây là phần không được phép hiểu sai.

---

## Prompt mẫu — dán nguyên khối này

```
Bắt đầu Version [số] của VMEC-05.

## 1. Ràng buộc an toàn cố định (không đổi qua các version — luôn tuân thủ)
- TUYỆT ĐỐI KHÔNG chẩn đoán bệnh, không kết luận nguyên nhân gây ra chỉ số 
  bất thường, không đề nghị điều trị/kê đơn.
- Chỉ giải thích chỉ số LÀ GÌ và Ý NGHĨA CHUNG — không suy đoán lý do 
  (cấm các cụm như "có thể do", "nguyên nhân do", "thường liên quan đến").
- Luôn khuyến cáo trao đổi trực tiếp với bác sĩ để được diễn giải chính xác.
- Grounded trên nguồn có thật, chống bịa (hallucination) — không tự sinh 
  thông tin y khoa ngoài nguồn RAG.
- Chỉ số nguy kịch (Kali, đường huyết cực đoan...) phải kích hoạt cảnh báo 
  khẩn riêng biệt, có gate xác nhận thủ công.
- Bảo mật PHI — không để lộ thông tin định danh bệnh nhân.

## 2. Bản Handoff version liền trước
[dán nguyên bản Version Handoff đã lưu trong changelog.md]

## 3. Quyết định kiến trúc đã chốt (không tự ý đổi)
- LangGraph để orchestrate, không dùng agent tự do kiểu ReAct — xem 
  ADR-001-vi-sao-dung-langgraph.md
- Đơn vị đo chuẩn mmol/L toàn hệ thống — xem ADR-002-he-don-vi-do.md
- Schema state hiện tại: [dán state.py hoặc link file]

## 4. Mục tiêu & DoD của version này
[mô tả ngắn, hoặc để trống nhờ AI đề xuất dựa trên "Việc ưu tiên cho 
version tiếp theo" trong bản Handoff ở mục 2]

## 5. Phạm vi KHÔNG làm ở version này
[liệt kê rõ — vd: "Không code OCR, không code memory/trend dù có thời 
gian dư — để dành version sau"]

## 6. Known issues đang cố ý để đó (không phải bug bị bỏ sót)
[copy từ mục "Vấn đề còn mở" trong bản Handoff — vd: "Chưa có unit 
conversion — quyết định có chủ đích, không phải thiếu sót"]

## 7. Bản đồ code hiện tại (nếu AI chưa đọc được repo trực tiếp)
[liệt kê ngắn gọn file/folder chính và chức năng — vd: 
`src/agents/graph.py` = luồng chính, `src/agents/nodes/` = từng node, 
`data/reference/` = bảng tham chiếu + ngưỡng nguy kịch]

## 8. Phân công (điền SAU khi đã thảo luận với team — không cần biết trước khi bắt đầu kickoff)
[bảng: Ai — làm gì trong version này — do đâu quyết định (vd theo DoD 
mục 4, hoặc theo "việc ưu tiên" từ bản Handoff mục 2)]
```

---

## Phân công được ghi ở đâu

**Không tạo file riêng cho phân công.** Cách dùng đúng:

1. `version-kickoff-template.md` (file này) — là khuôn rỗng, dùng lại mãi 
   mãi, không sửa nội dung vào đây.
2. Đầu mỗi version, copy khuôn này thành 1 file mới đặt tên theo version 
   (vd `v2-kickoff.md`, `v3-kickoff.md`), điền đầy đủ mục 1-7, thảo luận 
   với team để chốt mục 8 (Phân công), rồi lưu lại.
3. Bản đã điền đó (`v2-kickoff.md`...) chính là nơi lưu phân công của 
   version đó — gộp chung với ràng buộc, DoD, phạm vi trong cùng 1 file, 
   không cần tách riêng "file phân công" và "file ngữ cảnh".

Muốn tra "V2 ai làm gì" sau này → mở đúng `v2-kickoff.md`, không cần lục 
lại cả cuộc trò chuyện.

---

## Vì sao mục 1 phải nhắc lại mỗi lần, kể cả khi "không đổi"

AI không giữ trí nhớ giữa các phiên chat — mỗi chat mới coi như AI "quên 
sạch" mọi ràng buộc đã thống nhất trước đó, kể cả khi bạn tin nó đã hiểu 
rõ. Với phần khác (kiến trúc, phân công), quên rồi hỏi lại chỉ tốn thời 
gian. Nhưng với ràng buộc an toàn, quên rồi không nhắc lại có thể dẫn đến 
AI viết ra nội dung vi phạm ngay từ đầu version mới — nên đây là phần 
**duy nhất bắt buộc dán lại y nguyên**, không rút gọn, không diễn giải lại 
bằng lời khác dù đã quen thuộc.

## Khi nào bỏ bớt phần nào

- Nếu dùng AI coding có quyền đọc trực tiếp repo (Claude Code, Cursor...): 
  có thể bỏ mục 7 (bản đồ code) vì AI tự đọc được cấu trúc thư mục — nhưng 
  vẫn nên giữ mục 1, 3, 5, 6 vì đây là *quyết định*, không phải *thông tin 
  có thể suy ra từ code*.
- Nếu version mới chỉ là fix bug nhỏ, không phải mở version chính thức: 
  không cần dùng cả template này, chỉ cần nhắc mục 1 là đủ.