from __future__ import annotations

import re
import unicodedata
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataPayload,
    DoctorQuestionsPayload,
    ExplanationDataPayload,
    ExplanationIndicatorFacts,
    IntentEnum,
    NeedsInputPayload,
    ProgressStage,
    ReasonCode,
    ResponseStatus,
    canonical_critical_side,
)
from src.orchestrator.errors import OrchestratorWrapperError
from src.orchestrator.progress import ProgressCallback, emit_progress
from src.orchestrator.wrappers import get_my_history, get_my_indicator_trend, get_my_report, get_report_questions
from src.services.analyte_catalog import AnalyteCatalogError, get_analyte_catalog
from src.services.auth import ROLE_GUEST
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError


@dataclass(frozen=True)
class DispatchContext:
    current_user: object
    db: object
    current_report_ref: str | None
    current_analyte: str | None
    progress_callback: ProgressCallback | None = None
    # Raw patient message is used only for bounded presentation semantics and
    # the constrained provenance named-source verification path.
    message: str | None = None


@dataclass(frozen=True)
class WorkflowResult:
    status: ResponseStatus
    data: DataPayload
    reason_code: ReasonCode | None = None
    workflow_selected: str = ""


WorkflowHandler = Callable[[DispatchContext], Awaitable[WorkflowResult]]


def _blocked(reason_code: ReasonCode) -> WorkflowResult:
    return WorkflowResult(
        status=ResponseStatus.BLOCKED,
        reason_code=reason_code,
        data=BlockedPayload(
            safety_notice="Yêu cầu này chưa được hỗ trợ an toàn trong phiên tư vấn.",
            reason_code=reason_code,
        ),
    )


def _needs_input(reason_code: ReasonCode, prompt: str, missing_fields: list[str]) -> WorkflowResult:
    return WorkflowResult(
        status=ResponseStatus.NEEDS_INPUT,
        reason_code=reason_code,
        data=NeedsInputPayload(prompt=prompt, missing_fields=missing_fields),
    )


def _is_supported_analyte(name: str | None) -> bool:
    if not name:
        return True
    try:
        repository = ReferenceRepository.from_default_files()
    except ReferenceRepositoryError:
        return False
    canonical = repository.resolve_analyte(name)
    return canonical in repository.approved_analytes


def _normalize_question(message: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", (message or "").casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    without_accents = without_accents.replace("đ", "d")
    return " ".join(re.findall(r"[a-z0-9]+", without_accents))


def _explanation_presentation_mode(message: str | None) -> str:
    normalized = _normalize_question(message)
    if "la bao nhieu" in normalized:
        return "current_fact_first"
    if any(frame in normalized for frame in ("co cao khong", "co thap khong", "co binh thuong khong")):
        return "status_first"
    if any(frame in normalized for frame in ("la gi", "y nghia gi", "co y nghia")):
        return "education_first"
    return "mixed_explanation"


def _approved_educational_definition(analyte: str) -> tuple[str, list[str]]:
    """Return neutral approved-corpus prose, never competing patient facts."""
    try:
        definition = get_analyte_catalog().resolve(analyte)
    except AnalyteCatalogError:
        return "", []
    if definition is None:
        return "", []
    explanation = definition.curated_explanation.strip()
    normalized_explanation = _normalize_question(explanation)
    # Educational retrieval is not authoritative for patient-specific numbers
    # or reference ranges. Neutral durations such as "2-3 months" are safe.
    has_competing_numeric_fact = bool(re.search(r"\d", explanation)) and any(
        frame in normalized_explanation for frame in ("cua ban", "khoang tham chieu")
    )
    if not explanation or has_competing_numeric_fact:
        return "", []
    return explanation, list(dict.fromkeys(definition.sources))


async def _dispatch_analyze_report(context: DispatchContext) -> WorkflowResult:
    if context.current_analyte and not _is_supported_analyte(context.current_analyte):
        return _blocked(ReasonCode.UNSUPPORTED_ANALYTE)
    if not context.current_report_ref:
        return _needs_input(
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Vui lòng nhập chỉ số thủ công hoặc xác nhận OCR trước khi phân tích.",
            ["current_report_ref"],
        )
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=get_my_report(context.current_user, context.db, context.current_report_ref),
        workflow_selected="get_my_report",
    )


