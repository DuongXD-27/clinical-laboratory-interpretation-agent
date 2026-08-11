"""Đọc/ghi lịch sử xét nghiệm của bệnh nhân.

Tách khỏi route để phần quyết định "ai được xem gì" nằm gọn một chỗ: mọi truy
vấn lịch sử đều đi qua đây và đều nhận `patient_user_id` tường minh — không có
đường nào lấy được phiếu của bệnh nhân khác bằng cách quên một mệnh đề WHERE.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.models.db import LabReport, LabReportIndicator, User
from src.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    LabReportDetailSchema,
    LabReportSummarySchema,
)


def save_report(
    db: Session,
    *,
    patient_user_id: int,
    request: AnalyzeRequest,
    response: AnalyzeResponse,
    source: str = "manual",
) -> LabReport:
    """Lưu một lần phân tích thành phiếu trong lịch sử của bệnh nhân."""
    report = LabReport(
        patient_user_id=patient_user_id,
        test_date=request.test_date,
        patient_age=request.patient_age,
        patient_gender=request.patient_gender,
        language=request.language,
        has_critical_values=response.has_critical_values,
        guardrail_passed=response.guardrail_passed,
        summary=response.summary or "",
        source=source,
        indicators=[
            LabReportIndicator(
                name=ind.name,
                value=ind.value,
                unit=ind.unit,
                reference_low=ind.reference_low,
                reference_high=ind.reference_high,
                status=ind.status,
                is_abnormal=ind.is_abnormal,
                is_critical=ind.is_critical,
                explanation=ind.explanation or "",
                sources=list(ind.sources),
            )
            for ind in response.indicators
        ],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _base_query(patient_user_id: int | None, from_date: date | None, to_date: date | None):
    stmt = select(LabReport)
    if patient_user_id is not None:
        stmt = stmt.where(LabReport.patient_user_id == patient_user_id)
    # Khoảng ngày lọc theo test_date và bao gồm cả hai đầu mút: người dùng nhập
    # "từ 04 đến 07" thì phiếu ngày 04 và ngày 07 phải nằm trong kết quả.
    if from_date is not None:
        stmt = stmt.where(LabReport.test_date >= from_date)
    if to_date is not None:
        stmt = stmt.where(LabReport.test_date <= to_date)
    return stmt


def list_reports(
    db: Session,
    *,
    patient_user_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LabReportSummarySchema]]:
    """Trả về (tổng số bản ghi khớp bộ lọc, trang hiện tại).

    `patient_user_id=None` chỉ dùng cho bác sĩ xem toàn bộ bệnh nhân; route phải
    tự chặn trước, hàm này không đoán quyền.
    """
    stmt = _base_query(patient_user_id, from_date, to_date)

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    rows = (
        db.execute(
            stmt.options(selectinload(LabReport.indicators), selectinload(LabReport.patient))
            .order_by(LabReport.test_date.desc(), LabReport.id.desc())
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return total, [_to_summary(r) for r in rows]


def get_report(db: Session, report_id: int) -> LabReport | None:
    return db.execute(
        select(LabReport)
        .where(LabReport.id == report_id)
        .options(selectinload(LabReport.indicators), selectinload(LabReport.patient))
    ).scalar_one_or_none()


def resolve_patient_id(db: Session, username: str) -> int | None:
    user = db.execute(select(User).where(User.username == username)).scalar_one_or_none()
    return None if user is None else user.id


def _to_summary(report: LabReport) -> LabReportSummarySchema:
    return LabReportSummarySchema(
        id=report.id,
        patient_username=report.patient.username,
        test_date=report.test_date,
        created_at=report.created_at,
        indicator_count=len(report.indicators),
        abnormal_count=sum(1 for i in report.indicators if i.is_abnormal),
        has_critical_values=report.has_critical_values,
        source=report.source,
        summary=report.summary,
    )


def to_detail(report: LabReport) -> LabReportDetailSchema:
    from src.models.schemas import IndicatorResultSchema

    summary = _to_summary(report)
    return LabReportDetailSchema(
        **summary.model_dump(),
        patient_age=report.patient_age,
        patient_gender=report.patient_gender,
        language=report.language,
        guardrail_passed=report.guardrail_passed,
        indicators=[
            IndicatorResultSchema(
                name=i.name,
                value=i.value,
                unit=i.unit,
                reference_low=i.reference_low,
                reference_high=i.reference_high,
                status=i.status,
                is_abnormal=i.is_abnormal,
                is_critical=i.is_critical,
                explanation=i.explanation,
                sources=list(i.sources or []),
            )
            for i in report.indicators
        ],
    )
