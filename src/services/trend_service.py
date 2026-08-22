from __future__ import annotations

import logging
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date

from sqlalchemy.orm import Session

from src.models.db import LabReport, ReportIndicator
from src.models.schemas import (
    CriticalAlertSchema,
    ObservedDirection,
    SectionTrendsResponse,
    TrendAnalyteSummary,
    TrendFilter,
    TrendPointResponse,
    TrendResponse,
)
from src.services.analyte_sections import analyte_section, section_label
from src.services.critical_value_service import approaches_critical, evaluate_critical
from src.services.indicator_catalog_service import get_indicator_configuration_service
from src.services.patient_service import get_patient_by_username

logger = logging.getLogger(__name__)

MIN_TREND_POINTS = 3
LATEST_POINT_LIMIT = 5
INSUFFICIENT_DATA_REASON = "INSUFFICIENT_DATA"
DATA_QUALITY_REASON = "DATA_QUALITY_ERROR"
NOT_FOUND_REASON = "ANALYTE_NOT_FOUND"
GAP_TOO_LARGE_REASON = "GAP_TOO_LARGE"


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


def get_report_patient_snapshot(db: Session, *, report_id: int) -> tuple[str | None, int | None]:
    """Trạng thái giới tính/tuổi bệnh nhân tại thời điểm phiếu ``report_id`` được ghi nhận.

    Dùng để khớp đúng khoảng tham chiếu theo sex/age (ADR-010 CRIT-TREND-02) — cùng snapshot
    mà pipeline chính đã dùng, không phải giới tính/tuổi hiện tại của bệnh nhân.
    """
    report = db.query(LabReport).filter(LabReport.id == report_id).first()
    if report is None:
        return None, None
    return report.patient_gender_at_test, report.patient_age_at_test


def _latest_critical_state(
    analyte_canonical: str,
    unit: str,
    points: list[TrendPoint],
) -> tuple[str | None, bool, CriticalAlertSchema | None]:
    """ADR-010 CRIT-TREND-03: đánh giá điểm mới nhất bằng module ngưỡng nguy kịch dùng chung.

    Chỉ áp dụng cho các chỉ số có threshold active (glucose, potassium theo ADR-009) — với
    các chỉ số khác ``evaluate_critical`` trả ``evaluated=False`` và không có cảnh báo nào được sinh.
    """
    if len(points) < 2:
        return None, False, None
    latest, previous = points[-1], points[-2]
    evaluation = evaluate_critical(analyte_canonical, latest.canonical_value, unit)
    if evaluation.is_critical:
        critical_alert = (
            CriticalAlertSchema(
                indicator_name=analyte_canonical,
                value=latest.canonical_value,
                unit=unit,
                message=evaluation.alert_message,
            )
            if evaluation.alert_message is not None
            else None
        )
        return evaluation.critical_status, False, critical_alert
    if evaluation.evaluated:
        approaching = approaches_critical(evaluation, previous.canonical_value)
        return None, approaching, None
    return None, False, None


def _observed_direction(points: list[TrendPoint]) -> ObservedDirection | None:
    if len(points) < MIN_TREND_POINTS:
        return None
    if all(
        points[index].canonical_value > points[index - 1].canonical_value
        for index in range(1, len(points))
    ):
        return "increasing"
    if all(
        points[index].canonical_value < points[index - 1].canonical_value
        for index in range(1, len(points))
    ):
        return "decreasing"
    return None


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
            available = len(
                _apply_max_gap_policy(analyte_points, _max_gap_days_for(analyte))
            ) >= MIN_TREND_POINTS
        section = analyte_section(analyte)
        summaries.append(
            TrendAnalyteSummary(
                analyte_canonical=analyte,
                display_name=analyte,
                canonical_unit=unit,
                result_count=len(analyte_points),
                trend_available=available,
                section=section,
                section_label=section_label(section),
            )
        )
    return sorted(summaries, key=lambda item: item.display_name.casefold())


