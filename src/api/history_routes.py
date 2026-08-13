"""Lịch sử xét nghiệm của bệnh nhân.

Ranh giới quyền:

- guest   — 403 ở mọi history endpoint.
- patient — chỉ xem được report của chính mình.
- doctor  — xem được report của mọi patient, có thể lọc theo username.

Quyền đọc của patient luôn dựa trên user_id trong JWT, không dựa vào
patient_username do client gửi.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, get_db
from src.models.schemas import (
    LabReportDetailSchema,
    LabReportListResponse,
)
from src.services import history_repository as repo

router = APIRouter(
    prefix="/history",
    tags=["history"],
)

_history_user = require_roles(
    ROLE_PATIENT,
    ROLE_DOCTOR,
)


@router.get(
    "",
    response_model=LabReportListResponse,
)
async def list_history(
    from_date: date | None = Query(
        default=None,
        alias="from",
        description="Lọc từ ngày xét nghiệm (>=)",
    ),
    to_date: date | None = Query(
        default=None,
        alias="to",
        description="Lọc đến ngày xét nghiệm (<=)",
    ),
    patient_username: str | None = Query(
        default=None,
        description=(
            "Chỉ doctor dùng được: xem lịch sử của một patient cụ thể."
        ),
    ),
    limit: int = Query(
        default=50,
        ge=1,
        le=200,
    ),
    offset: int = Query(
        default=0,
        ge=0,
    ),
    current_user: CurrentUser = Depends(_history_user),
    db: Session = Depends(get_db),
) -> LabReportListResponse:
    if (
        from_date is not None
        and to_date is not None
        and from_date > to_date
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Khoảng ngày không hợp lệ: "
                "'from' phải trước hoặc bằng 'to'."
            ),
        )

    if current_user.role == ROLE_PATIENT:
        # Patient bị khóa cứng vào user_id trong token.
        #
        # patient_username nếu client cố tình gửi lên cũng bị bỏ qua.
        target_patient_id = current_user.user_id

        if target_patient_id is None:
            # Về lý thuyết deps.py đã chặn token patient thiếu uid.
            # Giữ defensive check để không vô tình query toàn bộ history.
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Phiên đăng nhập không hợp lệ.",
            )

    else:
        # Doctor mặc định xem toàn bộ patient history.
        target_patient_id = None

        if patient_username:
            target_patient_id = repo.resolve_patient_id(
                db,
                patient_username,
            )

            if target_patient_id is None:
                raise HTTPException(
                    status_code=404,
                    detail="Không tìm thấy bệnh nhân này.",
                )

    total, items = repo.list_reports(
        db,
        patient_id=target_patient_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )

    return LabReportListResponse(
        total=total,
        items=items,
    )


@router.get(
    "/{report_id}",
    response_model=LabReportDetailSchema,
)
async def get_history_detail(
    report_id: int,
    current_user: CurrentUser = Depends(_history_user),
    db: Session = Depends(get_db),
) -> LabReportDetailSchema:
    report = repo.get_report(
        db,
        report_id,
    )

    if report is None:
        raise HTTPException(
            status_code=404,
            detail="Không tìm thấy phiếu xét nghiệm.",
        )

    if (
        current_user.role == ROLE_PATIENT
        and report.patient_id != current_user.user_id
    ):
        # Không trả 403 vì 403 xác nhận report ID của người khác tồn tại.
        #
        # Trả 404 giúp tránh information disclosure qua ID enumeration.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiếu xét nghiệm.",
        )

    return repo.to_detail(report)
