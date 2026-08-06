import asyncio
import logging
import textwrap

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

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


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True
)
async def call_llm_with_retry(structured_llm, prompt: str) -> ExplanationOutput:
    """Gọi LLM kèm cơ chế thử lại (Exponential Backoff) nếu gặp lỗi 429 hoặc lỗi mạng."""
    return await structured_llm.ainvoke([HumanMessage(content=prompt)])


async def process_single_indicator(
    ind: dict,
    patient_age: str,
    gender_str: str,
    language: str,
    structured_llm,
    vector_store,
    semaphore: asyncio.Semaphore,
) -> tuple[dict, dict]:
    """Xử lý phân tích 1 chỉ số độc lập, bị kiểm soát bởi Semaphore."""
    async with semaphore:
        name = ind.get("name", "")
        val = ind.get("value")
        unit = ind.get("unit", "")
        status = ind.get("status", "unknown")

        # 1. Truy vấn RAG (Chạy trên thread riêng để không block Event Loop)
        context = ""
        extracted_sources = []
        if vector_store:
            try:
                rag_results = await asyncio.to_thread(
                    vector_store.search, query=name, k=1
                )
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
                                context += f"\nNguồn: {', '.join(sources_meta)}"
            except Exception as e:
                logger.error(f"Lỗi truy vấn ChromaDB cho {name}: {e}")
                context = "Không có thông tin tham khảo từ cơ sở dữ liệu."

        # 2. Xây dựng Prompt
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
                logger.info(f"Đang gọi LLM cho chỉ số: {name}")
                result = await call_llm_with_retry(structured_llm, prompt)
                explanation_text = result.explanation
                extracted_sources = result.sources
                logger.info(f"Gọi LLM thành công cho chỉ số: {name}")
            except Exception as e:
                logger.error(f"Lỗi khi gọi LLM cho {name} (đã thử lại hết mức): {e}")
                explanation_text = "Hệ thống đang bận, vui lòng thử lại."
        else:
            explanation_text = "Hệ thống đang bận, vui lòng thử lại."

        # 4. Trả về kết quả
        exp_obj: IndicatorExplanation = {
            "indicator_name": name,
            "status": status,
            "category": ind.get("category", "unknown"),
            "is_abnormal": ind.get("is_abnormal", False),
            "is_critical": ind.get("is_critical", False),
            "explanation": explanation_text,
            "sources": extracted_sources,
        }

        new_ind = dict(ind)
        new_ind["explanation"] = explanation_text
        new_ind["sources"] = extracted_sources
        
        return new_ind, exp_obj


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

    gender_str = (
        "Nam"
        if patient_gender == "male"
        else "Nữ" if patient_gender == "female" else "Khác"
    )

    # Giới hạn xử lý đồng thời (Concurrency Limiting) bằng Semaphore
    # Mức 3 có nghĩa là tối đa 3 request gọi LLM cùng một lúc, tránh quá tải API
    semaphore = asyncio.Semaphore(3)

    # Tạo danh sách các task chạy song song
    tasks = [
        process_single_indicator(
            ind,
            str(patient_age) if patient_age else "Không rõ",
            gender_str,
            language,
            structured_llm,
            vector_store,
            semaphore,
        )
        for ind in indicators
    ]

    # Chạy song song và đợi toàn bộ task hoàn tất
    results = await asyncio.gather(*tasks)

    # Gộp kết quả
    updated_indicators = []
    explanations = []
    
    for new_ind, exp_obj in results:
        updated_indicators.append(new_ind)
        explanations.append(exp_obj)

    return {"indicators": updated_indicators, "explanations": explanations}
