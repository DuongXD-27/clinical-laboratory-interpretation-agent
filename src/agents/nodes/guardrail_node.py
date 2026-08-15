import logging
import time
from copy import deepcopy

from langchain_core.messages import HumanMessage

from src.agents.state import AgentState
from src.services.llm import get_llm
from src.services.medical_safety_validator import MedicalSafetyValidator
from src.services.request_timing import add_timing_event
from src.services.template_loader import load_templates

logger = logging.getLogger(__name__)
DEFAULT_DISCLAIMER = load_templates().disclaimer


def _visible_text_content(content: object) -> str:
    """Return user-visible text without exposing provider metadata/reasoning."""
    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for block in content:
        if not isinstance(block, dict) or block.get("type") != "text":
            continue
        text = block.get("text")
        if isinstance(text, str) and text.strip():
            text_parts.append(text.strip())

    return "\n".join(text_parts).strip()


async def rewrite_with_llm(llm, original_text: str, grounding_context: str = "") -> str:
    """One bounded self-correction attempt before deterministic fallback."""
    if not llm or not original_text.strip():
        return original_text

    prompt = f"""\
Nhiệm vụ của bạn là biên tập lại đoạn văn bản sau sao cho an toàn về mặt y tế.

Văn bản gốc:
"{original_text}"

Ngữ cảnh y khoa duy nhất được phép dùng:
<context>
{grounding_context}
</context>

Yêu cầu:
1. Giữ lại thông tin giải thích giáo dục hữu ích chỉ khi thông tin đó xuất hiện trong context. Nếu context trống hoặc không hỗ trợ một thông tin y khoa thì xóa thông tin đó.
2. Loại bỏ chẩn đoán, khẳng định bệnh lý, kê đơn hoặc khuyên dùng thuốc.
3. Không suy đoán nguyên nhân.
4. Nếu văn bản nói NORMAL/LOW/HIGH, chỉ mô tả kết quả tương đối với khoảng tham chiếu được hệ thống sử dụng. Nếu nói CRITICAL_LOW/CRITICAL_HIGH, chỉ mô tả việc vượt ngưỡng cảnh báo nguy kịch được cấu hình; không chuyển thành chẩn đoán.
5. Loại bỏ mọi kết luận từ một kết quả xét nghiệm rằng bệnh nhân không có bệnh/viêm/nhiễm trùng/vấn đề y khoa, không gây triệu chứng/ảnh hưởng, miễn dịch ổn định, chức năng cơ quan bình thường hoặc đang ở mức tối ưu. Nếu trạng thái là NORMAL mà context không trực tiếp hỗ trợ nội dung giải thích cho mức bình thường, chỉ giữ lại câu xác nhận giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng.
6. Không thêm định nghĩa chỉ số, triệu chứng, nguyên nhân, hậu quả, điều trị hoặc kiến thức y khoa mới. Nếu bỏ phần vi phạm làm nội dung ngắn hơn thì giữ nội dung ngắn hơn.
7. Chỉ trả về đoạn văn đã sửa, không giải thích thêm.
"""
    started_at = time.perf_counter()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
    except Exception as exc:
        add_timing_event(
            "guardrail-rewrite-call",
            (time.perf_counter() - started_at) * 1000,
            outcome="error",
            target="text",
        )
        logger.error("Guardrail rewrite thất bại: %s", exc)
        return original_text
    add_timing_event(
        "guardrail-rewrite-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target="text",
    )
    return _visible_text_content(response.content)


async def rewrite_questions_with_llm(llm, questions: list[str]) -> list[str]:
    """One bounded rewrite for the doctor-question branch."""
    if not llm or not questions:
        return questions

    questions_text = "\n".join(f"- {question}" for question in questions)
    prompt = f"""\
Biên tập danh sách câu hỏi sau để người dùng xin bác sĩ giải thích thêm.
Loại bỏ tự chẩn đoán, suy đoán nguyên nhân và đề xuất thuốc/điều trị cụ thể.
Chỉ trả về mỗi câu hỏi trên một dòng bắt đầu bằng "- ".

{questions_text}
"""
    started_at = time.perf_counter()
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        visible_content = _visible_text_content(response.content)
        rewritten = [
            line.strip().removeprefix("-").strip()
            for line in visible_content.splitlines()
            if line.strip()
        ]
    except Exception as exc:
        add_timing_event(
            "guardrail-rewrite-call",
            (time.perf_counter() - started_at) * 1000,
            outcome="error",
            target="questions",
        )
        logger.error("Guardrail question rewrite thất bại: %s", exc)
        return questions
    add_timing_event(
        "guardrail-rewrite-call",
        (time.perf_counter() - started_at) * 1000,
        outcome="success",
        target="questions",
    )
    return rewritten or questions


