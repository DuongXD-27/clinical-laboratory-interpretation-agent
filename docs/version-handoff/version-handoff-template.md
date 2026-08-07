# Version Handoff Template — VMEC-05

Dùng file này theo 2 bước mỗi chu kỳ 3-4 ngày: **chốt version cũ** → **mở version mới**.

---

## BƯỚC 1 — Cuối mỗi version, gõ prompt này vào chat đang làm

```
Tóm tắt version này theo đúng format Version Handoff sau, dựa trên toàn bộ 
nội dung đã trao đổi trong chat này. Chỉ điền thông tin có thật đã được 
chốt/trao đổi, không suy đoán thêm:

## VERSION [số] — [ngày bắt đầu] đến [ngày kết thúc]

### Mục tiêu ban đầu
(mục tiêu đề ra khi bắt đầu version này)

### Đã hoàn thành
- ...

### Quyết định kỹ thuật đã chốt
(kiến trúc, thư viện, cấu trúc node/agent, format dữ liệu... đã quyết định 
và LÝ DO — để version sau không hỏi lại hoặc đổi ý vô căn cứ)
- ...

### Vấn đề còn mở / chưa giải quyết
- ...

### Rủi ro cần lưu ý ở version tiếp theo
- ...

### Trạng thái ràng buộc an toàn (guardrail)
(guardrail chống chẩn đoán/điều trị, cảnh báo giá trị nguy kịch, bảo mật PHI 
— đang ở mức nào: chưa có / prompt-level / có validator riêng...)

### PLO đã chạm trong version này
(liệt kê PLO 1-8 nào được thể hiện, mức độ nông/sâu)

### Việc ưu tiên cho version tiếp theo
- ...
```

---

## BƯỚC 2 — Lưu bản tóm tắt vừa nhận được

1. Copy kết quả Claude trả về ở Bước 1.
2. Dán nối tiếp vào cuối file `changelog.md` (tạo file này trong Knowledge 
   của Project nếu chưa có), theo thứ tự Version 0, 1, 2...
3. Upload/cập nhật lại `changelog.md` vào Knowledge của Project.

Việc này giúp Claude ở các chat sau có thể tra cứu lại lịch sử quyết định 
qua Knowledge, kể cả khi bạn không dán thủ công.

---

## BƯỚC 3 — Mở chat mới cho version tiếp theo, bắt đầu bằng prompt này

```
Bắt đầu Version [số mới] của VMEC-05. Đây là bản tóm tắt version liền trước:

[dán bản Version Handoff vừa lưu ở Bước 2]

Mục tiêu version này: [mô tả ngắn nếu có ý tưởng, hoặc để trống nhờ Claude 
đề xuất scope 3-4 ngày dựa trên "Việc ưu tiên cho version tiếp theo" ở trên]
```

---

## Lưu ý khi dùng

- Không cần làm bước này nếu version chưa xong hẳn — chỉ chốt khi thực sự 
  chuyển sang giai đoạn tiếp theo.
- Nếu 1 version bị dở dang (hết 3-4 ngày nhưng chưa xong), vẫn nên chốt 
  handoff bình thường — ghi rõ phần dở dang vào "Vấn đề còn mở", đừng cố 
  nhồi hết vào 1 chat cho gọn.
- Phần "Quyết định kỹ thuật đã chốt" là quan trọng nhất — đây là thứ hay bị 
  quên và dẫn đến việc version sau làm lại/đổi hướng không cần thiết.