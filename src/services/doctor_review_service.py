from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Literal

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from src.models.db import LabReport, ReportIndicator, ReportQuestion, ReviewFlag, User, _utcnow
from src.models.schemas import (
    DoctorFindingSchema,
    DoctorPatientSchema,
    DoctorQueueCountsSchema,
    DoctorQueueItemSchema,
    DoctorQueueResponse,
    DoctorReportDetailResponse,
    DoctorReportSchema,
    FindingReviewResponse,
    ReportProgressSchema,
    ReviewFlagSchema,
)

VERIFICATION_UNVERIFIED = "unverified"
VERIFICATION_PENDING = "pending_review"
VERIFICATION_VERIFIED = "verified"

OUTCOME_PENDING = "pending"
OUTCOME_AGREED = "agreed"
OUTCOME_CORRECTED = "corrected"
OUTCOME_SKIPPED = "skipped"
REVIEWED_OUTCOMES = {OUTCOME_AGREED, OUTCOME_CORRECTED, OUTCOME_SKIPPED}

FLAG_CRITICAL = "CRITICAL_VALUE"
FLAG_LOW_OCR = "LOW_OCR_CONFIDENCE"
FLAG_PATIENT_QUESTIONS = "PATIENT_HAS_QUESTIONS"

LOW_OCR_CONFIDENCE_THRESHOLD = 0.75
CORRECTION_MIN_LENGTH = 10

PRIORITY_WEIGHTS = {
    FLAG_CRITICAL: 50.0,
    FLAG_LOW_OCR: 15.0,
    FLAG_PATIENT_QUESTIONS: 10.0,
}
AGING_POINTS_PER_HOUR = 0.5
AGING_POINTS_MAX = 20.0


class DoctorReviewError(ValueError):
    pass


class ReportNotFoundError(DoctorReviewError):
    pass


class FindingNotFoundError(DoctorReviewError):
    pass


class ReportAlreadyVerifiedError(DoctorReviewError):
    pass


class PendingFindingsError(DoctorReviewError):
    pass


def _age_from_birthdate(birthdate: date | None, *, today: date | None = None) -> int | None:
    if birthdate is None:
        return None
    today = today or datetime.now(UTC).date()
    years = today.year - birthdate.year
    if (today.month, today.day) < (birthdate.month, birthdate.day):
        years -= 1
    return years


def _severity_level(report: LabReport) -> Literal["critical", "abnormal", "normal"]:
    if report.has_critical_values or any(indicator.is_critical for indicator in report.indicators):
        return "critical"
    if any(indicator.is_abnormal for indicator in report.indicators):
        return "abnormal"
    return "normal"


def _reference_range(indicator: ReportIndicator) -> str:
    low = "-" if indicator.reference_low is None else f"{indicator.reference_low:g}"
    high = "-" if indicator.reference_high is None else f"{indicator.reference_high:g}"
    return f"{low} - {high}"


def _finding_classification(
    indicator: ReportIndicator,
) -> Literal["critical", "abnormal", "normal"]:
    if indicator.is_critical:
        return "critical"
    if indicator.is_abnormal:
        return "abnormal"
    return "normal"


def _doctor_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.username


def _patient_name(report: LabReport) -> str:
    if report.patient is None:
        return f"Patient #{report.patient_id}"
    return report.patient.full_name or report.patient.username


def _flag_to_schema(flag: ReviewFlag) -> ReviewFlagSchema:
    return ReviewFlagSchema(
        code=flag.code,
        detail=flag.detail,
        severity=flag.severity,
        finding_id=flag.finding_id,
    )


def _finding_to_schema(indicator: ReportIndicator) -> DoctorFindingSchema:
    return DoctorFindingSchema(
        id=indicator.id,
        metric_code=indicator.analyte_canonical,
        metric_name=indicator.analyte_canonical or indicator.name,
        value=indicator.value,
        unit=indicator.unit,
        reference_range=_reference_range(indicator),
        classification=_finding_classification(indicator),
        ai_text=indicator.explanation,
        review_outcome=indicator.review_outcome or OUTCOME_PENDING,
        doctor_note=indicator.doctor_note,
        reviewed_by=_doctor_name(indicator.reviewed_by),
        reviewed_at=indicator.reviewed_at,
    )


