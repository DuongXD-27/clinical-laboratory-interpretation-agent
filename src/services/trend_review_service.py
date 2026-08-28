from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from src.models.db import TrendReviewRequest, User, _utcnow
from src.models.schemas import (
    DoctorPatientSchema,
    DoctorTrendReviewDetailResponse,
    DoctorTrendReviewListResponse,
    DoctorTrendReviewSummary,
    TrendFilter,
    TrendResponse,
    TrendReviewAssessment,
    TrendReviewHistoryResponse,
    TrendReviewPatientStateResponse,
    TrendReviewSchema,
)
from src.services.patient_service import get_patient_by_username
from src.services.trend_service import get_patient_trend


class TrendReviewError(ValueError):
    pass


class TrendReviewNotFoundError(TrendReviewError):
    pass


class DuplicatePendingTrendReviewError(TrendReviewError):
    pass


class TrendReviewNotAllowedError(TrendReviewError):
    pass


class TrendReviewAlreadyClosedError(TrendReviewError):
    pass


def _doctor_name(user: User | None) -> str | None:
    if user is None:
        return None
    return user.full_name or user.username


def _patient_name(user: User | None, patient_id: int) -> str:
    if user is None:
        return f"Patient #{patient_id}"
    return user.full_name or user.username


def _age_from_birthdate(value, *, today=None) -> int | None:
    if value is None:
        return None
    today = today or datetime.now(UTC).date()
    years = today.year - value.year
    if (today.month, today.day) < (value.month, value.day):
        years -= 1
    return years


def trend_snapshot_hash(trend: TrendResponse) -> str:
    payload = trend.model_dump(mode="json")
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _schema(row: TrendReviewRequest) -> TrendReviewSchema:
    return TrendReviewSchema(
        id=row.id,
        patient_id=row.patient_id,
        analyte_canonical=row.analyte_canonical,
        display_name=row.display_name,
        canonical_unit=row.canonical_unit,
        trend_filter=row.trend_filter,
        trend_snapshot=TrendResponse.model_validate(row.trend_snapshot),
        trend_snapshot_hash=row.trend_snapshot_hash,
        llm_explanation_snapshot=row.llm_explanation_snapshot,
        status=row.status,
        requested_at=row.requested_at,
        reviewed_by_doctor_id=row.reviewed_by_doctor_id,
        reviewed_by_username=_doctor_name(row.reviewed_by),
        reviewed_at=row.reviewed_at,
        doctor_assessment=row.doctor_assessment,
        doctor_comment=row.doctor_comment,
    )


def _current_trend(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
) -> TrendResponse:
    trend = get_patient_trend(
        db,
        username=username,
        analyte_canonical=analyte_canonical,
        trend_filter=trend_filter,
    )
    if not trend.trend_available:
        raise TrendReviewNotAllowedError("Xu hướng này chưa đủ dữ liệu để gửi bác sĩ review.")
    return trend


def get_patient_trend_review_state(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
) -> TrendReviewPatientStateResponse:
    patient = get_patient_by_username(db, username)
    pending = (
        db.execute(
            select(TrendReviewRequest)
            .where(
                TrendReviewRequest.patient_id == patient.id,
                TrendReviewRequest.analyte_canonical == analyte_canonical,
                TrendReviewRequest.trend_filter == trend_filter,
                TrendReviewRequest.status == TrendReviewRequest.STATUS_PENDING,
            )
            .options(selectinload(TrendReviewRequest.reviewed_by))
            .order_by(TrendReviewRequest.requested_at.desc(), TrendReviewRequest.id.desc())
        )
        .scalars()
        .first()
    )
    reviewed_rows = (
        db.execute(
            select(TrendReviewRequest)
            .where(
                TrendReviewRequest.patient_id == patient.id,
                TrendReviewRequest.analyte_canonical == analyte_canonical,
                TrendReviewRequest.trend_filter == trend_filter,
                TrendReviewRequest.status == TrendReviewRequest.STATUS_REVIEWED,
            )
            .options(selectinload(TrendReviewRequest.reviewed_by))
            .order_by(TrendReviewRequest.reviewed_at.desc(), TrendReviewRequest.id.desc())
        )
        .scalars()
        .all()
    )

    current_hash: str | None = None
    reason: str | None = None
    try:
        current_hash = trend_snapshot_hash(
            _current_trend(
                db,
                username=username,
                analyte_canonical=analyte_canonical,
                trend_filter=trend_filter,
            )
        )
    except TrendReviewNotAllowedError:
        reason = "TREND_UNAVAILABLE"

    latest_current_review: TrendReviewRequest | None = None
    latest_historical_review: TrendReviewRequest | None = None
    for row in reviewed_rows:
        if current_hash is not None and row.trend_snapshot_hash == current_hash:
            if latest_current_review is None:
                latest_current_review = row
            continue
        if latest_historical_review is None:
            latest_historical_review = row

    if pending is not None:
        can_request = False
        reason = "PENDING_EXISTS"
    elif reason == "TREND_UNAVAILABLE":
        can_request = False
    elif latest_current_review is not None:
        can_request = False
        reason = "LATEST_REVIEW_STILL_CURRENT"
    else:
        can_request = True
        if latest_historical_review is not None:
            reason = "CURRENT_TREND_CHANGED"

    return TrendReviewPatientStateResponse(
        latest_review=_schema(latest_current_review) if latest_current_review is not None else None,
        latest_historical_review=_schema(latest_historical_review) if latest_historical_review is not None else None,
        pending_request=_schema(pending) if pending is not None else None,
        can_request_review=can_request,
        reason=reason,
        current_trend_hash=current_hash,
        history_count=len(reviewed_rows),
    )


