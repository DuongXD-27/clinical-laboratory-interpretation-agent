from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation

from sqlalchemy.orm import Session, selectinload

from src.models.db import (
    LabReport,
    OutOfScopeLog,
    ReportCriticalAlert,
    ReportIndicator,
)
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, SaveReportRequest
from src.services.patient_service import get_patient_by_username
from src.services.reference_repository import ReferenceRepository

logger = logging.getLogger(__name__)


class LabHistoryError(ValueError):
    pass


class MissingTestDateError(LabHistoryError):
    pass


class ReportNotFoundError(LabHistoryError):
    pass


@dataclass(frozen=True)
class SaveReportResult:
    saved: bool
    duplicate: bool
    report_id: int | None
    existing_report_id: int | None = None
    requires_date_confirmation: bool = False


_CANONICAL_ANALYTE_FALLBACKS = {
    "glucose": "Fasting plasma glucose",
}


def _resolve_canonical_analyte(repository: ReferenceRepository, analyte: str | None) -> str | None:
    if not analyte:
        return None
    resolved = repository.resolve_analyte(analyte)
    if resolved:
        return resolved
    return _CANONICAL_ANALYTE_FALLBACKS.get(analyte.strip().casefold())


def _report_status(indicators: Iterable[object]) -> str:
    has_abnormal = False
    for indicator in indicators:
        if isinstance(indicator, dict):
            status = str(indicator.get("status", ""))
            critical_status = str(indicator.get("critical_status") or "")
            is_abnormal = bool(indicator.get("is_abnormal"))
            is_critical = bool(indicator.get("is_critical"))
        else:
            status = str(getattr(indicator, "status", ""))
            critical_status = str(getattr(indicator, "critical_status", None) or "")
            is_abnormal = bool(getattr(indicator, "is_abnormal", False))
            is_critical = bool(getattr(indicator, "is_critical", False))
        normalized_status = status.casefold()
        normalized_crit = critical_status.casefold()
        if (
            is_critical
            or normalized_status in {"critical_low", "critical_high"}
            or normalized_crit in {"critical_low", "critical_high"}
        ):
            return "CRITICAL"
        if is_abnormal or normalized_status in {"low", "high"}:
            has_abnormal = True
    return "ABNORMAL" if has_abnormal else "NORMAL"


def _number_key(value: float | int | None) -> str:
    if value is None:
        return ""
    try:
        decimal_value = Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return str(value)
    return format(decimal_value, "f")