def _report_to_schema(report: LabReport) -> DoctorReportSchema:
    return DoctorReportSchema(
        id=report.id,
        test_date=report.test_date,
        verification_status=report.verification_status or VERIFICATION_UNVERIFIED,
        verified_by=_doctor_name(report.verified_by),
        verified_at=report.verified_at,
        input_method="ocr" if report.ocr_source_filename else "manual",
        # The app intentionally does not persist uploaded patient images. Keep
        # this nullable so the UI can hide the image panel.
        original_image_url=None,
    )


def _question_to_schema(question: ReportQuestion):
    from src.services.history_repository import question_to_schema

    return question_to_schema(question)


def _sync_report_progress(report: LabReport) -> None:
    report.findings_total = len(report.indicators)
    report.findings_reviewed = sum(
        1
        for indicator in report.indicators
        if (indicator.review_outcome or OUTCOME_PENDING) in REVIEWED_OUTCOMES
    )


def _base_priority(flag_codes: set[str]) -> float:
    return sum(PRIORITY_WEIGHTS[code] for code in PRIORITY_WEIGHTS if code in flag_codes)


def _dynamic_priority(report: LabReport, *, now: datetime | None = None) -> float:
    flag_codes = {flag.code for flag in report.review_flags}
    score = _base_priority(flag_codes)
    queued_at = report.queued_at
    if queued_at is None:
        return score
    now = now or datetime.now(UTC)
    if queued_at.tzinfo is None:
        queued_at = queued_at.replace(tzinfo=UTC)
    waited_hours = max(0.0, (now - queued_at).total_seconds() / 3600)
    return score + min(AGING_POINTS_MAX, waited_hours * AGING_POINTS_PER_HOUR)


def refresh_review_flags(db: Session, report: LabReport) -> LabReport:
    """Regenerate queue flags for one report and sync report-level status."""

    existing = list(report.review_flags)
    for flag in existing:
        db.delete(flag)
    db.flush()

    _sync_report_progress(report)
    flags: list[ReviewFlag] = []

    for indicator in report.indicators:
        if indicator.is_critical:
            flags.append(
                ReviewFlag(
                    report_id=report.id,
                    finding_id=indicator.id,
                    code=FLAG_CRITICAL,
                    severity="high",
                    detail=f"{indicator.name} ở mức nguy kịch",
                )
            )

        if (
            indicator.ocr_confidence is not None
            and indicator.ocr_confidence < LOW_OCR_CONFIDENCE_THRESHOLD
        ):
            flags.append(
                ReviewFlag(
                    report_id=report.id,
                    finding_id=indicator.id,
                    code=FLAG_LOW_OCR,
                    severity="medium",
                    detail=(
                        f"Dòng OCR '{indicator.name}' có độ tin cậy "
                        f"{indicator.ocr_confidence:.2f}"
                    ),
                )
            )

    selected_questions = [question for question in report.questions if question.is_selected]
    if selected_questions:
        flags.append(
            ReviewFlag(
                report_id=report.id,
                finding_id=None,
                code=FLAG_PATIENT_QUESTIONS,
                severity="medium",
                detail=f"Bệnh nhân đã chọn {len(selected_questions)} câu hỏi",
            )
        )

    for flag in flags:
        db.add(flag)

    if report.verification_status != VERIFICATION_VERIFIED:
        if flags:
            report.verification_status = VERIFICATION_PENDING
            if report.queued_at is None:
                report.queued_at = _utcnow()
        else:
            report.verification_status = VERIFICATION_UNVERIFIED
            report.queued_at = None

    report.priority_score = _base_priority({flag.code for flag in flags})
    db.commit()
    db.refresh(report)
    return report


def refresh_review_flags_for_report_id(db: Session, report_id: int) -> None:
    report = get_report_for_doctor(db, report_id)
    refresh_review_flags(db, report)


def backfill_review_flags(db: Session) -> int:
    """Regenerate review flags for existing non-verified reports.

    This is intentionally explicit and development/demo-scoped at the caller.
    It fixes reports created before the doctor verification workflow existed,
    without changing reports already completed by a doctor.
    """

    reports = (
        db.execute(
            select(LabReport)
            .where(LabReport.verification_status != VERIFICATION_VERIFIED)
            .options(
                selectinload(LabReport.indicators),
                selectinload(LabReport.questions),
                selectinload(LabReport.review_flags),
            )
        )
        .scalars()
        .all()
    )
    changed = 0
    for report in reports:
        previous_status = report.verification_status
        previous_flag_codes = sorted(flag.code for flag in report.review_flags)
        refresh_review_flags(db, report)
        current_flag_codes = sorted(flag.code for flag in report.review_flags)
        if previous_status != report.verification_status or previous_flag_codes != current_flag_codes:
            changed += 1
    return changed


