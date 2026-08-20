from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date
from typing import Any

from pydantic import BaseModel
from sqlalchemy import select

from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, LabReport
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    DoctorQuestionsPayload,
    HistorySummaryPayload,
    ReasonCode,
    TrendDataPayload,
)
from src.models.schemas import AnalyzeResponse, TrendFilter
from src.orchestrator.errors import OrchestratorWrapperError
from src.services import history_repository, trend_service
from src.services.auth import ROLE_GUEST
from src.services.question_templates import generate_questions


def _raise(reason_code: ReasonCode) -> None:
    raise OrchestratorWrapperError(reason_code)


def _role_of(current_user: object) -> str:
    role = getattr(current_user, "role", None)
    username = getattr(current_user, "username", None)
    if not isinstance(role, str) or not isinstance(username, str) or not username:
        _raise(ReasonCode.AUTH_EXPIRED)
    if role not in {ROLE_GUEST, ROLE_PATIENT, ROLE_DOCTOR}:
        _raise(ReasonCode.AUTH_EXPIRED)
    return role


def _require_patient(current_user: object) -> tuple[str, int]:
    role = _role_of(current_user)
    if role == ROLE_DOCTOR:
        _raise(ReasonCode.UNSUPPORTED_CAPABILITY)
    if role == ROLE_GUEST:
        _raise(ReasonCode.UNSUPPORTED_CAPABILITY)
    actor_key = getattr(current_user, "user_id", None)
    username = getattr(current_user, "username")
    if not isinstance(actor_key, int):
        _raise(ReasonCode.AUTH_EXPIRED)
    return username, actor_key


def _require_non_doctor(current_user: object) -> str:
    role = _role_of(current_user)
    if role == ROLE_DOCTOR:
        _raise(ReasonCode.UNSUPPORTED_CAPABILITY)
    return role


def _parse_report_ref(report_ref: object) -> int:
    try:
        report_key = int(str(report_ref))
    except (TypeError, ValueError):
        _raise(ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED)
    if report_key <= 0:
        _raise(ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED)
    return report_key


def _history_filters(filters: Mapping[str, object] | None) -> tuple[date | None, date | None]:
    if filters is None:
        return None, None
    from_date = filters.get("from_date") if isinstance(filters.get("from_date"), date) else None
    to_date = filters.get("to_date") if isinstance(filters.get("to_date"), date) else None
    return from_date, to_date


def _owned_report(current_user: object, db: object, report_ref: object) -> LabReport:
    _, actor_key = _require_patient(current_user)
    report_key = _parse_report_ref(report_ref)
    try:
        owner_key = db.scalar(select(LabReport.patient_id).where(LabReport.id == report_key))
    except Exception as exc:
        raise OrchestratorWrapperError(ReasonCode.DB_UNAVAILABLE) from exc
    if owner_key != actor_key:
        _raise(ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED)
    try:
        report = history_repository.get_report(db, report_key)
    except Exception as exc:
        raise OrchestratorWrapperError(ReasonCode.DB_UNAVAILABLE) from exc
    if report is None or report.patient_id != actor_key:
        _raise(ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED)
    return report


def _indicator_mappings(session_result: object) -> list[Mapping[str, Any]]:
    if isinstance(session_result, AnalysisDataPayload | AnalyzeResponse):
        indicators = session_result.indicators
    else:
        indicators = getattr(session_result, "indicators", None)
    if indicators is None:
        _raise(ReasonCode.AMBIGUOUS_CONTEXT)
    mapped: list[Mapping[str, Any]] = []
    for indicator in indicators:
        if isinstance(indicator, BaseModel):
            mapped.append(indicator.model_dump())
        elif isinstance(indicator, Mapping):
            mapped.append(indicator)
        else:
            _raise(ReasonCode.AMBIGUOUS_CONTEXT)
    return mapped


def get_my_history(current_user: object, db: object, filters: Mapping[str, object] | None = None) -> HistorySummaryPayload:
    _, actor_key = _require_patient(current_user)
    from_date, to_date = _history_filters(filters)
    try:
        _, items = history_repository.list_reports(
            db,
            patient_id=actor_key,
            from_date=from_date,
            to_date=to_date,
            limit=1,
            offset=0,
        )
    except Exception as exc:
        raise OrchestratorWrapperError(ReasonCode.DB_UNAVAILABLE) from exc
    if not items:
        _raise(ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED)
    item = items[0]
    return HistorySummaryPayload(
        report_ref=str(item.id),
        test_date=item.test_date.isoformat(),
        summary=item.summary or "",
        status=item.status,
        has_critical_values=item.has_critical_values,
        result_count=item.indicator_count or item.result_count or 0,
        reviewed_by_doctor=item.reviewed_by_doctor,
        verification_status=item.verification_status,
    )


def get_my_report(current_user: object, db: object, report_ref: object) -> AnalysisDataPayload:
    report = _owned_report(current_user, db, report_ref)
    detail = history_repository.to_detail(report)
    return AnalysisDataPayload(
        indicators=detail.indicators,
        critical_alerts=detail.critical_alerts,
        has_critical_values=detail.has_critical_values,
    )


def get_my_indicator_trend(
    current_user: object,
    db: object,
    analyte: str,
    filters: Mapping[str, object] | None = None,
) -> TrendDataPayload:
    username, _ = _require_patient(current_user)
    trend_filter: TrendFilter = "latest5"
    if filters and filters.get("filter") in {"latest5", "three_months"}:
        trend_filter = filters["filter"]
    try:
        trend = trend_service.get_patient_trend(
            db,
            username=username,
            analyte_canonical=analyte,
            trend_filter=trend_filter,
        )
    except Exception as exc:
        raise OrchestratorWrapperError(ReasonCode.DB_UNAVAILABLE) from exc
    if trend.reason == trend_service.DATA_QUALITY_REASON:
        _raise(ReasonCode.TREND_UNIT_INCONSISTENT)
    if not trend.trend_available:
        _raise(ReasonCode.TREND_INSUFFICIENT_POINTS)
    return TrendDataPayload(trend=trend)


def get_report_questions(
    current_user: object,
    db: object,
    *,
    session_result: object | None = None,
    report_ref: object | None = None,
) -> DoctorQuestionsPayload:
    role = _require_non_doctor(current_user)
    if report_ref is not None:
        if role == ROLE_GUEST:
            _raise(ReasonCode.UNSUPPORTED_CAPABILITY)
        report = _owned_report(current_user, db, report_ref)
        detail = history_repository.to_detail(report)
        indicators: Sequence[Mapping[str, Any]] = [indicator.model_dump() for indicator in detail.indicators]
    elif session_result is not None:
        indicators = _indicator_mappings(session_result)
    else:
        _raise(ReasonCode.AMBIGUOUS_CONTEXT)
    return DoctorQuestionsPayload(questions=generate_questions(indicators))
