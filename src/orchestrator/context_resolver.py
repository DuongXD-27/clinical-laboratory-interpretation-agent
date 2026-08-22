from __future__ import annotations

import re
from dataclasses import dataclass

from src.models.orchestrator_schemas import (
    IntentEnum,
    OrchestratorSessionContext,
    ReasonCode,
    UIContext,
)
from src.services.analyte_resolver import LOCKED_35_ANALYTES

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


def _extract_explicit_analyte(message: str) -> str | None:
    normalized = _normalize(message)
    for analyte in sorted(LOCKED_35_ANALYTES, key=len, reverse=True):
        token = _normalize(analyte)
        if re.search(rf"\b{re.escape(token)}\b", normalized):
            return analyte
    return None


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

    explicit_analyte = _extract_explicit_analyte(message)
    if explicit_analyte:
        current_analyte = explicit_analyte

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
            forced_intent=IntentEnum.ANALYZE_TREND,
        )

    return ResolvedContext(
        current_report_ref=current_report_ref,
        current_analyte=current_analyte,
    )
