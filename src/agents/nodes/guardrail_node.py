import logging
import re
from functools import lru_cache
from typing import List

from langchain_core.messages import HumanMessage

from src.agents.state import AgentState
from src.services.llm import get_llm
from src.services.template_loader import load_templates
from src.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)

# Danh sách các từ khóa cấm liên quan đến chẩn đoán xác định và kê đơn điều trị (Quét Regex)
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

# Danh sách các câu mẫu vi phạm (Quét Semantic Similarity)
FORBIDDEN_SAMPLE_SENTENCES = [
    "Tôi chẩn đoán bạn mắc bệnh này.",
    "Bạn cần mua đơn thuốc sau.",
    "Bạn chắc chắn bị ung thư hoặc bệnh lý nghiêm trọng.",
    "Hãy uống thuốc này theo liều lượng cụ thể.",
    "Nguyên nhân gây ra kết quả này là do bạn bị bệnh.",
    "Điều trị bằng phương pháp này sẽ giúp bạn khỏi bệnh."
]

@lru_cache
def get_forbidden_embeddings() -> list[list[float]]:
    """Tải và mã hóa các câu cấm mẫu một lần duy nhất vào bộ nhớ."""
    try:
        vs = get_vector_store()
        # BGE-M3 có set normalize_embeddings=True, nên vector trả về đã chuẩn hóa (unit vector)
        return vs._embeddings.embed_documents(FORBIDDEN_SAMPLE_SENTENCES)
    except Exception as e:
        logger.error(f"Lỗi khi mã hóa các câu cấm mẫu: {e}")
        return []

async def rewrite_with_llm(llm, original_text: str) -> str:
    """Yêu cầu LLM viết lại nội dung để loại bỏ các vi phạm an toàn y tế."""
    if not llm or not original_text.strip():
        return original_text
        
    prompt = f"""\
    Nhiệm vụ của bạn là biên tập lại đoạn văn bản sau sao cho an toàn về mặt y tế.
    
    Văn bản gốc:
    "{original_text}"
    
    Yêu cầu:
    1. Giữ lại các thông tin giải thích hữu ích (nếu có).
    2. LOẠI BỎ HOÀN TOÀN các từ ngữ mang tính chất chẩn đoán bệnh, khẳng định bệnh lý, hoặc kê đơn/khuyên dùng thuốc.
    3. KHÔNG đưa ra suy đoán nguyên nhân (ví dụ: không dùng "có thể do", "thường liên quan đến").
    4. Trả về DUY NHẤT đoạn văn bản đã được sửa, không giải thích gì thêm.
    """
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content.strip()
    except Exception as e:
        logger.error(f"Lỗi khi gọi LLM để rewrite: {e}")
        return original_text

async def rewrite_questions_with_llm(llm, questions: list[str]) -> list[str]:
    """Yêu cầu LLM viết lại danh sách câu hỏi."""
    if not llm or not questions:
        return questions
        
    questions_str = "\n".join(f"- {q}" for q in questions)
    prompt = f"""\
    Nhiệm vụ của bạn là biên tập lại danh sách câu hỏi sau sao cho an toàn về mặt y tế.
    
    Danh sách gốc:
    {questions_str}
    
    Yêu cầu:
    1. Câu hỏi phải hướng tới việc xin ý kiến bác sĩ để được giải thích thêm.
    2. LOẠI BỎ HOÀN TOÀN các câu hỏi mang tính chất tự chẩn đoán bệnh, tự đề xuất loại thuốc cụ thể.
    3. Trả về danh sách câu hỏi, mỗi câu trên 1 dòng, bắt đầu bằng dấu "- ". Không giải thích gì thêm.
    """
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        lines = response.content.strip().split("\n")
        new_questions = [line.strip().lstrip("-").strip() for line in lines if line.strip()]
        return new_questions if new_questions else questions
    except Exception as e:
        logger.error(f"Lỗi khi gọi LLM để rewrite questions: {e}")
        return questions

