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
    r"chữa khỏi"
]

DEFAULT_DISCLAIMER = (
    "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa. "
    "Vui lòng trao đổi với bác sĩ để được diễn giải chính xác cho tình trạng của bạn."
)

async def guardrail_node(state: AgentState) -> dict:
    """Kiểm tra nội dung sinh ra để chặn chẩn đoán y khoa và đảm bảo có disclaimer."""
    
    explanations = state.get("explanations", [])
    summary = state.get("summary", "")
    disclaimer = state.get("disclaimer", "")
    
    flags = []
    
    # 1. Quét nội dung summary và explanations
    text_to_scan = [summary]
    for exp in explanations:
        text_to_scan.append(exp.get("explanation", ""))
        
    full_text = " ".join(text_to_scan).lower()
    
    for pattern in RESTRICTED_KEYWORDS:
        if re.search(pattern, full_text):
            flags.append(f"Phát hiện cụm từ vi phạm: '{pattern}'")
            
    # 2. Đánh giá guardrail_passed
    guardrail_passed = len(flags) == 0
    
    # 3. Đảm bảo có disclaimer chuẩn
    if not disclaimer or len(disclaimer.strip()) < 20:
        disclaimer = DEFAULT_DISCLAIMER
        
    return {
        "guardrail_passed": guardrail_passed,
        "guardrail_flags": flags,
        "disclaimer": disclaimer
    }
