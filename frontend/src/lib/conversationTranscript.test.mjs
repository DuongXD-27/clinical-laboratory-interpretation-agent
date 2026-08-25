import assert from "node:assert/strict";
import { test } from "node:test";

import {
  conversationLabel,
  messagesToTurns,
  pickInitialConversation,
} from "./conversationTranscript.mjs";

const msg = (id, role, content, extra = {}) => ({
  id,
  role,
  content,
  created_at: "2026-08-25T10:00:00",
  ...extra,
});

test("ghép transcript thành từng lượt hỏi–đáp", () => {
  const turns = messagesToTurns([
    msg(1, "user", "Chỉ số WBC của tôi thế nào?"),
    msg(2, "assistant", "WBC cao hơn khoảng tham chiếu.", { intent: "EXPLAIN_CURRENT_RESULT" }),
    msg(3, "user", "Tôi nên làm gì?"),
    msg(4, "assistant", "Bạn nên trao đổi với bác sĩ."),
  ]);

  assert.equal(turns.length, 2);
  assert.equal(turns[0].userMessage, "Chỉ số WBC của tôi thế nào?");
  assert.equal(turns[0].restoredMessage, "WBC cao hơn khoảng tham chiếu.");
  assert.equal(turns[0].restoredIntent, "EXPLAIN_CURRENT_RESULT");
  assert.equal(turns[1].userMessage, "Tôi nên làm gì?");
  assert.ok(turns.every((turn) => turn.restored === true));
});

test("câu hỏi chưa có câu trả lời vẫn được giữ lại", () => {
  // Server ghi câu hỏi TRƯỚC khi xử lý, nên một lượt lỗi giữa đường để lại
  // đúng hình này. Bỏ nó đi là làm người dùng tưởng mình chưa từng hỏi.
  const turns = messagesToTurns([
    msg(1, "user", "Câu hỏi bị lỗi giữa đường"),
  ]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].userMessage, "Câu hỏi bị lỗi giữa đường");
  assert.equal(turns[0].restoredMessage, null);
});

test("câu trả lời không có câu hỏi đi trước không bị mất", () => {
  const turns = messagesToTurns([msg(9, "assistant", "Nội dung không được phép mất")]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].userMessage, "");
  assert.equal(turns[0].restoredMessage, "Nội dung không được phép mất");
});

test("hai câu trả lời liền nhau được nối, không bị bỏ", () => {
  const turns = messagesToTurns([
    msg(1, "user", "Một câu hỏi"),
    msg(2, "assistant", "Phần một"),
    msg(3, "assistant", "Phần hai"),
  ]);

  assert.equal(turns.length, 2);
  assert.equal(turns[0].restoredMessage, "Phần một");
  assert.equal(turns[1].restoredMessage, "Phần hai");
});

test("bỏ qua tin nhắn méo mó thay vì nổ", () => {
  const turns = messagesToTurns([
    null,
    { id: 1, role: "user" },
    msg(2, "user", "Câu hỏi thật"),
    msg(3, "assistant", "Trả lời thật"),
    { id: 4, role: "system", content: "Không thuộc hợp đồng" },
  ]);

  assert.equal(turns.length, 1);
  assert.equal(turns[0].userMessage, "Câu hỏi thật");
});

test("transcript rỗng cho ra danh sách rỗng", () => {
  assert.deepEqual(messagesToTurns([]), []);
  assert.deepEqual(messagesToTurns(undefined), []);
});

test("nhãn hội thoại: có tiêu đề thì dùng, không thì nhãn tạm", () => {
  assert.equal(conversationLabel({ title: "Hỏi về WBC" }), "Hỏi về WBC");
  assert.equal(conversationLabel({ title: "   " }), "Cuộc trò chuyện mới");
  assert.equal(conversationLabel({ title: null }), "Cuộc trò chuyện mới");
  assert.equal(conversationLabel(undefined), "Cuộc trò chuyện mới");
});

test("mở lại đúng hội thoại đang xem lần trước", () => {
  const list = [{ id: 7 }, { id: 4 }, { id: 2 }];
  assert.equal(pickInitialConversation(list, "4"), 4);
  assert.equal(pickInitialConversation(list, 2), 2);
});

test("id đã lưu nhưng không còn trong danh sách thì rơi về hội thoại mới nhất", () => {
  // Hội thoại đã bị xoá, hoặc id còn sót từ một tài khoản khác từng đăng nhập
  // trên máy này. Tin id đó là mở màn hình ra rồi báo 404.
  const list = [{ id: 7 }, { id: 4 }];
  assert.equal(pickInitialConversation(list, "999"), 7);
  assert.equal(pickInitialConversation(list, null), 7);
  assert.equal(pickInitialConversation(list, "không-phải-số"), 7);
});

test("danh sách rỗng trả null để lượt đầu tự tạo hội thoại ở server", () => {
  assert.equal(pickInitialConversation([], "4"), null);
  assert.equal(pickInitialConversation(undefined, "4"), null);
});
