/** Dựng lại các lượt hội thoại từ transcript đã lưu.
 *
 * Đặt ở `lib/*.mjs` để `node --test` chạy được mà không cần dựng cả React —
 * đúng quy ước sẵn có của repo cho phần logic thuần.
 *
 * ## Vì sao lượt được dựng lại chỉ có văn bản
 *
 * Server lưu `content` (văn bản đã qua guardrail) kèm `intent` / `reason_code` /
 * `data_type`, chứ KHÔNG lưu nguyên payload có cấu trúc. Đây là lựa chọn có chủ
 * ý, đánh đổi một cách rõ ràng:
 *
 * - Lưu nguyên payload JSON là nhân đôi giá trị xét nghiệm sang một chỗ nữa,
 *   trong khi `report_indicators` đã giữ chúng.
 * - Schema payload có `extra="forbid"`. Một payload lưu từ bản cũ, sau khi
 *   schema đổi, sẽ không validate được nữa — và cả cuộc trò chuyện thành không
 *   mở được. Văn bản thì không bao giờ hết hạn.
 *
 * Cái mất: lượt dựng lại không có nút hành động và không có khối chỉ số. Đó là
 * giới hạn đã biết, không phải lỗi — và nó nằm đúng chỗ nên nằm: người dùng đọc
 * lại được mọi thứ đã hiện ra, chỉ không bấm lại được nút của lượt cũ.
 */

/** Ghép các tin nhắn phẳng thành từng lượt hỏi–đáp.
 *
 * Transcript là một dãy tin nhắn theo thứ tự id. Server ghi câu hỏi TRƯỚC khi
 * xử lý, nên một lượt lỗi giữa đường để lại tin nhắn `user` mà không có
 * `assistant` theo sau. Hàm này giữ nguyên lượt đó thay vì bỏ đi: người dùng
 * cần thấy mình đã hỏi gì.
 *
 * Hai tin `assistant` liền nhau (không nên xảy ra, nhưng dữ liệu cũ thì không
 * ai bảo đảm) được ghép vào lượt đang mở chứ không bị bỏ. Nguyên tắc: đọc
 * transcript không được làm mất chữ nào.
 */
export function messagesToTurns(messages) {
  const turns = [];
  let current = null;

  for (const message of messages ?? []) {
    if (!message || typeof message.content !== "string") continue;

    if (message.role === "user") {
      current = {
        id: `restored-${message.id}`,
        requestId: `restored-${message.id}`,
        userMessage: message.content,
        deliveryState: "COMPLETED",
        createdAt: message.created_at ?? new Date(0).toISOString(),
        retryable: false,
        restored: true,
        restoredMessage: null,
        restoredIntent: null,
      };
      turns.push(current);
      continue;
    }

    if (message.role !== "assistant") continue;

    if (current === null) {
      // Câu trả lời không có câu hỏi đi trước. Vẫn hiển thị, với phần hỏi để
      // trống — thà thấy một lượt lệch còn hơn mất nội dung.
      current = {
        id: `restored-${message.id}`,
        requestId: `restored-${message.id}`,
        userMessage: "",
        deliveryState: "COMPLETED",
        createdAt: message.created_at ?? new Date(0).toISOString(),
        retryable: false,
        restored: true,
        restoredMessage: null,
        restoredIntent: null,
      };
      turns.push(current);
    }

    current.restoredMessage =
      current.restoredMessage === null
        ? message.content
        : `${current.restoredMessage}\n\n${message.content}`;
    current.restoredIntent = message.intent ?? current.restoredIntent;
    current = null;
  }

  return turns;
}

/** Nhãn hiển thị cho một hội thoại trong danh sách.
 *
 * Tiêu đề do server đặt từ câu hỏi đầu tiên. Hội thoại chưa có lượt nào thì
 * chưa có tiêu đề — hiện nhãn tạm chứ không hiện chuỗi rỗng, vì một dòng trống
 * trong danh sách trông như lỗi tải.
 */
export function conversationLabel(conversation) {
  const title = conversation?.title;
  if (typeof title === "string" && title.trim() !== "") return title.trim();
  return "Cuộc trò chuyện mới";
}

/** Chọn hội thoại để mở khi vừa vào trang.
 *
 * Ưu tiên hội thoại người dùng đang mở lần trước (id lưu ở localStorage), và
 * chỉ khi id đó CÒN trong danh sách. Không kiểm lại thì một hội thoại đã bị
 * xoá, hoặc id còn sót từ một tài khoản khác từng đăng nhập trên máy này, sẽ
 * làm màn hình mở ra rồi báo 404.
 *
 * Không có gì hợp lệ thì mở hội thoại mới nhất. Trả `null` khi danh sách rỗng —
 * lúc đó lượt đầu tiên sẽ tự tạo hội thoại ở phía server.
 */
export function pickInitialConversation(conversations, storedId) {
  const list = Array.isArray(conversations) ? conversations : [];
  if (list.length === 0) return null;

  const parsed = typeof storedId === "string" ? Number.parseInt(storedId, 10) : storedId;
  if (Number.isInteger(parsed) && list.some((item) => item?.id === parsed)) {
    return parsed;
  }
  return list[0]?.id ?? null;
}