def generate_report_fingerprint(
    *,
    patient_id: int,
    test_date: date,
    results: list[dict],
) -> str:
    items = [
        {
            "analyte_canonical": item["analyte_canonical"],
            "canonical_value": _number_key(item["canonical_value"]),
            "canonical_unit": item["canonical_unit"],
        }
        for item in sorted(
            results,
            key=lambda row: (
                str(row.get("analyte_canonical") or ""),
                _number_key(row.get("canonical_value")),
                str(row.get("canonical_unit") or ""),
            ),
        )
    ]
    payload = {
        "patient_id": patient_id,
        "test_date": test_date.isoformat(),
        "results": items,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _canonical_result_rows(
    *,
    request: AnalyzeRequest,
    analysis: AnalyzeResponse,
    repository: ReferenceRepository,
) -> list[dict]:
    rows: list[dict] = []
    def dump(value):
        return value.model_dump(mode="json") if hasattr(value, "model_dump") else value

    for index, indicator in enumerate(analysis.indicators):
        raw_input = request.indicators[index] if index < len(request.indicators) else None
        raw_name = raw_input.name if raw_input is not None else indicator.name
        raw_value = raw_input.value if raw_input is not None else indicator.value
        raw_unit = raw_input.unit if raw_input is not None else indicator.unit
        canonical_source = indicator.analyte_canonical or raw_name or indicator.name
        canonical = _resolve_canonical_analyte(repository, canonical_source)
        canonical_name = canonical or indicator.analyte_canonical or raw_name or indicator.name
        canonical_unit = repository.normalize_unit(indicator.canonical_unit or raw_unit or indicator.unit)
        rows.append(
            {
                "analyte_raw": raw_name,
                "analyte_canonical": canonical_name,
                "raw_value": raw_value,
                "raw_unit": raw_unit,
                "canonical_value": indicator.canonical_value
                if indicator.canonical_value is not None
                else indicator.value,
                "canonical_unit": canonical_unit,
                "name": canonical_name,
                "value": indicator.value,
                "unit": indicator.unit,
                "reference_low": indicator.reference_low,
                "reference_high": indicator.reference_high,
                "status": indicator.status,
                "critical_status": indicator.critical_status,
                "rule_type": indicator.rule_type,
                "band_id": indicator.band_id,
                "upper_operator": indicator.upper_operator,
                "evaluation_reason": indicator.evaluation_reason,
                "explanation": indicator.explanation or "",
                "sources": indicator.sources or [],
                "analysis_provenance": {
                    "schema_version": 1,
                    "comparison_value": indicator.comparison_value,
                    "comparison_unit": indicator.comparison_unit,
                    "conversion_applied": indicator.conversion_applied,
                    "conversion_rule": indicator.conversion_rule,
                    "conversion_authority": indicator.conversion_authority,
                    "rule_id": indicator.rule_id,
                    "band_label": indicator.band_label,
                    "band_lower": indicator.band_lower,
                    "band_upper": indicator.band_upper,
                    "lower_operator": indicator.lower_operator,
                    "classification_provenance": dump(indicator.classification_provenance),
                    "retrieved_evidence": [dump(item) for item in indicator.retrieved_evidence],
                    "explanation_sources": [dump(item) for item in indicator.explanation_sources],
                    "artifact_provenance": dump(indicator.artifact_provenance),
                },
            }
        )
    return rows


def save_analyzed_report(
    db: Session,
    *,
    username: str,
    request: AnalyzeRequest,
    analysis: AnalyzeResponse,
    source_image: str | None = None,
) -> SaveReportResult:
    if request.test_date is None:
        return SaveReportResult(
            saved=False,
            duplicate=False,
            report_id=None,
            requires_date_confirmation=True,
        )

    patient = get_patient_by_username(db, username)
    repository = ReferenceRepository.from_default_files()
    result_rows = _canonical_result_rows(request=request, analysis=analysis, repository=repository)
    fingerprint = generate_report_fingerprint(
        patient_id=patient.id,
        test_date=request.test_date,
        results=result_rows,
    )

    existing = (
        db.query(LabReport)
        .filter(
            LabReport.patient_id == patient.id,
            LabReport.report_fingerprint == fingerprint,
        )
        .first()
    )
    if existing is not None:
        return SaveReportResult(
            saved=False,
            duplicate=True,
            report_id=None,
            existing_report_id=existing.id,
        )

    report = LabReport(
        patient_id=patient.id,
        test_date=request.test_date,
        patient_age_at_test=request.patient_age,
        patient_gender_at_test=request.patient_gender,
        ocr_source_filename=source_image,
        language=request.language,
        status=_report_status(analysis.indicators),
        report_fingerprint=fingerprint,
        summary=analysis.summary or "",
        has_critical_values=analysis.has_critical_values,
        guardrail_passed=analysis.guardrail_passed,
        disclaimer=analysis.disclaimer or "",
    )
    seen_exact_entries: set[tuple[str, str, str]] = set()
    for row in result_rows:
        canonical_name = row.get("analyte_canonical")
        canonical_val_str = _number_key(row.get("canonical_value"))
        canonical_unit_str = str(row.get("canonical_unit") or "")
        exact_key = (str(canonical_name or ""), canonical_val_str, canonical_unit_str)
        if canonical_name and exact_key in seen_exact_entries:
            logger.info(
                "save_analyzed_report_exact_duplicate_collapsed",
                extra={"analyte_canonical": canonical_name, "value": canonical_val_str, "patient_id": patient.id},
            )
            continue
        if canonical_name:
            seen_exact_entries.add(exact_key)
        report.indicators.append(ReportIndicator(**row))
    for alert in analysis.critical_alerts:
        report.critical_alerts.append(
            ReportCriticalAlert(
                indicator_name=alert.indicator_name,
                value=alert.value,
                unit=alert.unit,
                message=alert.message,
            )
        )
    for name in analysis.out_of_scope_indicators:
        report.out_of_scope_entries.append(OutOfScopeLog(raw_indicator_name=name))

    db.add(report)
    db.commit()
    db.refresh(report)
    from src.services.doctor_review_service import refresh_review_flags

    refresh_review_flags(db, report)
    return SaveReportResult(saved=True, duplicate=False, report_id=report.id)


def save_report_snapshot(
    db: Session,
    *,
    username: str,
    request: SaveReportRequest,
) -> SaveReportResult:
    if request.test_date is None:
        return SaveReportResult(
            saved=False,
            duplicate=False,
            report_id=None,
            requires_date_confirmation=True,
        )
    analyze_request = AnalyzeRequest(
        patient_age=request.patient_age or 0,
        patient_gender=request.patient_gender or "other",
        test_date=request.test_date,
        language=request.language,
        indicators=[
            {
                "name": indicator.name,
                "value": indicator.value,
                "unit": indicator.unit,
            }
            for indicator in request.analysis.indicators
        ],
    )
    return save_analyzed_report(
        db,
        username=username,
        request=analyze_request,
        analysis=request.analysis,
        source_image=request.source_image,
    )


def get_dashboard_summary(db: Session, *, username: str, limit: int = 5) -> dict:
    patient = get_patient_by_username(db, username)
    total = db.query(LabReport).filter(LabReport.patient_id == patient.id).count()
    reports = (
        db.query(LabReport)
        .options(selectinload(LabReport.indicators))
        .filter(LabReport.patient_id == patient.id)
        .order_by(LabReport.test_date.desc(), LabReport.created_at.desc())
        .limit(limit)
        .all()
    )
    return {
        "total_reports": total,
        "latest_test_date": reports[0].test_date if reports else None,
        "recent_reports": [_summary_row(report) for report in reports],
        "newly_verified_count": sum(1 for report in reports if report.verification_status == "verified"),
    }


def list_reports(db: Session, *, username: str) -> list[dict]:
    patient = get_patient_by_username(db, username)
    reports = (
        db.query(LabReport)
        .options(selectinload(LabReport.indicators))
        .filter(LabReport.patient_id == patient.id)
        .order_by(LabReport.test_date.desc(), LabReport.created_at.desc())
        .all()
    )
    return [_summary_row(report) for report in reports]


def get_report_detail(db: Session, *, username: str, report_id: int) -> LabReport:
    patient = get_patient_by_username(db, username)
    report = (
        db.query(LabReport)
        .options(
            selectinload(LabReport.indicators),
            selectinload(LabReport.critical_alerts),
            selectinload(LabReport.questions),
            selectinload(LabReport.out_of_scope_entries),
        )
        .filter(LabReport.id == report_id, LabReport.patient_id == patient.id)
        .first()
    )
    if report is None:
        raise ReportNotFoundError("Không tìm thấy phiếu xét nghiệm.")
    return report


def delete_report(db: Session, *, username: str, report_id: int) -> None:
    report = get_report_detail(db, username=username, report_id=report_id)
    db.delete(report)
    db.commit()


def _summary_row(report: LabReport) -> dict:
    status = _report_status(report.indicators)
    return {
        "report_id": report.id,
        "test_date": report.test_date,
        "result_count": len(report.indicators),
        "status": status,
        "created_at": report.created_at,
        "verification_status": report.verification_status or "unverified",
        "verified_at": report.verified_at,
    }
