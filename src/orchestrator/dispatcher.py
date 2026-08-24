from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass

from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    BlockedPayload,
    DataPayload,
    DoctorQuestionsPayload,
    ExplanationDataPayload,
    IntentEnum,
    NeedsInputPayload,
    ProgressStage,
    ReasonCode,
    ResponseStatus,
)
from src.orchestrator.errors import OrchestratorWrapperError
from src.orchestrator.progress import ProgressCallback, emit_progress
from src.orchestrator.wrappers import get_my_history, get_my_indicator_trend, get_my_report, get_report_questions
from src.services.auth import ROLE_GUEST
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError


@dataclass(frozen=True)
class DispatchContext:
    current_user: object
    db: object
    current_report_ref: str | None
    current_analyte: str | None
    progress_callback: ProgressCallback | None = None


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
        for indicator in report.indicators:
            names = {
                indicator.name,
                indicator.analyte_canonical or "",
                indicator.analyte_raw or "",
            }
            if context.current_analyte in names:
                return WorkflowResult(
                    status=ResponseStatus.SUCCESS,
                    data=ExplanationDataPayload(
                        explanation=indicator.explanation or "",
                        sources=list(indicator.sources or []),
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
        current_analyte=context.current_analyte,
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
