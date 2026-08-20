from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorSessionContext,
    ReasonCode,
    UIContext,
)

_COMPARISON_PATTERNS = (
    "so voi lan truoc",
    "so với lần trước",
    "compared with last time",
    "compare with last time",
)


@dataclass(frozen=True)
class ResolvedContext:
    current_report_ref: str | None
    current_analyte: str | None
    forced_intent: IntentEnum | None = None
    reason_code: ReasonCode | None = None


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[a-zA-Z0-9À-ỹ]+", text.casefold()))


def resolve_context(
    message: str,
    session: OrchestratorSessionContext,
    ui_context: UIContext | None,
) -> ResolvedContext:
    current_report_ref = session.current_report_ref
    current_analyte = session.current_analyte

    if ui_context is not None:
        current_report_ref = ui_context.candidate_report_ref or current_report_ref
        current_analyte = ui_context.candidate_analyte or current_analyte

    normalized = _normalize(message)
    asks_comparison = any(pattern in normalized for pattern in _COMPARISON_PATTERNS)
    if asks_comparison:
        if current_analyte:
            return ResolvedContext(
                current_report_ref=current_report_ref,
                current_analyte=current_analyte,
                forced_intent=IntentEnum.ANALYZE_TREND,
            )
        return ResolvedContext(
            current_report_ref=current_report_ref,
            current_analyte=current_analyte,
            reason_code=ReasonCode.AMBIGUOUS_CONTEXT,
        )

    return ResolvedContext(
        current_report_ref=current_report_ref,
        current_analyte=current_analyte,
    )
