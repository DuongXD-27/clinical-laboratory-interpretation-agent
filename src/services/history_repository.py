"""Đọc/ghi lịch sử xét nghiệm của bệnh nhân.

Repository này chịu trách nhiệm persistence và patient scoping cho lịch sử.

Schema canonical:
    users.id
        ↓
    lab_reports.patient_id
        ↓
    report_indicators.report_id

Authorization theo role vẫn được quyết định ở API route. Repository không tự
suy diễn role từ request; khi truy vấn lịch sử của một patient cụ thể, caller
phải truyền patient_id rõ ràng.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.models.db import (
    LabReport,
    OutOfScopeLog,
    ReportCriticalAlert,
    ReportIndicator,
    User,
)
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    IndicatorResultSchema,
    LabReportDetailSchema,
    LabReportSummarySchema,
)


def _normalize_indicator_name(name: str) -> str:
    """Chuẩn hóa tối thiểu để ghép metadata OCR với indicator kết quả."""
    return name.strip().casefold()


def _find_ocr_metadata(
    indicator_name: str,
    ocr_drafts: list[OCRIndicatorDraft] | None,
) -> tuple[float | None, str | None]:
    """Tìm metadata OCR tương ứng với một indicator.

    Chỉ gắn metadata khi tên indicator khớp. Không ghép theo index vì graph
    có thể thay đổi/drop/reorder indicator; ghép sai confidence/raw_text còn
    nguy hiểm hơn việc để metadata là NULL.
    """
    if not ocr_drafts:
        return None, None

    normalized_name = _normalize_indicator_name(indicator_name)

    for draft in ocr_drafts:
        if _normalize_indicator_name(draft.name) == normalized_name:
            return draft.confidence, draft.raw_text

    return None, None


def save_report(
    db: Session,
    *,
    patient_id: int,
    request: AnalyzeRequest,
    response: AnalyzeResponse,
    ocr_drafts: list[OCRIndicatorDraft] | None = None,
    ocr_source_filename: str | None = None,
) -> LabReport:
    """Lưu một lần phân tích vào lịch sử của patient.

    Chỉ route của authenticated patient được phép gọi hàm này.

    Không lưu:
    - ảnh OCR gốc;
    - is_abnormal/is_critical thành DB column;
    - source manual/ocr thành DB column.

    is_abnormal/is_critical được derive từ status.
    source được derive từ ocr_source_filename.
    """

    report_indicators: list[ReportIndicator] = []

    for indicator in response.indicators:
        ocr_confidence, ocr_raw_text = _find_ocr_metadata(
            indicator.name,
            ocr_drafts,
        )

        report_indicators.append(
            ReportIndicator(
                name=indicator.name,
                value=indicator.value,
                unit=indicator.unit,
                reference_low=indicator.reference_low,
                reference_high=indicator.reference_high,
                status=indicator.status,
                explanation=indicator.explanation or "",
                sources=list(indicator.sources or []),
                # indicator_catalog_id hiện để NULL nếu chưa có bước
                # canonical catalog resolution trong pipeline.
                indicator_catalog_id=None,
                ocr_confidence=ocr_confidence,
                ocr_raw_text=ocr_raw_text,
            )
        )

    critical_alerts = [
        ReportCriticalAlert(
            indicator_name=alert.indicator_name,
            value=alert.value,
            unit=alert.unit,
            message=alert.message,
        )
        for alert in response.critical_alerts
    ]

    out_of_scope_entries = [
        OutOfScopeLog(
            raw_indicator_name=indicator_name,
        )
        for indicator_name in response.out_of_scope_indicators
    ]

    report = LabReport(
        patient_id=patient_id,
        test_date=request.test_date,

        # Snapshot tại thời điểm xét nghiệm.
        patient_age_at_test=request.patient_age,
        patient_gender_at_test=request.patient_gender,

        # None = manual.
        # Có filename = report tới từ OCR.
        ocr_source_filename=ocr_source_filename,

        language=request.language,
        has_critical_values=response.has_critical_values,
        guardrail_passed=response.guardrail_passed,
        summary=response.summary or "",
        disclaimer=response.disclaimer or "",

        indicators=report_indicators,
        critical_alerts=critical_alerts,
        out_of_scope_entries=out_of_scope_entries,
    )

    db.add(report)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(report)

    return report


def _base_query(
    patient_id: int | None,
    from_date: date | None,
    to_date: date | None,
):
    """Tạo query history với date range inclusive."""

    stmt = select(LabReport)

    if patient_id is not None:
        stmt = stmt.where(
            LabReport.patient_id == patient_id
        )

    # Inclusive cả hai đầu:
    # from_date <= test_date <= to_date
    if from_date is not None:
        stmt = stmt.where(
            LabReport.test_date >= from_date
        )

    if to_date is not None:
        stmt = stmt.where(
            LabReport.test_date <= to_date
        )

    return stmt


def list_reports(
    db: Session,
    *,
    patient_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LabReportSummarySchema]]:
    """Trả về tổng số record và trang history hiện tại.

    patient_id=<id>:
        chỉ lấy report của patient đó.

    patient_id=None:
        không giới hạn patient ở repository level. Chỉ API route được phép
        quyết định role nào có quyền sử dụng chế độ này.
    """

    stmt = _base_query(
        patient_id,
        from_date,
        to_date,
    )

    total = (
        db.scalar(
            select(func.count()).select_from(
                stmt.subquery()
            )
        )
        or 0
    )

    rows = (
        db.execute(
            stmt.options(
                selectinload(LabReport.indicators),
                selectinload(LabReport.patient),
            )
            .order_by(
                LabReport.test_date.desc(),
                LabReport.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    return total, [
        _to_summary(report)
        for report in rows
    ]


def get_report(
    db: Session,
    report_id: int,
) -> LabReport | None:
    """Lấy một report cùng các child cần cho màn detail."""

    return (
        db.execute(
            select(LabReport)
            .where(
                LabReport.id == report_id
            )
            .options(
                selectinload(LabReport.patient),
                selectinload(LabReport.indicators),
                selectinload(LabReport.critical_alerts),
                selectinload(LabReport.questions),
                selectinload(LabReport.out_of_scope_entries),
            )
        )
        .scalar_one_or_none()
    )


def resolve_patient_id(
    db: Session,
    username: str,
) -> int | None:
    """Resolve username persistent thành users.id."""

    user = (
        db.execute(
            select(User).where(
                User.username == username
            )
        )
        .scalar_one_or_none()
    )

    if user is None:
        return None

    return user.id


def _derive_source(report: LabReport) -> str:
    """Presentation value; không phải DB column."""

    if report.ocr_source_filename is not None:
        return "ocr"

    return "manual"


def _to_summary(
    report: LabReport,
) -> LabReportSummarySchema:
    """Convert ORM report thành history-list item."""

    return LabReportSummarySchema(
        id=report.id,
        patient_username=(
            report.patient.username
            if report.patient is not None
            else None
        ),
        test_date=report.test_date,
        created_at=report.created_at,
        indicator_count=len(report.indicators),
        abnormal_count=sum(
            1
            for indicator in report.indicators
            if indicator.is_abnormal
        ),
        has_critical_values=report.has_critical_values,
        source=_derive_source(report),
        summary=report.summary,
    )


def to_detail(
    report: LabReport,
) -> LabReportDetailSchema:
    """Convert ORM report thành response detail đầy đủ."""

    return LabReportDetailSchema(
        id=report.id,
        patient_id=report.patient_id,
        patient_username=(
            report.patient.username
            if report.patient is not None
            else None
        ),
        test_date=report.test_date,
        created_at=report.created_at,

        patient_age_at_test=report.patient_age_at_test,
        patient_gender_at_test=report.patient_gender_at_test,

        language=report.language,
        summary=report.summary,
        has_critical_values=report.has_critical_values,
        guardrail_passed=report.guardrail_passed,
        disclaimer=report.disclaimer,

        indicator_count=len(report.indicators),
        abnormal_count=sum(
            1
            for indicator in report.indicators
            if indicator.is_abnormal
        ),
        source=_derive_source(report),

        indicators=[
            IndicatorResultSchema(
                name=indicator.name,
                value=indicator.value,
                unit=indicator.unit,
                reference_low=indicator.reference_low,
                reference_high=indicator.reference_high,
                status=indicator.status,
                is_abnormal=indicator.is_abnormal,
                is_critical=indicator.is_critical,
                explanation=indicator.explanation,
                sources=list(indicator.sources or []),
            )
            for indicator in report.indicators
        ],

        critical_alerts=list(
            report.critical_alerts
        ),

        questions=list(
            report.questions
        ),

        out_of_scope_entries=list(
            report.out_of_scope_entries
        ),
    )