async def _dispatch_explain_current(context: DispatchContext) -> WorkflowResult:
    if not context.current_report_ref:
        role = getattr(context.current_user, "role", None)
        if role == ROLE_GUEST:
            return _blocked(ReasonCode.UNSUPPORTED_CAPABILITY)
        return _needs_input(
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Hiện mình chưa thấy phiếu xét nghiệm nào trong tài khoản của bạn.\n\nBạn có thể gửi ảnh phiếu xét nghiệm hoặc nhập kết quả để mình hỗ trợ.",
            ["current_report_ref"],
        )

    # Mode A: Single-analyte explanation
    if context.current_analyte:
        if not _is_supported_analyte(context.current_analyte):
            return _blocked(ReasonCode.UNSUPPORTED_ANALYTE)

        report = get_my_report(context.current_user, context.db, context.current_report_ref)
        presentation_mode = _explanation_presentation_mode(context.message)
        for indicator in report.indicators:
            names = {
                indicator.name,
                indicator.analyte_canonical or "",
                indicator.analyte_raw or "",
            }
            if context.current_analyte in names:
                explanation = indicator.explanation or ""
                sources = list(getattr(indicator, "sources", None) or [])
                if presentation_mode == "education_first":
                    report_explanation = explanation.strip()
                    explanation, education_sources = _approved_educational_definition(context.current_analyte)
                    if (
                        explanation
                        and report_explanation
                        and _normalize_question(report_explanation) not in _normalize_question(explanation)
                    ):
                        explanation = f"{explanation}\n\n{report_explanation}"
                    sources = list(dict.fromkeys([*education_sources, *sources]))
                value = getattr(indicator, "value", None)
                unit = getattr(indicator, "unit", None)
                status = getattr(indicator, "status", None)
                # ORCH-V1.4C: stop dropping authoritative facts. Carry the
                # canonical fact block so deterministic single-analyte
                # composition can present value/unit/status/range/critical
                # verbatim, with the approved explanation kept supplemental.
                # Fail-safe: an incomplete snapshot (no authoritative
                # value/unit/status) keeps the legacy prose-only contract
                # instead of inventing partial facts.
                if value is None or unit is None or status is None:
                    return WorkflowResult(
                        status=ResponseStatus.SUCCESS,
                        data=ExplanationDataPayload(
                            explanation=explanation,
                            sources=sources,
                            presentation_mode=presentation_mode,
                        ),
                        workflow_selected="get_my_report",
                    )
                reference_low = getattr(indicator, "reference_low", None)
                reference_high = getattr(indicator, "reference_high", None)
                # Preserve the APPROVED critical warning of the same
                # detector run for this analyte, verbatim (display only).
                approved_critical_message = None
                for alert in getattr(report, "critical_alerts", None) or []:
                    if getattr(alert, "indicator_name", None) in names:
                        message = getattr(alert, "message", None)
                        if message:
                            approved_critical_message = message
                            break
                return WorkflowResult(
                    status=ResponseStatus.SUCCESS,
                    data=ExplanationDataPayload(
                        explanation=explanation,
                        sources=sources,
                        presentation_mode=presentation_mode,
                        facts=ExplanationIndicatorFacts(
                            analyte_name=getattr(indicator, "analyte_canonical", None) or indicator.name,
                            value=value,
                            unit=unit,
                            status=str(status),
                            reference_low=reference_low,
                            reference_high=reference_high,
                            has_two_sided_reference_range=(
                                reference_low is not None and reference_high is not None
                            ),
                            critical_status=canonical_critical_side(getattr(indicator, "critical_status", None)),
                            approved_critical_message=approved_critical_message,
                        ),
                    ),
                    workflow_selected="get_my_report",
                )
        return _needs_input(
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Vui lòng chọn một chỉ số có trong phiếu hiện tại.",
            ["current_analyte"],
        )

    # Mode B: Whole-report summary
    report = get_my_report(context.current_user, context.db, context.current_report_ref)
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=report,
        workflow_selected="get_my_report_summary",
    )


