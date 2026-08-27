"""Personalized explanation node with optional, independently-failing RAG."""

from __future__ import annotations

import asyncio
import logging
import textwrap
import time
from typing import Any

from langchain_core.messages import HumanMessage
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from src.agents.nodes.reference_range_checker_node import get_reference_repository
from src.agents.state import AgentState, IndicatorExplanation, RetrievedChunk
from src.config import get_settings
from src.services.analyte_catalog import get_analyte_catalog
from src.services.context_budget import build_bounded_context
from src.services.llm import get_llm
from src.services.medical_citations import get_medical_citation_repository
from src.services.medical_knowledge_retriever import (
    MedicalKnowledgeRetriever,
    get_medical_knowledge_retriever,
)
from src.services.medical_safety_assets import (
    GENERATION_SAFETY_CONTRACT,
    ensure_reference_qualification,
)
from src.services.patient_explanation import (
    build_patient_explanation,
    filter_patient_education_text,
    plain_definition,
)
from src.services.request_timing import add_timing_event
from src.services.safe_grounding import (
    build_safe_grounding_view,
)
from src.services.template_loader import load_templates

logger = logging.getLogger(__name__)


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


def _known_citations(
    *,
    analyte: str,
    sources: list[str],
    chunks: list[RetrievedChunk],
) -> list[dict[str, Any]]:
    """Resolve structured metadata only from corpus-owned records."""
    repository = get_medical_citation_repository()
    citations = repository.resolve_many(
        analyte=analyte,
        sources=sources,
    )
    for chunk in chunks:
        citation = repository.resolve(
            analyte=analyte,
            source_id=str(chunk.get("source_id") or ""),
            url=str(chunk.get("source_url") or chunk.get("source") or ""),
            note_type=str(chunk.get("note_type") or "") or None,
        )
        if citation is not None:
            citations.append(citation)
    unique: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for citation in citations:
        key = (citation.source_id, citation.note_type)
        if key in seen:
            continue
        seen.add(key)
        unique.append(citation.as_dict())
    return unique


def _resolve_band_fallback(
    indicator: dict[str, Any],
    *,
    unit: str,
    patient_gender: str | None,
    patient_age: int | float | None,
) -> str | None:
    """Deterministic band id when the checker's matched rule carried none.

    GRQ-004 Fix 1: banded/CDL analytes store their approved educational
    knowledge as band_notes, which the retriever can only admit when a band id
    is provided. Resolution reuses the SAME authoritative rule bounds loaded by
    the reference checker (ReferenceRepository.resolve_band) plus the frozen
    band vocabulary — no new classification engine, no threshold changes.

    Retrieval-context only: the resolved band never mutates indicator status,
    critical facts, or persisted data. Fail-closed to None.
    """
    status = str(indicator.get("status", "")).strip().lower()
    if not status or status == "unknown":
        return None
    existing_band = str(indicator.get("band_id") or "").strip()
    if existing_band:
        return existing_band
    try:
        numeric_value = float(indicator.get("value"))
    except (TypeError, ValueError):
        return None
    analyte_hint = str(indicator.get("analyte_canonical") or indicator.get("analyte_id") or indicator.get("name") or "")
    if not analyte_hint:
        return None
    try:
        return get_reference_repository().resolve_band(
            analyte=analyte_hint,
            value=numeric_value,
            unit=unit,
            patient_gender=patient_gender,
            patient_age=patient_age,
        )
    except Exception as exc:
        logger.info("Band resolution unavailable for %s: %s", analyte_hint, exc)
        return None


