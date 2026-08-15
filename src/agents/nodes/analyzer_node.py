"""Personalized explanation node with optional, independently-failing RAG."""

from __future__ import annotations

import asyncio
import logging
import textwrap
import time
import unicodedata
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agents.state import AgentState, IndicatorExplanation, RetrievedChunk
from src.config import get_settings
from src.services.llm import get_llm
from src.services.medical_knowledge_retriever import (
    MedicalKnowledgeRetriever,
    get_medical_knowledge_retriever,
)
from src.services.request_timing import add_timing_event
from src.services.template_loader import load_templates

logger = logging.getLogger(__name__)

GENERATION_SAFETY_CONTRACT = """\
Hợp đồng an toàn bắt buộc:
- NORMAL chỉ có nghĩa là giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng. Không được suy ra cơ thể/sức khỏe/chức năng cơ quan bình thường, miễn dịch ổn định, không có bệnh, viêm, nhiễm trùng hoặc vấn đề y khoa.
- Khi trạng thái là NORMAL: TUYỆT ĐỐI KHÔNG suy diễn rằng "bình thường thì không gây triệu chứng/không ảnh hưởng gì", và KHÔNG liệt kê rủi ro khi tăng/giảm nếu context không nói rõ về trạng thái bình thường. Nếu context chỉ mô tả khi tăng cao/giảm thấp mà không có nội dung trực tiếp về mức bình thường, lời giải thích CHỈ ĐƯỢC nêu giá trị, đơn vị và xác nhận giá trị nằm trong khoảng tham chiếu được hệ thống sử dụng; bỏ toàn bộ phần tăng/giảm.
- LOW/HIGH chỉ có nghĩa là giá trị thấp/cao so với khoảng tham chiếu được hệ thống sử dụng; đây không phải chẩn đoán.
- CRITICAL_LOW/CRITICAL_HIGH chỉ có nghĩa là giá trị vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình; cảnh báo xác định của hệ thống là có thẩm quyền và đây không phải chẩn đoán.
- Không gọi giá trị là "mức tối ưu" và không khẳng định tim, gan, thận, miễn dịch hay chức năng khác hoạt động bình thường từ một kết quả xét nghiệm đơn lẻ.
- Ngoài giá trị, đơn vị, trạng thái xác định, khoảng tham chiếu và cảnh báo xác định: mọi triệu chứng, ảnh hưởng, liên hệ hoặc nội dung y khoa phải được nêu trực tiếp trong context cho đúng trạng thái đó. Context không nêu thì phải bỏ, không dùng kiến thức sẵn có của mô hình để bổ sung hay suy diễn ngược từ trạng thái khác.
- Giữ nguyên ngôn ngữ điều kiện của context như "có thể" hoặc "có thể gặp"; không đổi thành khẳng định về bệnh nhân như "bệnh nhân đang", "điều này cho thấy" hoặc "điều này chứng minh".
- Khi context không đủ hoặc không trực tiếp hỗ trợ cho trạng thái hiện tại, ưu tiên lời giải thích tối giản (chỉ nêu giá trị, đơn vị và xác nhận giá trị nằm trong khoảng tham chiếu) thay vì suy diễn.
"""

_STATUS_QUALIFIERS = {
    "normal": "Giá trị này nằm trong khoảng tham chiếu được hệ thống sử dụng.",
    "low": "Giá trị này thấp so với khoảng tham chiếu được hệ thống sử dụng.",
    "high": "Giá trị này cao so với khoảng tham chiếu được hệ thống sử dụng.",
    "critical_low": "Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình.",
    "critical_high": "Giá trị này vượt ngưỡng cảnh báo nguy kịch được hệ thống cấu hình.",
}


def _normalized_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def ensure_reference_qualification(explanation: str, status: str) -> str:
    """Guarantee a generic status boundary without replacing generated content."""
    qualifier = _STATUS_QUALIFIERS.get(status)
    if not qualifier:
        return explanation

    normalized = _normalized_text(explanation)
    is_qualified = (
        "khoang tham chieu" in normalized
        if status in {"normal", "low", "high"}
        else "nguong canh bao nguy kich" in normalized
    )
    return explanation if is_qualified else f"{qualifier} {explanation}".strip()