async def guardrail_node(state: AgentState) -> dict:
    """Kiểm tra nội dung sinh ra để chặn chẩn đoán y khoa.
    
    Tích hợp kiểm duyệt qua 2 bước: Regex Keywords và Vector Semantic Similarity.
    Hỗ trợ cơ chế Self-Correction bằng LLM nếu phát hiện vi phạm.
    """
    # Nạp thư viện mẫu
    templates = load_templates()
    fallback_explanation = templates.get(
        "fallback_explanation", 
        "Vui lòng tham vấn trực tiếp với bác sĩ chuyên môn để được giải thích chính xác."
    )
    fallback_summary = templates.get(
        "fallback_summary", 
        "Hệ thống phát hiện nội dung cần bác sĩ đánh giá. Vui lòng gặp bác sĩ để được tư vấn."
    )
    default_disclaimer = templates.get(
        "disclaimer", 
        "Thông tin này chỉ mang tính giáo dục chung, KHÔNG phải chẩn đoán y khoa."
    )
    fallback_questions = templates.get(
        "doctor_questions_fallback",
        ["Chỉ số này của tôi có ý nghĩa gì đối với sức khỏe tổng thể?"]
    )

    explanations = state.get("explanations", [])
    indicators = state.get("indicators", [])
    summary = state.get("summary", "")
    disclaimer = state.get("disclaimer", "")
    questions_for_doctor = state.get("questions_for_doctor", [])

    flags = []

    # Khởi tạo embedding cache nếu chưa có
    forbidden_vecs = get_forbidden_embeddings()

    # Hàm kiểm tra vi phạm kết hợp Regex và Vector Similarity
    def check_violation(text: str) -> bool:
        if not text:
            return False
            
        # 1. Quét Regex
        text_lower = text.lower()
        for pattern in RESTRICTED_KEYWORDS:
            if re.search(pattern, text_lower):
                flags.append(f"Phát hiện cụm từ cấm (Regex): '{pattern}'")
                return True
                
        # 2. Quét Vector Semantic Similarity
        if forbidden_vecs:
            try:
                vs = get_vector_store()
                text_vec = vs._embeddings.embed_query(text)
                
                # Tính Cosine Similarity (Dot Product)
                for i, f_vec in enumerate(forbidden_vecs):
                    # Vì normalize_embeddings=True nên độ dài vector là 1 -> Cosine = Dot Product
                    similarity = sum(a * b for a, b in zip(text_vec, f_vec))
                    if similarity > 0.85:
                        matched_sentence = FORBIDDEN_SAMPLE_SENTENCES[i]
                        flags.append(f"Vi phạm ngữ nghĩa (sim={similarity:.2f}): Tương đồng '{matched_sentence}'")
                        return True
            except Exception as e:
                logger.error(f"Lỗi khi chạy Vector Similarity check: {e}")
                
        return False

    # Tải LLM để phục vụ Retry
    try:
        llm = get_llm()
    except Exception as e:
        logger.error(f"Failed to load LLM for guardrail retry: {e}")
        llm = None

    # 1. Quét nội dung summary
    if check_violation(summary):
        if llm:
            logger.info("Rewrite attempted for summary...")
            rewritten_summary = await rewrite_with_llm(llm, summary)
            if check_violation(rewritten_summary):
                summary = fallback_summary
            else:
                summary = rewritten_summary
        else:
            summary = fallback_summary

    # 2. Quét từng explanation và indicator
    for exp in explanations:
        text_to_check = exp.get("explanation", "")
        if check_violation(text_to_check) or check_violation(exp.get("indicator_name", "")):
            if llm:
                logger.info(f"Rewrite attempted for explanation of {exp.get('indicator_name')}...")
                rewritten_exp = await rewrite_with_llm(llm, text_to_check)
                if check_violation(rewritten_exp):
                    exp["explanation"] = fallback_explanation
                else:
                    exp["explanation"] = rewritten_exp
            else:
                exp["explanation"] = fallback_explanation

    for ind in indicators:
        text_to_check = ind.get("explanation", "")
        if check_violation(text_to_check):
            if llm:
                logger.info(f"Rewrite attempted for indicator {ind.get('name')}...")
                rewritten_ind = await rewrite_with_llm(llm, text_to_check)
                if check_violation(rewritten_ind):
                    ind["explanation"] = fallback_explanation
                else:
                    ind["explanation"] = rewritten_ind
            else:
                ind["explanation"] = fallback_explanation

    # 3. Quét danh sách câu hỏi gợi ý cho bác sĩ
    questions_violated = False
    for q in questions_for_doctor:
        if check_violation(q):
            questions_violated = True
            break
            
    if questions_violated:
        if llm:
            logger.info("Rewrite attempted for questions_for_doctor...")
            rewritten_questions = await rewrite_questions_with_llm(llm, questions_for_doctor)
            # Quét lại danh sách mới
            still_violated = any(check_violation(q) for q in rewritten_questions)
            if still_violated:
                questions_for_doctor = fallback_questions
            else:
                questions_for_doctor = rewritten_questions
        else:
            questions_for_doctor = fallback_questions

    # 4. Đánh giá guardrail_passed
    guardrail_passed = len(flags) == 0

    # 5. Đảm bảo có disclaimer chuẩn
    if not disclaimer or len(disclaimer.strip()) < 20:
        disclaimer = default_disclaimer

    return {
        "guardrail_passed": guardrail_passed,
        "guardrail_flags": list(set(flags)),
        "disclaimer": disclaimer,
        "summary": summary,
        "explanations": explanations,
        "indicators": indicators,
        "questions_for_doctor": questions_for_doctor
    }
