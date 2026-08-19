from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.models.db import ROLE_DOCTOR, get_db
from src.models.schemas import (
    DoctorCompleteReportResponse,
    DoctorQueueResponse,
    DoctorReportDetailResponse,
    FindingReviewRequest,
    FindingReviewResponse,
    QuestionAnswerRequest,
    ReportQuestionSchema,
)
from src.services import doctor_review_service as service

router = APIRouter(prefix="/doctor", tags=["doctor"])

_doctor_only = require_roles(ROLE_DOCTOR)


def _doctor_id(current_user: CurrentUser) -> int:
    if current_user.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập không hợp lệ.",
        )
    return current_user.user_id


@router.get("/queue", response_model=DoctorQueueResponse)
async def queue(
    tab: str = Query(default="pending"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=50, alias="pageSize"),
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorQueueResponse:
    _doctor_id(current_user)
    return service.list_queue(db, tab=tab, page=page, page_size=page_size)


@router.get("/reports/{report_id}", response_model=DoctorReportDetailResponse)
async def report_detail(
    report_id: int,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorReportDetailResponse:
    _doctor_id(current_user)
    try:
        return service.get_doctor_report_detail(db, report_id)
    except service.ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/findings/{finding_id}/review", response_model=FindingReviewResponse)
async def review_finding(
    finding_id: int,
    payload: FindingReviewRequest,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> FindingReviewResponse:
    try:
        return service.review_finding(
            db,
            finding_id,
            doctor_id=_doctor_id(current_user),
            outcome=payload.outcome,
            doctor_note=payload.doctor_note,
        )
    except service.FindingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.ReportAlreadyVerifiedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.DoctorReviewError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/questions/{question_id}/answer", response_model=ReportQuestionSchema)
async def answer_question(
    question_id: int,
    payload: QuestionAnswerRequest,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> ReportQuestionSchema:
    try:
        return service.answer_question(
            db,
            question_id,
            doctor_id=_doctor_id(current_user),
            answer_text=payload.answer_text,
        )
    except service.ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.ReportAlreadyVerifiedError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/reports/{report_id}/complete", response_model=DoctorCompleteReportResponse)
async def complete_report(
    report_id: int,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorCompleteReportResponse:
    try:
        report = service.complete_report(
            db,
            report_id,
            doctor_id=_doctor_id(current_user),
        )
        return DoctorCompleteReportResponse(
            report=service.complete_report_response(report)
        )
    except service.ReportNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.PendingFindingsError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