def get_report_for_doctor(db: Session, report_id: int) -> LabReport:
    report = (
        db.execute(
            select(LabReport)
            .where(LabReport.id == report_id)
            .options(
                selectinload(LabReport.patient),
                selectinload(LabReport.verified_by),
                selectinload(LabReport.indicators).selectinload(ReportIndicator.reviewed_by),
                selectinload(LabReport.review_flags),
                selectinload(LabReport.questions).selectinload(ReportQuestion.answered_by),
            )
        )
        .scalar_one_or_none()
    )
    if report is None:
        raise ReportNotFoundError("Không tìm thấy phiếu xét nghiệm.")
    return report


def _reports_for_counts(db: Session) -> list[LabReport]:
    return (
        db.execute(
            select(LabReport).options(
                selectinload(LabReport.review_flags),
            )
        )
        .scalars()
        .all()
    )


def _counts(reports: list[LabReport]) -> DoctorQueueCountsSchema:
    pending_reports = [
        report for report in reports if report.verification_status == VERIFICATION_PENDING
    ]
    return DoctorQueueCountsSchema(
        critical=sum(
            1
            for report in pending_reports
            if any(flag.code == FLAG_CRITICAL for flag in report.review_flags)
        ),
        ocr=sum(
            1
            for report in pending_reports
            if any(flag.code == FLAG_LOW_OCR for flag in report.review_flags)
        ),
        questions=sum(
            1
            for report in pending_reports
            if any(flag.code == FLAG_PATIENT_QUESTIONS for flag in report.review_flags)
        ),
        pending=len(pending_reports),
        verified=sum(1 for report in reports if report.verification_status == VERIFICATION_VERIFIED),
    )


def list_queue(
    db: Session,
    *,
    tab: str = "pending",
    page: int = 1,
    page_size: int = 20,
) -> DoctorQueueResponse:
    page = max(1, page)
    page_size = min(max(1, page_size), 50)

    reports = (
        db.execute(
            select(LabReport).options(
                selectinload(LabReport.patient),
                selectinload(LabReport.indicators),
                selectinload(LabReport.review_flags),
            )
        )
        .scalars()
        .all()
    )
    counts = _counts(reports)

    if tab == "verified":
        filtered = [
            report
            for report in reports
            if report.verification_status == VERIFICATION_VERIFIED
        ]
        filtered.sort(key=lambda report: (report.verified_at or report.created_at), reverse=True)
    else:
        filtered = [
            report
            for report in reports
            if report.verification_status == VERIFICATION_PENDING
        ]
        if tab == "critical":
            filtered = [
                report
                for report in filtered
                if any(flag.code == FLAG_CRITICAL for flag in report.review_flags)
            ]
        elif tab == "ocr":
            filtered = [
                report
                for report in filtered
                if any(flag.code == FLAG_LOW_OCR for flag in report.review_flags)
            ]
        elif tab == "questions":
            filtered = [
                report
                for report in filtered
                if any(flag.code == FLAG_PATIENT_QUESTIONS for flag in report.review_flags)
            ]

        filtered.sort(
            key=lambda report: (
                -_dynamic_priority(report),
                report.queued_at or report.created_at,
                report.id,
            )
        )

    total = len(filtered)
    start = (page - 1) * page_size
    page_items = filtered[start : start + page_size]

    return DoctorQueueResponse(
        items=[
            DoctorQueueItemSchema(
                report_id=report.id,
                patient_name=_patient_name(report),
                patient_id=report.patient_id,
                test_date=report.test_date,
                severity_level=_severity_level(report),
                flags=[_flag_to_schema(flag) for flag in report.review_flags],
                findings_reviewed=report.findings_reviewed,
                findings_total=report.findings_total or len(report.indicators),
                queued_at=report.queued_at,
            )
            for report in page_items
        ],
        counts=counts,
        page=page,
        page_size=page_size,
        total=total,
    )