class ExplanationOutput(BaseModel):
    explanation: str = Field(
        ...,
        description="Giải thích dễ hiểu, ngắn gọn về chỉ số bằng tiếng Việt.",
    )
    sources: list[str] = Field(
        default_factory=list,
        description="Nguồn được trích từ context; hệ thống vẫn kiểm tra lại trước khi trả ra.",
    )


@retry(
    wait=wait_exponential(multiplier=2, min=2, max=10),
    stop=stop_after_attempt(3),
    reraise=True,
)
async def call_llm_with_retry(structured_llm, prompt: str) -> ExplanationOutput:
    return await structured_llm.ainvoke([HumanMessage(content=prompt)])


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _known_sources(indicator: dict[str, Any], chunks: list[RetrievedChunk]) -> list[str]:
    sources = [str(source) for source in indicator.get("sources", []) if str(source)]
    for chunk in chunks:
        sources.extend(str(source) for source in chunk.get("sources", []) if str(source))
        if chunk.get("source"):
            sources.append(str(chunk["source"]))
    return _deduplicate(sources)


async def _retrieve_optional_context(
    *,
    retriever: MedicalKnowledgeRetriever | None,
    rag_semaphore: asyncio.Semaphore,
    analyte_id: str,
    name: str,
    status: str,
) -> list[RetrievedChunk]:
    if retriever is None or not analyte_id:
        return []
    query = f"Ý nghĩa xét nghiệm {name} khi kết quả ở mức {status}"
    try:
        queue_started_at = time.perf_counter()
        async with rag_semaphore:
            add_timing_event(
                "rag-semaphore-wait",
                (time.perf_counter() - queue_started_at) * 1000,
                analyte_id=analyte_id,
            )
            call_started_at = time.perf_counter()
            try:
                result = await asyncio.to_thread(
                    retriever.retrieve,
                    query=query,
                    analyte_id=analyte_id,
                    limit=3,
                )
            except Exception:
                add_timing_event(
                    "rag-call",
                    (time.perf_counter() - call_started_at) * 1000,
                    analyte_id=analyte_id,
                    outcome="error",
                )
                raise
            add_timing_event(
                "rag-call",
                (time.perf_counter() - call_started_at) * 1000,
                analyte_id=analyte_id,
                outcome="success",
            )
            return result
    except Exception as exc:
        # RAG is enrichment only. Structured classification and curated fallback
        # remain available even when the provider, network or vector index fails.
        logger.error("Optional RAG unavailable for %s: %s", name, exc)
        return []


