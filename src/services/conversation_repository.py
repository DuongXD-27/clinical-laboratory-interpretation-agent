"""Đọc và ghi hội thoại — nơi duy nhất enforce quyền sở hữu.

## Quy tắc bất di bất dịch của module này

**Mọi hàm đọc hoặc ghi đều nhận `patient_id` tường minh.** Không hàm nào tra
Conversation chỉ bằng `conversation_id`. Cùng khuôn với `history_repository`, và
vì cùng một lý do: nếu tồn tại một hàm `get(conversation_id)` không kèm chủ sở
hữu thì sớm muộn có route gọi nó và quên lọc, rồi bệnh nhân A đọc được hội thoại
của bệnh nhân B.

`patient_id` **luôn** đến từ `current_user.user_id`, tức từ claim `uid` trong JWT
đã kiểm chữ ký ở `get_current_user`. Không bao giờ từ thân request.

**Không tìm thấy trả về `None`, và route dịch thành 404 — không phải 403.** 403
xác nhận rằng id đó có tồn tại, đủ để dò ra hội thoại của người khác bằng cách
thử id. Đây là quy tắc đã áp cho `/history` và giữ nguyên ở đây.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from src.models.db import Conversation, ConversationMessage

logger = logging.getLogger(__name__)

ROLE_USER = "user"
ROLE_ASSISTANT = "assistant"

# Tiêu đề rút từ câu hỏi đầu tiên, cắt ở đây chứ không ở giao diện: danh sách
# hội thoại hiển thị ở nhiều chỗ và cắt mỗi nơi một kiểu thì nhìn lệch nhau.
TITLE_MAX_CHARS = 60


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def create_conversation(db: Session, *, patient_id: int, title: str | None = None) -> Conversation:
    """Mở một hội thoại mới với context RỖNG.

    Đây chính là cơ chế của New Chat. Không có bước "xoá context cũ" nào cả —
    hàng mới sinh ra đã không có `current_analyte`, không có `pending_question`.
    Cách này không hỏng được, khác với việc phải nhớ gọi một hàm reset.

    **Một ngoại lệ, và chỉ một: `onboarding_acknowledged` được kế thừa.**

    Không phải cho tiện. Xác nhận "tôi đã đọc hướng dẫn" là thuộc tính của
    NGƯỜI, còn `current_analyte` là thuộc tính của CUỘC TRÒ CHUYỆN — hai thứ
    khác loại nên vòng đời khác nhau. Bắt bệnh nhân bấm lại "Tôi đã hiểu" mỗi
    lần mở hội thoại mới là biến một lời cam kết an toàn thành một cái nút phải
    bấm cho qua, tức là làm nó mất tác dụng. Ngược lại, kế thừa ngữ cảnh y khoa
    thì trực tiếp gây trả lời sai — đó mới là thứ phải chặn.
    """

    inherited = _has_acknowledged_onboarding(db, patient_id=patient_id)
    conversation = Conversation(
        patient_id=patient_id,
        title=title,
        onboarding_acknowledged=inherited,
    )
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _has_acknowledged_onboarding(db: Session, *, patient_id: int) -> bool:
    """Bệnh nhân này đã từng xác nhận hướng dẫn trong bất kỳ hội thoại nào chưa.

    Một truy vấn EXISTS chứ không tải cả danh sách: câu hỏi chỉ là có/không, và
    hàm này chạy ở mỗi lần bấm New Chat.
    """

    return bool(
        db.execute(
            select(Conversation.id)
            .where(Conversation.patient_id == patient_id)
            .where(Conversation.onboarding_acknowledged.is_(True))
            .limit(1)
        )
        .scalars()
        .first()
    )


def get_conversation(db: Session, *, conversation_id: int, patient_id: int) -> Conversation | None:
    """Một hội thoại, CHỈ khi nó thuộc về `patient_id`.

    Không có biến thể nào của hàm này bỏ qua `patient_id`. Cố ý.
    """

    return (
        db.execute(
            select(Conversation)
            .where(Conversation.id == conversation_id)
            .where(Conversation.patient_id == patient_id)
        )
        .scalars()
        .first()
    )


def list_conversations(
    db: Session, *, patient_id: int, limit: int = 50, offset: int = 0
) -> tuple[Sequence[Conversation], int]:
    """Hội thoại của bệnh nhân, mới cập nhật trước, kèm tổng số."""

    total = int(
        db.execute(
            select(func.count()).select_from(Conversation).where(Conversation.patient_id == patient_id)
        ).scalar_one()
    )
    rows = (
        db.execute(
            select(Conversation)
            .where(Conversation.patient_id == patient_id)
            .order_by(Conversation.updated_at.desc(), Conversation.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return rows, total


def get_or_create_latest(db: Session, *, patient_id: int) -> Conversation:
    """Hội thoại gần nhất, tạo mới nếu chưa có cái nào.

    Dùng cho client cũ chưa gửi `conversation_id`. Giữ tương thích ngược: bản
    frontend đã deploy vẫn gọi `/orchestrator/message` không kèm id, và nó phải
    tiếp tục chạy chứ không được 400.
    """

    rows, _ = list_conversations(db, patient_id=patient_id, limit=1)
    if rows:
        return rows[0]
    return create_conversation(db, patient_id=patient_id)


def list_messages(
    db: Session, *, conversation_id: int, patient_id: int
) -> Sequence[ConversationMessage] | None:
    """Transcript của một hội thoại. `None` nếu không phải của người này.

    Quyền sở hữu của tin nhắn SUY RA từ hội thoại: phải qua được
    `get_conversation` trước. `conversation_messages` không có cột `patient_id`
    để tránh hai nguồn sự thật có thể lệch nhau.
    """

    if get_conversation(db, conversation_id=conversation_id, patient_id=patient_id) is None:
        return None

    return (
        db.execute(
            select(ConversationMessage)
            .where(ConversationMessage.conversation_id == conversation_id)
            .order_by(ConversationMessage.id)
        )
        .scalars()
        .all()
    )


def append_message(
    db: Session,
    *,
    conversation: Conversation,
    role: str,
    content: str,
    intent: str | None = None,
    reason_code: str | None = None,
    data_type: str | None = None,
) -> ConversationMessage:
    """Ghi một lượt. Nhận đối tượng `Conversation` đã qua kiểm quyền, không nhận id.

    Ký hiệu này là cố ý: muốn ghi thì phải có trong tay một `Conversation` lấy
    từ `get_conversation`, tức là đã qua cửa `patient_id`. Nhận `conversation_id`
    thì hàm này lại thành một đường vòng bỏ qua kiểm quyền.
    """

    message = ConversationMessage(
        conversation_id=conversation.id,
        role=role,
        content=content,
        intent=intent,
        reason_code=reason_code,
        data_type=data_type,
    )
    db.add(message)

    # Câu hỏi đầu tiên đặt tên cho hội thoại, để danh sách không toàn "Hội thoại
    # mới". Chỉ lấy lượt của người dùng — câu mở đầu của trợ lý giống hệt nhau ở
    # mọi hội thoại nên vô dụng làm nhãn.
    if conversation.title is None and role == ROLE_USER:
        cleaned = " ".join(content.split())
        conversation.title = cleaned[:TITLE_MAX_CHARS] or None

    conversation.updated_at = _utcnow()
    try:
        db.commit()
    except Exception:
        # ROLLBACK, khong chi nem len. Mot flush that bai lam session vao trang
        # thai "pending rollback", va MOI truy van sau do — ke ca viec ghi tin
        # nhan cua tro ly — deu chet theo voi PendingRollbackError. Do la cach
        # mot loi nho bien thanh mat ca luot tra loi khoi transcript.
        db.rollback()
        raise
    db.refresh(message)
    return message


def save_context(db: Session, *, conversation: Conversation, context: object) -> None:
    """Lưu context của orchestrator lên chính hàng hội thoại.

    Đây là mắt xích khiến New Chat cô lập thật sự: context được ghi vào ĐÚNG
    hàng đang nói chuyện, nên hội thoại khác đọc hàng khác và không thấy gì.
    """

    conversation.onboarding_acknowledged = bool(getattr(context, "onboarding_acknowledged", False))
    conversation.current_report_ref = getattr(context, "current_report_ref", None)
    conversation.current_analyte = getattr(context, "current_analyte", None)

    last_intent = getattr(context, "last_intent", None)
    conversation.last_intent = getattr(last_intent, "value", None) if last_intent else None

    state = getattr(context, "conversation_state", None)
    conversation.pending_question = getattr(state, "pending_question", None) if state else None
    conversation.pending_question_at = getattr(state, "pending_question_timestamp", None) if state else None
    conversation.expected_entity = getattr(state, "expected_entity", None) if state else None

    conversation.updated_at = _utcnow()
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


__all__ = [
    "ROLE_ASSISTANT",
    "ROLE_USER",
    "append_message",
    "create_conversation",
    "get_conversation",
    "get_or_create_latest",
    "list_conversations",
    "list_messages",
    "save_context",
]
