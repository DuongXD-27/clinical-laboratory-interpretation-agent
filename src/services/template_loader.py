import json
import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_FALLBACK_EXPLANATION = "Vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác."
DEFAULT_FALLBACK_SUMMARY = "Hệ thống phát hiện nội dung cần bác sĩ đánh giá. Vui lòng gặp bác sĩ để được tư vấn."
DEFAULT_DISCLAIMER = "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa."
DEFAULT_DOCTOR_QUESTIONS = ("Chỉ số này của tôi có ý nghĩa gì đối với sức khỏe tổng thể?",)


@dataclass(frozen=True)
class TemplateLibrary:
    fallback_explanation: str
    fallback_summary: str
    disclaimer: str
    doctor_questions_fallback: tuple[str, ...]


def _defaults() -> TemplateLibrary:
    return TemplateLibrary(
        fallback_explanation=DEFAULT_FALLBACK_EXPLANATION,
        fallback_summary=DEFAULT_FALLBACK_SUMMARY,
        disclaimer=DEFAULT_DISCLAIMER,
        doctor_questions_fallback=DEFAULT_DOCTOR_QUESTIONS,
    )


@lru_cache
def load_templates() -> TemplateLibrary:
    """
    Đọc thư viện mẫu (Template Library) từ file JSON tĩnh.

    Sử dụng `functools.lru_cache` để đảm bảo file cấu hình này chỉ được đọc
    từ đĩa cứng đúng 1 lần duy nhất lúc khởi động app (hoặc ở lần gọi đầu tiên).
    Điều này giúp tối ưu hóa hiệu năng, tránh I/O bottleneck khi có nhiều requests,
    đồng thời giữ cho code logic và dữ liệu text được tách biệt hoàn toàn.

    Returns a validated, immutable template library.
    """
    template_path = Path(__file__).resolve().parents[2] / "data" / "reference" / "templates.json"

    if not template_path.exists():
        logger.warning("Không tìm thấy %s. Trả về fallback templates mặc định.", template_path)
        return _defaults()

    try:
        with open(template_path, encoding="utf-8") as file:
            payload = json.load(file)
        questions = payload.get("doctor_questions_fallback")
        if (
            not isinstance(questions, list)
            or not questions
            or not all(isinstance(question, str) and question.strip() for question in questions)
        ):
            raise ValueError("doctor_questions_fallback phải là danh sách chuỗi không rỗng")
        return TemplateLibrary(
            fallback_explanation=str(payload["fallback_explanation"]).strip(),
            fallback_summary=str(payload["fallback_summary"]).strip(),
            disclaimer=str(payload["disclaimer"]).strip(),
            doctor_questions_fallback=tuple(question.strip() for question in questions),
        )
    except Exception as exc:
        logger.error("Lỗi khi đọc %s: %s. Trả về fallback templates mặc định.", template_path, exc)
        return _defaults()
