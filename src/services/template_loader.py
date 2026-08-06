import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)

@lru_cache
def load_templates() -> Dict[str, Any]:
    """
    Đọc thư viện mẫu (Template Library) từ file JSON tĩnh.
    
    Sử dụng `functools.lru_cache` để đảm bảo file cấu hình này chỉ được đọc 
    từ đĩa cứng đúng 1 lần duy nhất lúc khởi động app (hoặc ở lần gọi đầu tiên).
    Điều này giúp tối ưu hóa hiệu năng, tránh I/O bottleneck khi có nhiều requests,
    đồng thời giữ cho code logic và dữ liệu text được tách biệt hoàn toàn.
    
    Returns:
        Dict[str, Any]: Từ điển chứa các mẫu câu giải thích dự phòng (fallback),
                        câu hỏi kiểm duyệt và thông điệp an toàn (disclaimer).
    """
    template_path = Path("data/reference/templates.json")
    
    if not template_path.exists():
        logger.warning("Không tìm thấy %s. Trả về fallback templates mặc định.", template_path)
        return {
            "fallback_explanation": "Vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác.",
            "fallback_summary": "Hệ thống phát hiện nội dung cần bác sĩ đánh giá. Vui lòng gặp bác sĩ để được tư vấn.",
            "disclaimer": "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa.",
            "doctor_questions_fallback": [
                "Chỉ số này của tôi có ý nghĩa gì đối với sức khỏe tổng thể?"
            ]
        }
        
    try:
        with open(template_path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception as exc:
        logger.error("Lỗi khi đọc %s: %s. Trả về fallback templates mặc định.", template_path, exc)
        return {
            "fallback_explanation": "Vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác.",
            "fallback_summary": "Hệ thống phát hiện nội dung cần bác sĩ đánh giá. Vui lòng gặp bác sĩ để được tư vấn.",
            "disclaimer": "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa.",
            "doctor_questions_fallback": [
                "Chỉ số này của tôi có ý nghĩa gì đối với sức khỏe tổng thể?"
            ]
        }
