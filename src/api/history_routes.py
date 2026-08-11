"""Lịch sử xét nghiệm của bệnh nhân.

Ranh giới quyền theo ma trận đã chốt:

- guest   — 403 ở mọi endpoint dưới đây (phiên khách không có lịch sử).
- patient — chỉ thấy phiếu của CHÍNH MÌNH; `patient_username` bị bỏ qua.
- doctor  — thấy phiếu của mọi bệnh nhân, lọc thêm được theo `patient_username`.

Quyền đọc dựa trên `user_id` trong token, không dựa vào tham số do client gửi.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, get_db
from src.models.schemas import LabReportDetailSchema, LabReportListResponse
from src.services import history_repository as repo

router = APIRouter(prefix="/history", tags=["history"])

_history_user = require_roles(ROLE_PATIENT, ROLE_DOCTOR)


@router.get("", response_model=LabReportListResponse)
async def list_history(
    from_date: date | None = Query(default=None, alias="from", description="Lọc từ ngày xét nghiệm (>=)"),
    to_date: date | None = Query(default=None, alias="to", description="Lọc đến ngày xét nghiệm (<=)"),
    patient_username: str | None = Query(
        default=None,
        description="Chỉ bác sĩ dùng được: xem lịch sử của một bệnh nhân cụ thể.",
    ),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(_history_user),
    db: Session = Depends(get_db),
) -> LabReportListResponse:
    if from_date and to_date and from_date > to_date:
        raise HTTPException(status_code=422, detail="Khoảng ngày không hợp lệ: 'from' phải trước 'to'.")

    if current_user.role == ROLE_PATIENT:
        # Bệnh nhân bị khoá cứng vào chính mình: tham số patient_username không
        # có tác dụng, kể cả khi gọi thẳng API.
        target_patient_id: int | None = current_user.user_id
    else:
        target_patient_id = None
        if patient_username:
            target_patient_id = repo.resolve_patient_id(db, patient_username)
            if target_patient_id is None:
                raise HTTPException(status_code=404, detail="Không tìm thấy bệnh nhân này.")

    total, items = repo.list_reports(
        db,
        patient_user_id=target_patient_id,
        from_date=from_date,
        to_date=to_date,
        limit=limit,
        offset=offset,
    )
    return LabReportListResponse(total=total, items=items)


@router.get("/{report_id}", response_model=LabReportDetailSchema)
async def get_history_detail(
    report_id: int,
    current_user: CurrentUser = Depends(_history_user),
    db: Session = Depends(get_db),
) -> LabReportDetailSchema:
    report = repo.get_report(db, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Không tìm thấy phiếu xét nghiệm.")

    if current_user.role == ROLE_PATIENT and report.patient_user_id != current_user.user_id:
        # Trả 404 chứ không 403: 403 gián tiếp xác nhận "phiếu này có tồn tại",
        # đủ để dò ID phiếu của người khác.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Không tìm thấy phiếu xét nghiệm.")

    return repo.to_detail(report)