def _apply_filter(
    points: list[TrendPoint], trend_filter: TrendFilter, *, today: date | None = None
) -> list[TrendPoint]:
    sorted_desc = sorted(points, key=lambda point: (point.test_date, point.report_id), reverse=True)
    if trend_filter == "latest5":
        return sorted(sorted_desc[:LATEST_POINT_LIMIT], key=lambda point: (point.test_date, point.report_id))
    if trend_filter == "three_months":
        current_date = today or date.today()
        boundary = _subtract_months(current_date, 3)
        filtered = [point for point in points if boundary <= point.test_date <= current_date]
        return sorted(filtered, key=lambda point: (point.test_date, point.report_id))
    raise TrendServiceError("Bộ lọc xu hướng không hợp lệ.")


def _apply_max_gap_policy(points: list[TrendPoint], max_gap_days: int | None) -> list[TrendPoint]:
    """Keep the newest uninterrupted sequence when a configured gap is exceeded."""
    if max_gap_days is None or len(points) < 2:
        return points
    contiguous = [points[-1]]
    for point in reversed(points[:-1]):
        if (contiguous[-1].test_date - point.test_date).days > max_gap_days:
            break
        contiguous.append(point)
    return list(reversed(contiguous))


def _max_gap_days_for(analyte_canonical: str) -> int | None:
    configuration = get_indicator_configuration_service().get(analyte_canonical)
    return configuration.max_gap_days if configuration is not None else None


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
    section = analyte_section(analyte_canonical)
    section_fields = {"section": section, "section_label": section_label(section)}
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
            **section_fields,
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
            **section_fields,
        )

    filtered_points = _apply_filter(all_points, trend_filter, today=today)
    gap_filtered_points = _apply_max_gap_policy(
        filtered_points,
        _max_gap_days_for(analyte_canonical),
    )
    gap_limited = len(gap_filtered_points) < len(filtered_points)
    filtered_points = gap_filtered_points
    if len(filtered_points) < MIN_TREND_POINTS:
        return TrendResponse(
            analyte_canonical=analyte_canonical,
            display_name=analyte_canonical,
            canonical_unit=unit,
            filter=trend_filter,
            result_count=len(filtered_points),
            trend_available=False,
            reason=GAP_TOO_LARGE_REASON if gap_limited else INSUFFICIENT_DATA_REASON,
            points=[],
            **section_fields,
        )

    observed_direction = _observed_direction(filtered_points)
    critical_status, approaching_critical, critical_alert = _latest_critical_state(
        analyte_canonical,
        unit,
        filtered_points,
    )

    return TrendResponse(
        analyte_canonical=analyte_canonical,
        display_name=analyte_canonical,
        canonical_unit=unit,
        filter=trend_filter,
        result_count=len(filtered_points),
        trend_available=True,
        observed_direction=observed_direction,
        points=[
            TrendPointResponse(
                report_id=point.report_id,
                test_date=point.test_date,
                value=point.canonical_value,
                assessment=point.assessment,
            )
            for point in filtered_points
        ],
        critical_status=critical_status,
        approaching_critical=approaching_critical,
        critical_alert=critical_alert,
        **section_fields,
    )

def get_patient_section_trends(
    db: Session,
    *,
    username: str,
    section: str,
    trend_filter: TrendFilter,
    today: date | None = None,
) -> SectionTrendsResponse:
    """Fetch trends for all trend-available analytes within a functional section.

    Returns a SectionTrendsResponse containing trend data per analyte,
    reusing the existing get_patient_trend logic for each analyte.
    """
    patient = get_patient_by_username(db, username)
    rows = _query_candidate_rows(db, patient_id=patient.id)

    analytes_in_section: list[str] = []
    seen: set[str] = set()
    for report, indicator in rows:
        canonical = str(indicator.analyte_canonical)
        analyte_section_key = analyte_section(canonical)
        if analyte_section_key == section and canonical not in seen:
            seen.add(canonical)
            analytes_in_section.append(canonical)

    trends: list[TrendResponse] = [
        get_patient_trend(
            db,
            username=username,
            analyte_canonical=analyte,
            trend_filter=trend_filter,
            today=today,
        )
        for analyte in analytes_in_section
    ]
    trends = [t for t in trends if t.trend_available]

    return SectionTrendsResponse(
        section=section,
        section_label=section_label(section),
        trends=trends,
    )
