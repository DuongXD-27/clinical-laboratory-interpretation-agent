from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, get_current_user
from src.models.db import get_db
from src.models.schemas import (
    LabReportDetailSchema,
    PatientDashboardSchema,
    PatientLabReportListResponse,
    PatientProfileSchema,
    PatientProfileUpdateRequest,
)
from src.services.lab_history_service import (
    ReportNotFoundError,
    delete_report,
    get_dashboard_summary,
    get_report_detail,
    list_reports,
)
from src.services.patient_service import (
    PatientNotFoundError,
    PatientServiceError,
    get_patient_by_username,
    update_patient_profile,
)

router = APIRouter(prefix="/patient/me", tags=["patient"])


def _require_patient(current_user: CurrentUser) -> None:
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ bệnh nhân được truy cập dữ liệu này.")


def _profile_response(patient) -> PatientProfileSchema:
    return PatientProfileSchema(
        patient_id=patient.id,
        username=patient.username,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        sex=patient.sex,
        email=patient.email,
        created_at=patient.created_at,
        updated_at=patient.updated_at,
    )


@router.get("/profile", response_model=PatientProfileSchema)
async def get_profile(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientProfileSchema:
    _require_patient(current_user)
    try:
        return _profile_response(get_patient_by_username(db, current_user.username))
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.patch("/profile", response_model=PatientProfileSchema)
async def patch_profile(
    request: PatientProfileUpdateRequest,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientProfileSchema:
    _require_patient(current_user)
    try:
        return _profile_response(
            update_patient_profile(db, username=current_user.username, payload=request)
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except PatientServiceError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/dashboard", response_model=PatientDashboardSchema)
async def dashboard(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientDashboardSchema:
    _require_patient(current_user)
    try:
        return PatientDashboardSchema(**get_dashboard_summary(db, username=current_user.username))
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/lab-reports", response_model=PatientLabReportListResponse)
async def lab_reports(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PatientLabReportListResponse:
    _require_patient(current_user)
    try:
        return PatientLabReportListResponse(reports=list_reports(db, username=current_user.username))
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/lab-reports/{report_id}", response_model=LabReportDetailSchema)
async def lab_report_detail(
    report_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> LabReportDetailSchema:
    _require_patient(current_user)
    try:
        report = get_report_detail(db, username=current_user.username, report_id=report_id)
    except (PatientNotFoundError, ReportNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    detail = LabReportDetailSchema.model_validate(report)
    detail.result_count = len(report.indicators)
    return detail


@router.delete("/lab-reports/{report_id}", status_code=204)
async def delete_lab_report(
    report_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    _require_patient(current_user)
    try:
        delete_report(db, username=current_user.username, report_id=report_id)
    except (PatientNotFoundError, ReportNotFoundError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