async def _dispatch_history(context: DispatchContext) -> WorkflowResult:
    await emit_progress(context.progress_callback, ProgressStage.LONGITUDINAL_RETRIEVAL)
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=get_my_history(context.current_user, context.db),
        workflow_selected="get_my_history",
    )


async def _dispatch_trend(context: DispatchContext) -> WorkflowResult:
    if not context.current_analyte:
        return _needs_input(ReasonCode.AMBIGUOUS_CONTEXT, "Vui lòng chọn chỉ số cần xem xu hướng.", ["current_analyte"])
    if not _is_supported_analyte(context.current_analyte):
        return _blocked(ReasonCode.UNSUPPORTED_ANALYTE)
    await emit_progress(context.progress_callback, ProgressStage.LONGITUDINAL_RETRIEVAL)
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=get_my_indicator_trend(context.current_user, context.db, context.current_analyte),
        workflow_selected="get_my_indicator_trend",
    )


async def _dispatch_questions(context: DispatchContext) -> WorkflowResult:
    if not context.current_report_ref:
        return _needs_input(
            ReasonCode.AMBIGUOUS_CONTEXT,
            "Vui lòng chọn phiếu xét nghiệm để tạo câu hỏi cho bác sĩ.",
            ["current_report_ref"],
        )
    payload = get_report_questions(
        context.current_user,
        context.db,
        report_ref=context.current_report_ref,
        analyte=context.current_analyte,
    )
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=DoctorQuestionsPayload(questions=payload.questions),
        workflow_selected="get_report_questions",
    )


async def _dispatch_unsupported(_: DispatchContext) -> WorkflowResult:
    return _blocked(ReasonCode.UNKNOWN_INTENT)

async def _dispatch_safe_general(_: DispatchContext) -> WorkflowResult:
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=ExplanationDataPayload(
            explanation="Chào bạn. Tôi có thể giúp bạn xem và hiểu các kết quả xét nghiệm đã có, xem xu hướng, hoặc chuẩn bị câu hỏi để trao đổi với bác sĩ.",
            sources=[]
        ),
        workflow_selected="safe_general"
    )


# ---------------------------------------------------------------------------
# CHAT-V1.5-R1-G1: constrained provenance / source follow-up mode
#
# One canonical approved-source path. Sources come ONLY from the stored
# approved indicator sources of the current authorized report/analyte context
# (``get_my_report`` enforces patient ownership). Rendering is fully
# deterministic: no LLM participates, no source identity is invented, and no
# internal chunk/source IDs are exposed — only stored titles (URLs are kept
# verbatim when already present in the stored metadata).
# ---------------------------------------------------------------------------

NO_STORED_SOURCE_MESSAGE = (
    "Hiện tôi không có nguồn tham chiếu đã được lưu cho phần giải thích này."
)

_NAMED_SOURCE_PROBES: tuple[tuple[str, str], ...] = (
    ("who", "WHO"),
    ("cdc", "CDC"),
    ("vinmec", "Vinmec"),
    ("mayo clinic", "Mayo Clinic"),
    ("arup", "ARUP"),
)


def _detect_named_source_probe(message: str | None) -> tuple[str, str] | None:
    """Return ``(match_key, display_label)`` when the question names a source."""
    if not message:
        return None
    from src.orchestrator.gates import _normalize

    normalized = _normalize(message)
    for key, label in _NAMED_SOURCE_PROBES:
        if re.search(rf"\b{re.escape(key)}\b", normalized):
            return key, label
    return None


def _source_mentions(source: str, key: str) -> bool:
    return re.search(rf"\b{re.escape(key)}\b", source, re.IGNORECASE) is not None


def _dedupe_sources(sources: object) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in sources or []:
        text = str(raw).strip()
        if text and text not in seen:
            seen.add(text)
            ordered.append(text)
    return ordered


def _render_source_entries(sources: list[str]) -> list[str]:
    return [f"{index}. {source}" for index, source in enumerate(sources, start=1)]


