from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.models.db import LabReport, ReportIndicator
from src.models.schemas import (
    TrendAnalyteSummary,
    TrendFilter,
    TrendPointResponse,
    TrendResponse,
)
from src.services.patient_service import get_patient_by_username

logger = logging.getLogger(__name__)

MIN_TREND_POINTS = 3
LATEST_POINT_LIMIT = 5
INSUFFICIENT_DATA_REASON = "INSUFFICIENT_DATA"
DATA_QUALITY_REASON = "DATA_QUALITY_ERROR"
NOT_FOUND_REASON = "ANALYTE_NOT_FOUND"


class TrendServiceError(ValueError):
    pass


class TrendDataQualityError(TrendServiceError):
    pass


@dataclass(frozen=True)
class TrendPoint:
    report_id: int
    test_date: date
    analyte_canonical: str
    canonical_value: float
    canonical_unit: str
    assessment: str


def _is_valid_point(report: LabReport, indicator: ReportIndicator) -> bool:
    return (
        report.patient_id is not None
        and report.test_date is not None
        and bool(indicator.analyte_canonical)
        and indicator.canonical_value is not None
        and isinstance(indicator.canonical_value, int | float)
        and bool(indicator.canonical_unit)
    )


def _query_candidate_rows(db: Session, *, patient_id: int) -> list[tuple[LabReport, ReportIndicator]]:
    return (
        db.query(LabReport, ReportIndicator)
        .join(ReportIndicator, ReportIndicator.report_id == LabReport.id)
        .filter(LabReport.patient_id == patient_id)
        .all()
    )


def _build_points(
    rows: list[tuple[LabReport, ReportIndicator]],
    *,
    analyte_canonical: str | None = None,
) -> list[TrendPoint]:
    duplicate_keys: Counter[tuple[int, str]] = Counter()
    for report, indicator in rows:
        if not _is_valid_point(report, indicator):
            continue
        canonical = str(indicator.analyte_canonical)
        if analyte_canonical is not None and canonical != analyte_canonical:
            continue
        duplicate_keys[(report.id, canonical)] += 1

    duplicates = [key for key, count in duplicate_keys.items() if count > 1]
    if duplicates:
        logger.error("Duplicate canonical analyte rows in one report: %s", duplicates)
        raise TrendDataQualityError("Một phiếu có nhiều kết quả cho cùng một chỉ số.")

    points: list[TrendPoint] = []
    for report, indicator in rows:
        if not _is_valid_point(report, indicator):
            continue
        canonical = str(indicator.analyte_canonical)
        if analyte_canonical is not None and canonical != analyte_canonical:
            continue
        points.append(
            TrendPoint(
                report_id=report.id,
                test_date=report.test_date,
                analyte_canonical=canonical,
                canonical_value=float(indicator.canonical_value),
                canonical_unit=str(indicator.canonical_unit),
                assessment=str(indicator.status),
            )
        )
    return points


def _assert_unit_consistency(points: list[TrendPoint]) -> str:
    units = {point.canonical_unit for point in points}
    if len(units) > 1:
        logger.error("Inconsistent canonical units for trend points: %s", sorted(units))
        raise TrendDataQualityError("Các kết quả chuẩn hóa có đơn vị không nhất quán.")
    return next(iter(units), "")


def get_patient_trend_analytes(db: Session, *, username: str) -> list[TrendAnalyteSummary]:
    patient = get_patient_by_username(db, username)
    rows = _query_candidate_rows(db, patient_id=patient.id)
    points = _build_points(rows)
    grouped: dict[str, list[TrendPoint]] = defaultdict(list)
    for point in points:
        grouped[point.analyte_canonical].append(point)

    summaries: list[TrendAnalyteSummary] = []
    for analyte, analyte_points in grouped.items():
        try:
            unit = _assert_unit_consistency(analyte_points)
        except TrendDataQualityError:
            unit = ""
            available = False
        else:
            available = len(analyte_points) >= MIN_TREND_POINTS
        summaries.append(
            TrendAnalyteSummary(
                analyte_canonical=analyte,
                display_name=analyte,
                canonical_unit=unit,
                result_count=len(analyte_points),
                trend_available=available,
            )
        )
    return sorted(summaries, key=lambda item: item.display_name.casefold())


def _apply_filter(points: list[TrendPoint], trend_filter: TrendFilter, *, today: date | None = None) -> list[TrendPoint]:
    sorted_desc = sorted(points, key=lambda point: (point.test_date, point.report_id), reverse=True)
    if trend_filter == "latest5":
        return sorted(sorted_desc[:LATEST_POINT_LIMIT], key=lambda point: (point.test_date, point.report_id))
    if trend_filter == "three_months":
        current_date = today or date.today()
        boundary = _subtract_months(current_date, 3)
        filtered = [
            point
            for point in points
            if boundary <= point.test_date <= current_date
        ]
        return sorted(filtered, key=lambda point: (point.test_date, point.report_id))
    raise TrendServiceError("Bộ lọc xu hướng không hợp lệ.")


def _subtract_months(value: date, months: int) -> date:
    month_index = value.month - months
    year = value.year + (month_index - 1) // 12
    month = (month_index - 1) % 12 + 1
    days_in_month = (
        29
        if month == 2 and (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        else [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]
    )
    return date(year, month, min(value.day, days_in_month))


def get_patient_trend(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
    today: date | None = None,
) -> TrendResponse:
    patient = get_patient_by_username(db, username)
    rows = _query_candidate_rows(db, patient_id=patient.id)
    try:
        all_points = _build_points(rows, analyte_canonical=analyte_canonical)
        unit = _assert_unit_consistency(all_points)
    except TrendDataQualityError:
        return TrendResponse(
            analyte_canonical=analyte_canonical,
            display_name=analyte_canonical,
            canonical_unit="",
            filter=trend_filter,
            result_count=0,
            trend_available=False,
            reason=DATA_QUALITY_REASON,
            points=[],
        )

    if not all_points:
        return TrendResponse(
            analyte_canonical=analyte_canonical,
            display_name=analyte_canonical,
            canonical_unit="",
            filter=trend_filter,
            result_count=0,
            trend_available=False,
            reason=NOT_FOUND_REASON,
            points=[],
        )

    filtered_points = _apply_filter(all_points, trend_filter, today=today)
    if len(filtered_points) < MIN_TREND_POINTS:
        return TrendResponse(
            analyte_canonical=analyte_canonical,
            display_name=analyte_canonical,
            canonical_unit=unit,
            filter=trend_filter,
            result_count=len(filtered_points),
            trend_available=False,
            reason=INSUFFICIENT_DATA_REASON,
            points=[],
        )

    return TrendResponse(
        analyte_canonical=analyte_canonical,
        display_name=analyte_canonical,
        canonical_unit=unit,
        filter=trend_filter,
        result_count=len(filtered_points),
        trend_available=True,
        points=[
            TrendPointResponse(
                report_id=point.report_id,
                test_date=point.test_date,
                value=point.canonical_value,
                assessment=point.assessment,
            )
            for point in filtered_points
        ],
    )
