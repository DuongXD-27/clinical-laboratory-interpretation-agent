import re
from src.agents.state import AgentState

# Danh sách các từ khóa cấm liên quan đến chẩn đoán xác định và kê đơn điều trị
RESTRICTED_KEYWORDS = [
    r"chẩn đoán bạn bị",
    r"bạn mắc bệnh",
    r"chắc chắn bị",
    r"kê đơn",
    r"uống thuốc",
    r"dùng thuốc",
    r"phẫu thuật",
    r"liều lượng",
    r"điều trị bằng",
    r"bạn đang bị",
    r"chữa khỏi",
    r"có thể do",
    r"nguyên nhân do",
    r"thường liên quan đến",
    r"do ảnh hưởng của"
]

DEFAULT_DISCLAIMER = (
    "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa. "
    "Vui lòng trao đổi với bác sĩ để được diễn giải chính xác cho tình trạng của bạn."
)

SAFE_FALLBACK_TEXT = "Phát hiện nội dung có thể chứa yếu tố suy đoán nguyên nhân hoặc chẩn đoán. Để đảm bảo an toàn, vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác."

async def guardrail_node(state: AgentState) -> dict:
    """Kiểm tra nội dung sinh ra để chặn chẩn đoán y khoa và đảm bảo có disclaimer."""
    
    explanations = state.get("explanations", [])
    indicators = state.get("indicators", [])
    summary = state.get("summary", "")
    disclaimer = state.get("disclaimer", "")
    
    flags = []
    
    # Hàm kiểm tra vi phạm
    def check_violation(text: str) -> bool:
        if not text: return False
        text_lower = text.lower()
        for pattern in RESTRICTED_KEYWORDS:
            if re.search(pattern, text_lower):
                flags.append(f"Phát hiện cụm từ vi phạm: '{pattern}'")
                return True
        return False

    # 1. Quét nội dung summary
    if check_violation(summary):
        summary = SAFE_FALLBACK_TEXT
        
    # 2. Quét từng explanation và indicator
    for exp in explanations:
        if check_violation(exp.get("explanation", "")) or check_violation(exp.get("indicator_name", "")):
            # Fallback chỉ đè lên explanation
            exp["explanation"] = SAFE_FALLBACK_TEXT
            
    for ind in indicators:
        if check_violation(ind.get("explanation", "")):
            ind["explanation"] = SAFE_FALLBACK_TEXT
            
    # 3. Đánh giá guardrail_passed
    guardrail_passed = len(flags) == 0
    
    # 4. Đảm bảo có disclaimer chuẩn
    if not disclaimer or len(disclaimer.strip()) < 20:
        disclaimer = DEFAULT_DISCLAIMER
        
    return {
        "guardrail_passed": guardrail_passed,
        "guardrail_flags": list(set(flags)),
        "disclaimer": disclaimer,
        "summary": summary,
        "explanations": explanations,
        "indicators": indicators
    }