async def guardrail_node(state: AgentState) -> dict:
    """Validate all user-visible text, retry once, then use shared templates.

    Detection is deterministic and local (regex + accent-insensitive intent
    rules). The LLM is used only to rewrite content already found unsafe; its
    output must pass the same local validator before it can leave this node.
    """
    templates = load_templates()
    validator = MedicalSafetyValidator()

    explanations = deepcopy(state.get("explanations", []))
    indicators = deepcopy(state.get("indicators", []))
    summary = state.get("summary", "")
    disclaimer = state.get("disclaimer", "")
    questions_for_doctor = list(state.get("questions_for_doctor", []))
    retrieved_contexts = list(state.get("retrieved_contexts", []))

    flags: list[str] = []
    violation_detected = False

    def violations_for(text: str, context: str) -> bool:
        nonlocal violation_detected
        violations = validator.validate(text)
        if not violations:
            return False
        violation_detected = True
        flags.extend(f"{context} — {violation.describe()}" for violation in violations)
        return True

    def rewrite_requires_fallback(text: str, context: str) -> bool:
        """Treat an empty rewrite as a failed retry, not as safe content."""
        if not text.strip():
            flags.append(f"{context} — LLM trả về nội dung rỗng")
            return True
        return violations_for(text, context)

    def grounding_context_for(indicator_name: str) -> str:
        normalized_name = indicator_name.strip().casefold()
        return "\n\n".join(
            str(chunk.get("text", "")).strip()
            for chunk in retrieved_contexts
            if str(chunk.get("indicator_name", "")).strip().casefold() == normalized_name
            and str(chunk.get("text", "")).strip()
        )

    llm = None
    llm_loaded = False

    def retry_llm():
        nonlocal llm, llm_loaded
        if llm_loaded:
            return llm
        llm_loaded = True
        try:
            llm = get_llm()
        except Exception as exc:
            logger.error("Không tải được LLM cho guardrail retry: %s", exc)
            llm = None
        return llm

    if violations_for(summary, "summary"):
        active_llm = retry_llm()
        summary_context = "\n\n".join(
            str(chunk.get("text", "")).strip()
            for chunk in retrieved_contexts
            if str(chunk.get("text", "")).strip()
        )
        rewritten = (
            await rewrite_with_llm(active_llm, summary, summary_context)
            if active_llm
            else summary
        )
        summary = (
            templates.fallback_summary
            if rewrite_requires_fallback(rewritten, "summary sau retry")
            else rewritten
        )

    for explanation in explanations:
        indicator_name = str(explanation.get("indicator_name", ""))
        text = str(explanation.get("explanation", ""))
        if violations_for(indicator_name, "tên chỉ số trong explanation"):
            explanation["indicator_name"] = "Chỉ số cần bác sĩ kiểm tra"
        if violations_for(text, f"explanation {indicator_name}"):
            active_llm = retry_llm()
            rewritten = (
                await rewrite_with_llm(
                    active_llm,
                    text,
                    grounding_context_for(indicator_name),
                )
                if active_llm
                else text
            )
            explanation["explanation"] = (
                templates.fallback_explanation
                if rewrite_requires_fallback(
                    rewritten, f"explanation {indicator_name} sau retry"
                )
                else rewritten
            )

    for indicator in indicators:
        indicator_name = str(indicator.get("name", ""))
        text = str(indicator.get("explanation", ""))
        if violations_for(indicator_name, "tên chỉ số"):
            indicator["name"] = "Chỉ số cần bác sĩ kiểm tra"
        if violations_for(text, f"indicator {indicator_name}"):
            active_llm = retry_llm()
            rewritten = (
                await rewrite_with_llm(
                    active_llm,
                    text,
                    grounding_context_for(indicator_name),
                )
                if active_llm
                else text
            )
            indicator["explanation"] = (
                templates.fallback_explanation
                if rewrite_requires_fallback(
                    rewritten, f"indicator {indicator_name} sau retry"
                )
                else rewritten
            )

    if any(violations_for(question, "câu hỏi cho bác sĩ") for question in questions_for_doctor):
        active_llm = retry_llm()
        rewritten_questions = (
            await rewrite_questions_with_llm(active_llm, questions_for_doctor)
            if active_llm
            else questions_for_doctor
        )
        questions_for_doctor = (
            list(templates.doctor_questions_fallback)
            if any(
                violations_for(question, "câu hỏi sau retry")
                for question in rewritten_questions
            )
            else rewritten_questions
        )

    if not disclaimer or len(disclaimer.strip()) < 20:
        disclaimer = templates.disclaimer
    elif violations_for(disclaimer, "disclaimer"):
        active_llm = retry_llm()
        rewritten = (
            await rewrite_with_llm(active_llm, disclaimer)
            if active_llm
            else disclaimer
        )
        disclaimer = (
            templates.disclaimer
            if rewrite_requires_fallback(rewritten, "disclaimer sau retry")
            else rewritten
        )

    return {
        # False records that unsafe content was generated, even when the final
        # response has been made safe by rewrite/fallback.
        "guardrail_passed": not violation_detected,
        "guardrail_flags": list(dict.fromkeys(flags)),
        "disclaimer": disclaimer,
        "summary": summary,
        "explanations": explanations,
        "indicators": indicators,
        "questions_for_doctor": questions_for_doctor,
    }