def get_doctor_report_detail(db: Session, report_id: int) -> DoctorReportDetailResponse:
    report = get_report_for_doctor(db, report_id)
    _sync_report_progress(report)
    db.commit()
    db.refresh(report)

    flags_by_finding = {flag.finding_id for flag in report.review_flags if flag.finding_id is not None}
    findings = sorted(
        report.indicators,
        key=lambda indicator: (
            indicator.id not in flags_by_finding,
            indicator.id,
        ),
    )
    selected_questions = sorted(
        [question for question in report.questions if question.is_selected or question.answer_text],
        key=lambda question: (question.display_order, question.id),
    )

    return DoctorReportDetailResponse(
        report=_report_to_schema(report),
        patient=DoctorPatientSchema(
            id=report.patient_id,
            name=_patient_name(report),
            age=report.patient_age_at_test or _age_from_birthdate(
                report.patient.date_of_birth if report.patient is not None else None
            ),
            gender=report.patient_gender_at_test or (report.patient.sex if report.patient else None),
        ),
        flags=[_flag_to_schema(flag) for flag in report.review_flags],
        findings=[_finding_to_schema(indicator) for indicator in findings],
        questions=[_question_to_schema(question) for question in selected_questions],
    )


def review_finding(
    db: Session,
    finding_id: int,
    *,
    doctor_id: int,
    outcome: str,
    doctor_note: str | None = None,
) -> FindingReviewResponse:
    finding = (
        db.execute(
            select(ReportIndicator)
            .where(ReportIndicator.id == finding_id)
            .options(
                selectinload(ReportIndicator.report).selectinload(LabReport.indicators),
                selectinload(ReportIndicator.reviewed_by),
            )
        )
        .scalar_one_or_none()
    )
    if finding is None:
        raise FindingNotFoundError("Không tìm thấy luận điểm.")

    report = finding.report
    if report.verification_status == VERIFICATION_VERIFIED:
        raise ReportAlreadyVerifiedError("Phiếu đã được kiểm chứng và chỉ đọc.")

    if outcome not in REVIEWED_OUTCOMES:
        raise DoctorReviewError("Kết cục kiểm chứng không hợp lệ.")

    normalized_note = doctor_note.strip() if doctor_note else None
    if outcome == OUTCOME_CORRECTED and (
        normalized_note is None or len(normalized_note) < CORRECTION_MIN_LENGTH
    ):
        raise DoctorReviewError("Nội dung đính chính cần tối thiểu 10 ký tự.")

    finding.review_outcome = outcome
    finding.doctor_note = normalized_note if outcome == OUTCOME_CORRECTED else None
    if not finding.ai_text_snapshot:
        finding.ai_text_snapshot = finding.explanation
    finding.reviewed_by_doctor_id = doctor_id
    finding.reviewed_at = _utcnow()
    _sync_report_progress(report)

    db.commit()
    db.refresh(finding)
    db.refresh(report)

    return FindingReviewResponse(
        finding=_finding_to_schema(finding),
        report_progress=ReportProgressSchema(
            reviewed=report.findings_reviewed,
            total=report.findings_total,
        ),
    )


def complete_report(db: Session, report_id: int, *, doctor_id: int) -> LabReport:
    report = get_report_for_doctor(db, report_id)
    _sync_report_progress(report)
    if report.findings_reviewed < report.findings_total:
        raise PendingFindingsError("Còn luận điểm chưa xử lý.")

    report.verification_status = VERIFICATION_VERIFIED
    report.verified_by_doctor_id = doctor_id
    report.verified_at = _utcnow()
    db.commit()
    db.refresh(report)
    return report


def complete_report_response(report: LabReport) -> DoctorReportSchema:
    return _report_to_schema(report)


def answer_question(
    db: Session,
    question_id: int,
    *,
    doctor_id: int,
    answer_text: str,
):
    question = (
        db.execute(
            select(ReportQuestion)
            .where(ReportQuestion.id == question_id)
            .options(
                selectinload(ReportQuestion.report),
                selectinload(ReportQuestion.answered_by),
            )
        )
        .scalar_one_or_none()
    )
    if question is None:
        raise ReportNotFoundError("Không tìm thấy câu hỏi.")
    if question.report.verification_status == VERIFICATION_VERIFIED:
        raise ReportAlreadyVerifiedError("Phiếu đã được kiểm chứng và chỉ đọc.")

    question.answer_text = answer_text.strip()
    question.answered_by_doctor_id = doctor_id
    question.answered_at = _utcnow()
    question.status = "answered"
    db.commit()
    db.refresh(question)
    return _question_to_schema(question)


def newly_verified_count(db: Session, *, patient_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(LabReport)
            .where(
                LabReport.patient_id == patient_id,
                LabReport.verification_status == VERIFICATION_VERIFIED,
            )
        )
        or 0
    )
