"""Node sinh câu hỏi gợi ý cho bác sĩ.

Đặt SAU analyzer và TRƯỚC guardrail: guardrail bắt buộc kiểm duyệt cả câu hỏi
trước khi nội dung ra ngoài (ADR-004 — guardrail luôn là lớp cuối cùng, không có
ngoại lệ cho bất kỳ nội dung nào hiển thị cho bệnh nhân).

Node này rule-based, không gọi LLM. Toàn bộ logic nằm ở
``src/services/question_templates.py`` để test được mà không cần dựng graph.
"""

from __future__ import annotations

import logging

from src.agents.state import AgentState
from src.services.question_templates import generate_questions

logger = logging.getLogger(__name__)


def question_generator_node(state: AgentState) -> dict:
    """Ghi ``questions_for_doctor`` (chuỗi, cho guardrail) + metadata song song.

    ``questions_for_doctor`` giữ đúng kiểu ``list[str]`` mà nhánh kiểm duyệt câu
    hỏi của guardrail đã chờ từ V2. ``doctor_question_meta`` là danh sách song
    song cùng thứ tự, mang analyte_id / tên chỉ số / mức ưu tiên để lưu vào phiếu
    sau khi guardrail chạy xong.

    Không bao giờ raise ra ngoài: câu hỏi gợi ý là phần bổ sung giá trị, không
    phải phần cốt lõi. Người bệnh không được nhìn thấy màn hình lỗi chỉ vì phần
    câu hỏi không hoạt động — họ vẫn phải nhận đủ chỉ số, trạng thái và giải
    thích như bình thường.
    """

    indicators = [
        indicator
        for indicator in (state.get("indicators") or [])
        if indicator.get("input_integrity_status") != "NEED_REVIEW"
    ]

    try:
        generated = generate_questions(indicators)
    except Exception:
        logger.exception("Sinh câu hỏi gợi ý thất bại; trả về danh sách rỗng")
        return {"questions_for_doctor": [], "doctor_question_meta": []}

    logger.info(
        "generated %d doctor questions from %d indicators",
        len(generated),
        len(indicators),
    )

    return {
        "questions_for_doctor": [question.text for question in generated],
        "doctor_question_meta": [
            {
                "priority": question.priority,
                "display_order": question.display_order,
                "analyte_id": question.analyte_id,
                "indicator_name": question.indicator_name,
            }
            for question in generated
        ],
    }
