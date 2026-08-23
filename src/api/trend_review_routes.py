from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, get_db
from src.models.schemas import (
    DoctorTrendReviewDetailResponse,
    DoctorTrendReviewListResponse,
    DoctorTrendReviewSubmitRequest,
    TrendFilter,
    TrendReviewCreateRequest,
    TrendReviewPatientStateResponse,
    TrendReviewRequestResponse,
    TrendReviewSchema,
)
from src.services import trend_review_service as service
from src.services.patient_service import PatientNotFoundError

router = APIRouter(tags=["trend-review"])

_patient_only = require_roles(ROLE_PATIENT)
_doctor_only = require_roles(ROLE_DOCTOR)


def _doctor_id(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )
    return current_user.user_id


@router.get(
    "/patient/me/trends/{analyte_canonical}/review",
    response_model=TrendReviewPatientStateResponse,
)
async def patient_trend_review_state(
    analyte_canonical: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> TrendReviewPatientStateResponse:
    try:
        return service.get_patient_trend_review_state(
            db,
            username=current_user.username,
            analyte_canonical=analyte_canonical,
            trend_filter=filter,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/patient/me/trends/{analyte_canonical}/review-requests",
    response_model=TrendReviewRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_patient_trend_review_request(
    analyte_canonical: str,
    payload: TrendReviewCreateRequest,
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> TrendReviewRequestResponse:
    try:
        review = service.create_patient_trend_review_request(
            db,
            username=current_user.username,
            analyte_canonical=analyte_canonical,
            trend_filter=payload.trend_filter,
            llm_explanation=payload.llm_explanation,
        )
        return TrendReviewRequestResponse(review=review, created=True)
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.DuplicatePendingTrendReviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.TrendReviewNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/doctor/trend-reviews", response_model=DoctorTrendReviewListResponse)
async def doctor_trend_reviews(
    status_filter: str = Query(default="PENDING", alias="status"),
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorTrendReviewListResponse:
    _doctor_id(current_user)
    return service.list_doctor_trend_reviews(db, status=status_filter)


@router.get("/doctor/trend-reviews/{request_id}", response_model=DoctorTrendReviewDetailResponse)
async def doctor_trend_review_detail(
    request_id: int,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorTrendReviewDetailResponse:
    _doctor_id(current_user)
    try:
        return service.get_doctor_trend_review_detail(db, request_id)
    except service.TrendReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/doctor/trend-reviews/{request_id}/review", response_model=TrendReviewSchema)
async def submit_doctor_trend_review(
    request_id: int,
    payload: DoctorTrendReviewSubmitRequest,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> TrendReviewSchema:
    try:
        return service.submit_doctor_trend_review(
            db,
            request_id,
            doctor_id=_doctor_id(current_user),
            doctor_assessment=payload.doctor_assessment,
            doctor_comment=payload.doctor_comment,
        )
    except service.TrendReviewNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.TrendReviewAlreadyClosedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