def create_patient_trend_review_request(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
    llm_explanation: str,
) -> TrendReviewSchema:
    patient = get_patient_by_username(db, username)
    trend = _current_trend(
        db,
        username=username,
        analyte_canonical=analyte_canonical,
        trend_filter=trend_filter,
    )
    current_hash = trend_snapshot_hash(trend)
    state = get_patient_trend_review_state(
        db,
        username=username,
        analyte_canonical=analyte_canonical,
        trend_filter=trend_filter,
    )
    if state.pending_request is not None:
        raise DuplicatePendingTrendReviewError("Đã có yêu cầu review đang chờ cho chỉ số này.")
    if state.latest_review is not None and state.latest_review.trend_snapshot_hash == current_hash:
        raise TrendReviewNotAllowedError("Review mới nhất vẫn khớp dữ liệu xu hướng hiện tại.")

    row = TrendReviewRequest(
        patient_id=patient.id,
        analyte_canonical=trend.analyte_canonical,
        display_name=trend.display_name,
        canonical_unit=trend.canonical_unit,
        trend_filter=trend.filter,
        trend_snapshot=trend.model_dump(mode="json"),
        trend_snapshot_hash=current_hash,
        llm_explanation_snapshot=llm_explanation.strip(),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise DuplicatePendingTrendReviewError("Đã có yêu cầu review đang chờ cho chỉ số này.") from exc
    except Exception:
        db.rollback()
        raise
    db.refresh(row)
    return _schema(row)


def list_patient_trend_review_history(
    db: Session,
    *,
    username: str,
    analyte_canonical: str,
    trend_filter: TrendFilter,
) -> TrendReviewHistoryResponse:
    patient = get_patient_by_username(db, username)
    rows = (
        db.execute(
            select(TrendReviewRequest)
            .where(
                TrendReviewRequest.patient_id == patient.id,
                TrendReviewRequest.analyte_canonical == analyte_canonical,
                TrendReviewRequest.trend_filter == trend_filter,
                TrendReviewRequest.status == TrendReviewRequest.STATUS_REVIEWED,
            )
            .options(selectinload(TrendReviewRequest.reviewed_by))
            .order_by(TrendReviewRequest.reviewed_at.desc(), TrendReviewRequest.id.desc())
        )
        .scalars()
        .all()
    )
    return TrendReviewHistoryResponse(
        total=len(rows),
        items=[_schema(row) for row in rows],
    )


def list_doctor_trend_reviews(
    db: Session,
    *,
    status: str = TrendReviewRequest.STATUS_PENDING,
) -> DoctorTrendReviewListResponse:
    stmt = (
        select(TrendReviewRequest)
        .options(
            selectinload(TrendReviewRequest.patient),
            selectinload(TrendReviewRequest.reviewed_by),
        )
        .order_by(TrendReviewRequest.requested_at.desc(), TrendReviewRequest.id.desc())
    )
    if status != "all":
        stmt = stmt.where(TrendReviewRequest.status == status)
    rows = db.execute(stmt).scalars().all()
    return DoctorTrendReviewListResponse(
        total=len(rows),
        items=[
            DoctorTrendReviewSummary(
                id=row.id,
                patient_id=row.patient_id,
                patient_name=_patient_name(row.patient, row.patient_id),
                analyte_canonical=row.analyte_canonical,
                display_name=row.display_name,
                trend_filter=row.trend_filter,
                point_count=len((row.trend_snapshot or {}).get("points") or []),
                status=row.status,
                requested_at=row.requested_at,
                reviewed_at=row.reviewed_at,
                reviewed_by_username=_doctor_name(row.reviewed_by),
            )
            for row in rows
        ],
    )


def get_doctor_trend_review_detail(db: Session, request_id: int) -> DoctorTrendReviewDetailResponse:
    row = db.execute(
        select(TrendReviewRequest)
        .where(TrendReviewRequest.id == request_id)
        .options(
            selectinload(TrendReviewRequest.patient),
            selectinload(TrendReviewRequest.reviewed_by),
        )
    ).scalar_one_or_none()
    if row is None:
        raise TrendReviewNotFoundError("Không tìm thấy yêu cầu review xu hướng.")
    patient = row.patient
    return DoctorTrendReviewDetailResponse(
        review=_schema(row),
        patient=DoctorPatientSchema(
            id=row.patient_id,
            name=_patient_name(patient, row.patient_id),
            age=_age_from_birthdate(patient.date_of_birth if patient is not None else None),
            gender=patient.sex if patient is not None else None,
        ),
    )


def submit_doctor_trend_review(
    db: Session,
    request_id: int,
    *,
    doctor_id: int,
    doctor_assessment: TrendReviewAssessment,
    doctor_comment: str,
) -> TrendReviewSchema:
    row = db.execute(
        select(TrendReviewRequest)
        .where(TrendReviewRequest.id == request_id)
        .options(selectinload(TrendReviewRequest.reviewed_by))
    ).scalar_one_or_none()
    if row is None:
        raise TrendReviewNotFoundError("Không tìm thấy yêu cầu review xu hướng.")
    if row.status != TrendReviewRequest.STATUS_PENDING:
        raise TrendReviewAlreadyClosedError("Yêu cầu này đã được xử lý.")

    row.status = TrendReviewRequest.STATUS_REVIEWED
    row.reviewed_by_doctor_id = doctor_id
    row.reviewed_at = _utcnow()
    row.doctor_assessment = doctor_assessment
    row.doctor_comment = doctor_comment.strip()
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    refreshed = db.execute(
        select(TrendReviewRequest)
        .where(TrendReviewRequest.id == request_id)
        .options(selectinload(TrendReviewRequest.reviewed_by))
    ).scalar_one()
    return _schema(refreshed)
