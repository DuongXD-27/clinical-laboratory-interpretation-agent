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
    SectionHeatmapResponse,
    SectionTrendsResponse,
    TrendAnalyteListResponse,
    TrendExplanationResponse,
    TrendFilter,
    TrendResponse,
)
from src.services import history_repository as repo
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
from src.services.section_trend_explanation_service import (
    SECTION_KEYS,
    explain_section_trend,
)
from src.services.trend_explanation_service import (
    TrendExplanationUnavailableError,
    explain_patient_trend,
)
from src.services.trend_service import (
    get_patient_section_heatmap,
    get_patient_section_trends,
    get_patient_trend,
    get_patient_trend_analytes,
)

router = APIRouter(prefix="/patient/me", tags=["patient"])


def _require_patient(current_user: CurrentUser) -> None:
    if current_user.role != "patient":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Chỉ bệnh nhân được truy cập dữ liệu này.")


def _profile_response(patient) -> PatientProfileSchema:
    raw_style = getattr(patient, "response_style", None)
    safe_style = raw_style if raw_style in {"concise", "simple", "detailed"} else "simple"
    return PatientProfileSchema(
        patient_id=patient.id,
        username=patient.username,
        full_name=patient.full_name,
        date_of_birth=patient.date_of_birth,
        sex=patient.sex,
        email=patient.email,
        response_style=safe_style,
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
        return _profile_response(update_patient_profile(db, username=current_user.username, payload=request))
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


@router.get("/trends/analytes", response_model=TrendAnalyteListResponse)
async def trend_analytes(
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendAnalyteListResponse:
    _require_patient(current_user)
    try:
        return TrendAnalyteListResponse(analytes=get_patient_trend_analytes(db, username=current_user.username))
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trends/sections/{section}/trends", response_model=SectionTrendsResponse)
async def section_trends(
    section: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectionTrendsResponse:
    if section not in SECTION_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Section không hợp lệ: {section}. Chọn từ: {', '.join(SECTION_KEYS)}",
        )
    _require_patient(current_user)
    try:
        return get_patient_section_trends(
            db,
            username=current_user.username,
            section=section,
            trend_filter=filter,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trends/sections/{section}/heatmap", response_model=SectionHeatmapResponse)
async def section_heatmap(
    section: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectionHeatmapResponse:
    if section not in SECTION_KEYS:
        raise HTTPException(
            status_code=400,
            detail=f"Section không hợp lệ: {section}. Chọn từ: {', '.join(SECTION_KEYS)}",
        )
    _require_patient(current_user)
    try:
        return get_patient_section_heatmap(
            db,
            username=current_user.username,
            section=section,
            trend_filter=filter,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trends/{analyte_canonical}", response_model=TrendResponse)
async def trend_data(
    analyte_canonical: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendResponse:
    _require_patient(current_user)
    try:
        return get_patient_trend(
            db,
            username=current_user.username,
            analyte_canonical=analyte_canonical,
            trend_filter=filter,
        )
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trends/{analyte_canonical}/explain", response_model=TrendExplanationResponse)
async def trend_explanation(
    analyte_canonical: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendExplanationResponse:
    _require_patient(current_user)
    try:
        return await explain_patient_trend(
            db,
            username=current_user.username,
            analyte_canonical=analyte_canonical,
            trend_filter=filter,
        )
    except TrendExplanationUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PatientNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/trends/sections/{section}/explain", response_model=TrendExplanationResponse)
async def section_trend_explanation(
    section: str,
    filter: TrendFilter = "latest5",
    current_user: CurrentUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TrendExplanationResponse:
    _require_patient(current_user)
    if section not in SECTION_KEYS:
        raise HTTPException(status_code=400, detail="Nhóm chức năng không hợp lệ.")
    try:
        return await explain_section_trend(
            db,
            username=current_user.username,
            section=section,
            trend_filter=filter,
        )
    except TrendExplanationUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
    # Dùng chung repo.to_detail() với /api/v1/history/{id} (ADR-010 CRIT-TREND-06)
    # thay vì model_validate thẳng từ ORM — chỗ đó là nơi duy nhất gán section cho
    # từng indicator; validate thẳng sẽ luôn để section=None.
    detail = repo.to_detail(report)
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