async def process_single_indicator(
    indicator: dict[str, Any],
    patient_age: str,
    gender_str: str,
    language: str,
    structured_llm,
    retriever: MedicalKnowledgeRetriever | None,
    rag_semaphore: asyncio.Semaphore,
    llm_semaphore: asyncio.Semaphore,
    llm_timeout_seconds: float,
) -> tuple[dict[str, Any], IndicatorExplanation, list[RetrievedChunk]]:
    name = str(indicator.get("name", ""))
    analyte_id = str(indicator.get("analyte_id", ""))
    value = indicator.get("value")
    unit = str(indicator.get("unit", ""))
    status = str(indicator.get("status", "unknown"))
    curated_explanation = str(indicator.get("explanation", "")).strip()
    fallback_explanation = curated_explanation or load_templates().fallback_explanation

    chunks = await _retrieve_optional_context(
        retriever=retriever,
        rag_semaphore=rag_semaphore,
        analyte_id=analyte_id,
        name=name,
        status=status,
    )
    known_sources = _known_sources(indicator, chunks)
    rag_context = "\n\n".join(chunk.get("text", "") for chunk in chunks if chunk.get("text"))
    context = rag_context or curated_explanation

    prompt = textwrap.dedent(
        f"""\
        Bạn là trợ lý giải thích kết quả xét nghiệm cho mục đích giáo dục.
        Bệnh nhân: {patient_age} tuổi, giới tính {gender_str}.
        Ngôn ngữ hiển thị: {language}.

        Dữ liệu có cấu trúc đã được hệ thống xác định bằng lookup, KHÔNG được sửa:
        - Chỉ số: {name}
        - Giá trị: {value} {unit}
        - Trạng thái: {status}

        Ngữ cảnh giáo dục bổ sung (có thể là RAG hoặc curated fallback):
        <context>
        {context}
        </context>

        Nhiệm vụ:
        1. Nêu ngắn gọn giá trị và ý nghĩa của trạng thái theo hợp đồng an toàn bên dưới. Chỉ giải thích chỉ số LÀ GÌ khi định nghĩa đó xuất hiện rõ trong context; nếu context không định nghĩa thì bỏ phần này.
        2. Không thay đổi trạng thái, khoảng tham chiếu, đơn vị hoặc mức critical.
        3. KHÔNG chẩn đoán, suy đoán nguyên nhân, kê đơn hay đề nghị điều trị.
        4. Chỉ dùng thông tin có trong context. Nếu context không đủ, giữ lời giải thích tối thiểu.

        {GENERATION_SAFETY_CONTRACT}
        """
    )

    explanation_text = fallback_explanation
    if structured_llm is not None and context:
        try:
            queue_started_at = time.perf_counter()
            async with llm_semaphore:
                add_timing_event(
                    "llm-semaphore-wait",
                    (time.perf_counter() - queue_started_at) * 1000,
                    analyte_id=analyte_id or "unknown",
                )
                call_started_at = time.perf_counter()
                try:
                    result = await asyncio.wait_for(
                        call_llm_with_retry(structured_llm, prompt),
                        timeout=llm_timeout_seconds,
                    )
                except Exception:
                    add_timing_event(
                        "llm-explanation-call",
                        (time.perf_counter() - call_started_at) * 1000,
                        analyte_id=analyte_id or "unknown",
                        outcome="error",
                    )
                    raise
                add_timing_event(
                    "llm-explanation-call",
                    (time.perf_counter() - call_started_at) * 1000,
                    analyte_id=analyte_id or "unknown",
                    outcome="success",
                )
            if result.explanation.strip():
                explanation_text = result.explanation.strip()
        except Exception as exc:
            logger.error("LLM explanation failed for %s; using curated fallback: %s", name, exc)

    explanation_text = ensure_reference_qualification(explanation_text, status)

    explanation: IndicatorExplanation = {
        "indicator_name": name,
        "status": status,
        "category": indicator.get("category", "unknown"),
        "is_abnormal": indicator.get("is_abnormal", False),
        "is_critical": indicator.get("is_critical", False),
        "explanation": explanation_text,
        # Never trust model-generated URLs. Only return sources supplied by the
        # authoritative catalog or retrieved document metadata.
        "sources": known_sources,
    }
    updated_indicator = dict(indicator)
    updated_indicator["explanation"] = explanation_text
    updated_indicator["sources"] = known_sources
    return updated_indicator, explanation, chunks


async def analyzer_node(state: AgentState) -> dict:
    """Enrich deterministic assessments while keeping RAG optional."""

    indicators = state.get("indicators", [])
    if not indicators:
        return {"retrieved_contexts": []}

    try:
        structured_llm = get_llm().with_structured_output(ExplanationOutput)
    except Exception as exc:
        logger.error("LLM unavailable; using curated explanations: %s", exc)
        structured_llm = None

    try:
        retriever = get_medical_knowledge_retriever()
    except Exception as exc:
        logger.info("Optional RAG disabled or unavailable: %s", exc)
        retriever = None

    patient_age_value = state.get("patient_age")
    patient_age = "Không rõ" if patient_age_value is None else str(patient_age_value)
    patient_gender = state.get("patient_gender")
    gender_str = "Nam" if patient_gender == "male" else "Nữ" if patient_gender == "female" else "Khác"
    language = state.get("language", "vi")
    llm_timeout_seconds = get_settings().llm_timeout_seconds

    # Local/remote embeddings and LLM calls have different resource profiles.
    # Keep retrieval serialized; LLM generation may use bounded concurrency.
    rag_semaphore = asyncio.Semaphore(1)
    llm_semaphore = asyncio.Semaphore(3)
    results = await asyncio.gather(
        *[
            process_single_indicator(
                indicator,
                patient_age,
                gender_str,
                language,
                structured_llm,
                retriever,
                rag_semaphore,
                llm_semaphore,
                llm_timeout_seconds,
            )
            for indicator in indicators
        ]
    )

    updated_indicators: list[dict[str, Any]] = []
    explanations: list[IndicatorExplanation] = []
    retrieved_contexts: list[RetrievedChunk] = []
    for updated_indicator, explanation, chunks in results:
        updated_indicators.append(updated_indicator)
        explanations.append(explanation)
        retrieved_contexts.extend(chunks)

    return {
        "indicators": updated_indicators,
        "explanations": explanations,
        "retrieved_contexts": retrieved_contexts,
    }