async def _retrieve_optional_context(
    *,
    retriever: MedicalKnowledgeRetriever | None,
    rag_semaphore: asyncio.Semaphore,
    analyte_id: str,
    name: str,
    status: str,
    band_id: str | None,
    critical_status: str | None,
) -> list[RetrievedChunk]:
    if retriever is None or not analyte_id or status.strip().lower() == "unknown":
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
                    status=status,
                    band_id=band_id,
                    critical_status=critical_status,
                    limit=get_settings().retrieval_top_k,
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
    patient_gender_raw: str | None = None,
    patient_age_raw: int | float | None = None,
) -> tuple[dict[str, Any], IndicatorExplanation, list[RetrievedChunk]]:
    name = str(indicator.get("name", ""))
    analyte_id = str(indicator.get("analyte_id", ""))
    value = indicator.get("value")
    unit = str(indicator.get("unit", ""))
    status = str(indicator.get("status", "unknown"))

    catalog = None
    try:
        catalog = get_analyte_catalog()
    except Exception:
        pass
    definition = catalog.resolve(name) if catalog else None
    if definition is None and catalog and analyte_id:
        definition = catalog.get(analyte_id)

    is_critical = bool(indicator.get("is_critical", False))
    critical_status = indicator.get("critical_status")
    if not critical_status and is_critical:
        critical_status = "critical_high" if status == "high" else "critical_low" if status == "low" else "critical_high"

    raw_explanation = str(indicator.get("explanation", "")).strip()
    if definition is not None:
        catalog_explanation = definition.explanation_for_status(status, critical_status=critical_status)
        if raw_explanation and raw_explanation != definition.curated_explanation:
            curated_explanation = raw_explanation
        else:
            curated_explanation = catalog_explanation or raw_explanation
    else:
        curated_explanation = raw_explanation

    chunks = await _retrieve_optional_context(
        retriever=retriever,
        rag_semaphore=rag_semaphore,
        analyte_id=analyte_id,
        name=name,
        status=status,
        band_id=_resolve_band_fallback(
            indicator,
            unit=unit,
            patient_gender=patient_gender_raw,
            patient_age=patient_age_raw,
        ),
        critical_status=critical_status,
    )
    known_sources = _known_sources(indicator, chunks)
    if definition and not known_sources:
        known_sources = list(definition.sources)
    safe_chunks = build_safe_grounding_view(chunks)
    safe_chunks = [
        {**chunk, "text": filtered}
        for chunk in safe_chunks
        if (filtered := filter_patient_education_text(str(chunk.get("text", ""))))
    ]
    rag_context = build_bounded_context(
        safe_chunks,
        max_chars=get_settings().max_analyzer_context_chars,
    )
    safe_curated_explanation = filter_patient_education_text(curated_explanation)
    safe_neutral_explanation = plain_definition(
        analyte_id=analyte_id,
        curated_description=(definition.curated_explanation if definition is not None else ""),
    )
    context = rag_context or safe_curated_explanation or safe_neutral_explanation
    fallback_explanation = build_patient_explanation(
        analyte_id=analyte_id,
        name=name,
        value=value,
        unit=unit,
        status=status,
        critical_status=critical_status,
        is_critical=is_critical,
        curated_description=(definition.curated_explanation if definition is not None else raw_explanation),
        supplemental_text=context,
    ) or load_templates().fallback_explanation

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
        1. Viết tối đa hai câu bổ sung bằng tiếng Việt thông dụng. Không lặp lại giá trị hoặc trạng thái; hệ thống sẽ ghép các dữ kiện đó riêng.
        2. Không thay đổi trạng thái, khoảng tham chiếu, đơn vị hoặc mức critical.
        3. KHÔNG chẩn đoán, suy đoán nguyên nhân, kê đơn hay đề nghị điều trị.
        4. Chỉ dùng thông tin có trong context. Nếu context không đủ, giữ lời giải thích tối thiểu.

        {GENERATION_SAFETY_CONTRACT}
        """
    )

    explanation_text = fallback_explanation
    if structured_llm is not None and context and status.strip().lower() != "unknown":
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
                explanation_text = build_patient_explanation(
                    analyte_id=analyte_id,
                    name=name,
                    value=value,
                    unit=unit,
                    status=status,
                    critical_status=critical_status,
                    is_critical=is_critical,
                    curated_description=(definition.curated_explanation if definition is not None else raw_explanation),
                    supplemental_text=result.explanation.strip(),
                )
        except Exception as exc:
            logger.error("LLM explanation failed for %s; using curated fallback: %s", name, exc)

    explanation_text = ensure_reference_qualification(
        explanation_text,
        status,
        critical_status=critical_status,
        is_critical=is_critical,
    )
    citations = _known_citations(
        analyte=(definition.indicator if definition is not None else name),
        sources=known_sources,
        chunks=safe_chunks,
    )

    explanation: IndicatorExplanation = {
        "indicator_name": name,
        "status": status,
        "critical_status": critical_status,
        "category": indicator.get("category", "unknown"),
        "is_abnormal": indicator.get("is_abnormal", False),
        "is_critical": is_critical,
        "explanation": explanation_text,
        # Never trust model-generated URLs. Only return sources supplied by the
        # authoritative catalog or retrieved document metadata.
        "sources": known_sources,
        "rule_type": indicator.get("rule_type"),
        "band_id": indicator.get("band_id"),
        "upper_operator": indicator.get("upper_operator"),
        "evaluation_reason": indicator.get("evaluation_reason"),
        "citations": citations,
    }
    updated_indicator = dict(indicator)
    updated_indicator["explanation"] = explanation_text
    updated_indicator["sources"] = known_sources
    updated_indicator["citations"] = citations
    updated_indicator["explanation_sources"] = citations
    return updated_indicator, explanation, safe_chunks


async def analyzer_node(state: AgentState) -> dict:
    """Enrich deterministic assessments while keeping RAG optional."""

    indicators = state.get("indicators", [])
    if not indicators:
        return {"retrieved_contexts": []}

    review_indicators = [
        dict(indicator)
        for indicator in indicators
        if indicator.get("input_integrity_status") == "NEED_REVIEW"
    ]
    analyzable_indicators = [
        indicator
        for indicator in indicators
        if indicator.get("input_integrity_status") != "NEED_REVIEW"
    ]
    if not analyzable_indicators:
        return {
            "indicators": review_indicators,
            "explanations": [],
            "retrieved_contexts": [],
        }

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
                patient_gender_raw=patient_gender,
                patient_age_raw=patient_age_value,
            )
            for indicator in analyzable_indicators
        ]
    )

    updated_indicators: list[dict[str, Any]] = []
    explanations: list[IndicatorExplanation] = []
    retrieved_contexts: list[RetrievedChunk] = []
    for updated_indicator, explanation, chunks in results:
        updated_indicators.append(updated_indicator)
        explanations.append(explanation)
        retrieved_contexts.extend(chunks)

    # Keep review-only rows visible and preserve input order, but never send
    # those rows to retrieval or an LLM.
    analyzed = iter(updated_indicators)
    updated_indicators = [
        dict(item)
        if item.get("input_integrity_status") == "NEED_REVIEW"
        else next(analyzed)
        for item in indicators
    ]

    return {
        "indicators": updated_indicators,
        "explanations": explanations,
        "retrieved_contexts": retrieved_contexts,
    }
