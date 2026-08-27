"""Ghim kiểu cột của bảng hội thoại — hồi quy cho một lỗi thật trên production.

## Vì sao phải ghim KIỂU, không phải ghi thử rồi đọc lại

`pending_question` từng được khai `String(64)` vì tôi tưởng nó giữ một mã ngắn.
Thực tế nó giữ **nguyên văn câu hỏi lại** của trợ lý, dài khoảng 150 ký tự:

    "Bạn muốn xem chỉ số nào?\n\nBạn có thể chọn một chỉ số trong phiếu xét
     nghiệm hoặc nhập tên chỉ số, ví dụ:\n- WBC\n- Glucose\n- HbA1c..."

Bộ test 1473 case vẫn xanh, vì **SQLite không cưỡng chế độ dài VARCHAR** — nó
ghi thẳng giá trị dài vào cột `varchar(64)` không kêu gì. Postgres thì cưỡng
chế, nên production ném `StringDataRightTruncation`, session vào trạng thái
pending-rollback, và lượt trả lời của trợ lý biến mất khỏi transcript.

Nên một test kiểu "ghi 200 ký tự rồi đọc lại" là **vô dụng**: nó xanh trên
SQLite cả trước và sau khi sửa. Thứ duy nhất kiểm được trên SQLite là chính
kiểu cột đã khai trong model. Đó là điều file này làm.
"""

from __future__ import annotations

import pytest
from sqlalchemy import String, Text

from src.models.db import Conversation, ConversationMessage

# Những cột giữ văn bản do người hoặc LLM sinh ra. Không cột nào trong đây được
# phép có giới hạn độ dài: không ai dự đoán được câu trả lời dài bao nhiêu.
FREE_TEXT_COLUMNS = [
    (Conversation, "pending_question"),
    (ConversationMessage, "content"),
]

# Những cột giữ mã hoặc định danh. Giới hạn độ dài ở đây là đúng, nhưng phải đủ
# rộng cho tên chỉ số mà bệnh nhân tự gõ, không chỉ cho id canonical.
BOUNDED_COLUMNS = [
    (Conversation, "current_analyte", 255),
    (Conversation, "expected_entity", 255),
    (Conversation, "current_report_ref", 64),
    (Conversation, "last_intent", 64),
    (ConversationMessage, "role", 16),
    (ConversationMessage, "intent", 64),
    (ConversationMessage, "reason_code", 64),
    (ConversationMessage, "data_type", 32),
]


@pytest.mark.parametrize(("model", "column"), FREE_TEXT_COLUMNS)
def test_free_text_columns_are_unbounded_text(model, column):
    """Văn bản tự do phải là `Text`, không phải `String(n)`."""

    col = model.__table__.columns[column]
    assert isinstance(col.type, Text), (
        f"{model.__tablename__}.{column} phải là Text — nó giữ văn bản tự do, "
        f"đang là {col.type!r}. Giới hạn độ dài ở đây không nổ trên SQLite "
        f"nhưng nổ trên Postgres production."
    )
    assert getattr(col.type, "length", None) is None


@pytest.mark.parametrize(("model", "column", "minimum"), BOUNDED_COLUMNS)
def test_bounded_columns_are_wide_enough(model, column, minimum):
    col = model.__table__.columns[column]
    assert isinstance(col.type, String)
    assert col.type.length is not None
    assert col.type.length >= minimum, (
        f"{model.__tablename__}.{column} chỉ có {col.type.length} ký tự, "
        f"cần tối thiểu {minimum}."
    )


def test_no_context_column_silently_truncates_a_real_clarification_prompt():
    """Câu hỏi lại thật của trợ lý phải vừa cột đang giữ nó.

    Đây là nguyên văn giá trị đã làm vỡ production, giữ lại làm mốc thay vì một
    chuỗi 'x' * 200 vô nghĩa — nếu ai đó thu hẹp cột lại, thông báo lỗi chỉ
    thẳng vào nội dung thật đã gây ra sự cố.
    """

    real_prompt = (
        "Bạn muốn xem chỉ số nào?\n\n"
        "Bạn có thể chọn một chỉ số trong phiếu xét nghiệm hoặc nhập tên chỉ số, ví dụ:\n"
        "- WBC\n- Glucose\n- HbA1c\n- Cholesterol"
    )
    assert len(real_prompt) > 64, "giá trị mốc phải dài hơn giới hạn cũ mới có ý nghĩa"

    col = Conversation.__table__.columns["pending_question"]
    limit = getattr(col.type, "length", None)
    assert limit is None or limit >= len(real_prompt)
