import logging
import textwrap

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field

from src.agents.state import AgentState, IndicatorExplanation
from src.services.llm import get_llm
from src.services.vector_store import get_vector_store

logger = logging.getLogger(__name__)


class ExplanationOutput(BaseModel):
    explanation: str = Field(
        ...,
        description="Giải thích dễ hiểu, ngắn gọn về chỉ số (bằng tiếng Việt).",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Danh sách các nguồn tham khảo (URL) y khoa từ tài liệu.",
    )


async def analyzer_node(state: AgentState) -> dict:
    """Phân tích các chỉ số, truy vấn ChromaDB (RAG) và dùng LLM để tạo giải thích."""
    indicators = state.get("indicators", [])
    patient_age = state.get("patient_age")
    patient_gender = state.get("patient_gender")
    language = state.get("language", "vi")

    if not indicators:
        return {}

    try:
        llm = get_llm()
        structured_llm = llm.with_structured_output(ExplanationOutput)
    except Exception as e:
        logger.error(f"Failed to load LLM: {e}")
        structured_llm = None

    try:
        vector_store = get_vector_store()
    except Exception as e:
        logger.error(f"Failed to load VectorStore: {e}")
        vector_store = None

    explanations = []
    updated_indicators = []

    gender_str = (
        "Nam"
        if patient_gender == "male"
        else "Nữ" if patient_gender == "female" else "Khác"
    )

    for ind in indicators:
        name = ind.get("name", "")
        val = ind.get("value")
        unit = ind.get("unit", "")
        status = ind.get("status", "unknown")

        # 1. Truy vấn RAG
        context = ""
        extracted_sources = []
        if vector_store:
            try:
                rag_results = vector_store.search(query=name, k=1)
                if (
                    rag_results
                    and rag_results.get("documents")
                    and len(rag_results["documents"]) > 0
                    and len(rag_results["documents"][0]) > 0
                ):
                    docs = rag_results["documents"][0]
                    metas = (
                        rag_results["metadatas"][0]
                        if rag_results.get("metadatas")
                        else []
                    )

                    context = "\n".join(docs)
                    for meta in metas:
                        if meta and "sources" in meta:
                            sources_meta = meta["sources"]
                            if isinstance(sources_meta, str):
                                context += f"\nNguồn: {sources_meta}"
                            elif isinstance(sources_meta, list):
                                context += (
                                    f"\nNguồn: {', '.join(sources_meta)}"
                                )
            except Exception as e:
                logger.error(f"Lỗi truy vấn ChromaDB cho {name}: {e}")
                context = "Không có thông tin tham khảo từ cơ sở dữ liệu."

        # 2. Xây dựng Prompt (Dùng textwrap.dedent)
        prompt = textwrap.dedent(
            f"""\
            Bạn là một trợ lý y tế phân tích kết quả xét nghiệm.
            Bệnh nhân: {patient_age} tuổi, giới tính {gender_str}.
            Ngôn ngữ hiển thị: {language}.

            Chỉ số xét nghiệm: {name}
            Giá trị đo được: {val} {unit}
            Trạng thái: {status} (bình thường, thấp, cao, nguy kịch, ...)

            Dưới đây là thông tin y khoa trích xuất từ cơ sở dữ liệu (RAG):
            <context>
            {context}
            </context>

            Nhiệm vụ:
            1. Viết một đoạn giải thích ngắn gọn, thân thiện, dễ hiểu cho bệnh nhân về ý nghĩa của kết quả chỉ số này dựa trên ngữ cảnh trên. Dùng ngôn ngữ: {language}.
            2. KHÔNG đưa ra lời khuyên y tế, KHÔNG kê đơn thuốc, KHÔNG chẩn đoán bệnh.
            3. TUYỆT ĐỐI KHÔNG suy đoán nguyên nhân gây ra kết quả bất thường (ví dụ: không dùng "có thể do", "nguyên nhân do", "thường liên quan đến"). Chỉ giải thích chỉ số đó LÀ GÌ và Ý NGHĨA CHUNG.
            4. Trích xuất danh sách các nguồn từ ngữ cảnh (nếu có URL nguồn). Nếu không có, để mảng rỗng.
            """
        )

        # 3. Gọi LLM
        explanation_text = ""
        if structured_llm:
            try:
                result: ExplanationOutput = await structured_llm.ainvoke(
                    [HumanMessage(content=prompt)]
                )
                explanation_text = result.explanation
                extracted_sources = result.sources
            except Exception as e:
                logger.error(f"Lỗi khi gọi LLM cho {name}: {e}")
                explanation_text = "Hệ thống đang bận, vui lòng thử lại."
        else:
            explanation_text = "Hệ thống đang bận, vui lòng thử lại."

        # 4. Lưu kết quả
        exp_obj: IndicatorExplanation = {
            "indicator_name": name,
            "status": status,
            "is_abnormal": ind.get("is_abnormal", False),
            "is_critical": ind.get("is_critical", False),
            "explanation": explanation_text,
            "sources": extracted_sources,
        }
        explanations.append(exp_obj)

        new_ind = dict(ind)
        new_ind["explanation"] = explanation_text
        new_ind["sources"] = extracted_sources
        updated_indicators.append(new_ind)

    return {"indicators": updated_indicators, "explanations": explanations}