def _compose_provenance_explanation(message: str | None, sources: list[str]) -> str:
    probe = _detect_named_source_probe(message)
    if probe is not None:
        key, label = probe
        present = any(_source_mentions(source, key) for source in sources)
        if present:
            lines = [
                f"Có. {label} nằm trong các nguồn tham chiếu đã được duyệt "
                "cho phần giải thích này:"
            ]
        elif not sources:
            return (
                "Hiện tôi không có nguồn tham chiếu nào được lưu cho phần giải thích "
                f"này, nên tôi không thể xác nhận nguồn {label}."
            )
        else:
            lines = [
                f"Trong các nguồn tham chiếu đã được duyệt cho phần giải thích này "
                f"không có nguồn {label}. Các nguồn hiện có:"
            ]
        lines.extend(_render_source_entries(sources))
        return "\n".join(lines)

    if not sources:
        return NO_STORED_SOURCE_MESSAGE
    lines = ["Phần giải thích này dựa trên các nguồn tham chiếu đã được duyệt sau:"]
    lines.extend(_render_source_entries(sources))
    return "\n".join(lines)


def _approved_sources_for_context(
    report: object, current_analyte: str | None
) -> list[str]:
    """Stored approved sources bound to the CURRENT context only.

    With an active analyte: only that analyte's sources. Without one: every
    approved indicator source of the current report, in stored order.
    """
    sources: list[str] = []
    if current_analyte:
        for indicator in getattr(report, "indicators", ()) or ():
            names = {
                getattr(indicator, "name", None),
                getattr(indicator, "analyte_canonical", None) or "",
                getattr(indicator, "analyte_raw", None) or "",
            }
            if current_analyte in names:
                sources.extend(getattr(indicator, "sources", None) or [])
                break
    else:
        for indicator in getattr(report, "indicators", ()) or ():
            sources.extend(getattr(indicator, "sources", None) or [])
    return _dedupe_sources(sources)


async def dispatch_provenance_followup(context: DispatchContext) -> WorkflowResult:
    """CHAT-V1.5-R1-G1 canonical provenance workflow.

    Deterministic; fail-closed on wrapper errors (ownership, DB). Never
    merges unrelated source pools and never fabricates a missing URL.
    """
    if not context.current_report_ref:
        return WorkflowResult(
            status=ResponseStatus.SUCCESS,
            data=ExplanationDataPayload(
                explanation=_compose_provenance_explanation(context.message, []),
                sources=[],
            ),
            workflow_selected="source_provenance",
        )
    try:
        report = get_my_report(context.current_user, context.db, context.current_report_ref)
        sources = _approved_sources_for_context(report, context.current_analyte)
    except OrchestratorWrapperError as exc:
        return _blocked(exc.reason_code)
    return WorkflowResult(
        status=ResponseStatus.SUCCESS,
        data=ExplanationDataPayload(
            explanation=_compose_provenance_explanation(context.message, sources),
            sources=list(sources),
        ),
        workflow_selected="source_provenance",
    )

WORKFLOW_DISPATCH: Mapping[IntentEnum, WorkflowHandler] = {
    IntentEnum.ANALYZE_REPORT: _dispatch_analyze_report,
    IntentEnum.EXPLAIN_CURRENT_RESULT: _dispatch_explain_current,
    IntentEnum.VIEW_HISTORY: _dispatch_history,
    IntentEnum.ANALYZE_TREND: _dispatch_trend,
    IntentEnum.GET_DOCTOR_QUESTIONS: _dispatch_questions,
    IntentEnum.UNSUPPORTED_OR_UNSAFE: _dispatch_unsupported,
    IntentEnum.SAFE_GENERAL: _dispatch_safe_general,
}


async def dispatch_workflow(intent: IntentEnum, context: DispatchContext) -> WorkflowResult:
    try:
        return await WORKFLOW_DISPATCH[intent](context)
    except OrchestratorWrapperError as exc:
        return _blocked(exc.reason_code)


def analysis_payload_from_response(response: object) -> AnalysisDataPayload | None:
    if isinstance(response, AnalysisDataPayload):
        return response
    indicators = getattr(response, "indicators", None)
    if indicators is None:
        return None
    return AnalysisDataPayload(
        indicators=list(indicators),
        critical_alerts=list(getattr(response, "critical_alerts", [])),
        has_critical_values=bool(getattr(response, "has_critical_values", False)),
    )
