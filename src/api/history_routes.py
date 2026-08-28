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
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, LabReport, get_db
from src.models.schemas import (
    DoctorNoteCreateRequest,
    DoctorNoteSchema,
    LabReportDetailSchema,
    LabReportListResponse,
    QuestionAnswerRequest,
    QuestionSelectionRequest,
    ReportQuestionSchema,
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

# Hai chức năng dưới đây bất đối xứng theo role một cách có chủ đích: bệnh nhân
# tick chọn câu hỏi, bác sĩ ghi chú và trả lời. Authentication không hàm ý quyền.
_patient_only = require_roles(ROLE_PATIENT)
_doctor_only = require_roles(ROLE_DOCTOR)


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
        description=("Chỉ doctor dùng được: xem lịch sử của một patient cụ thể."),
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
    if from_date is not None and to_date is not None and from_date > to_date:
        raise HTTPException(
            status_code=422,
            detail=("Khoảng ngày không hợp lệ: 'from' phải trước hoặc bằng 'to'."),
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

    if current_user.role == ROLE_PATIENT and report.patient_id != current_user.user_id:
        # Không trả 403 vì 403 xác nhận report ID của người khác tồn tại.
        #
        # Trả 404 giúp tránh information disclosure qua ID enumeration.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy phiếu xét nghiệm.",
        )

    return repo.to_detail(report)


def _load_report_for(
    db: Session,
    report_id: int,
    current_user: CurrentUser,
) -> LabReport:
    """Lấy phiếu, áp đúng scope theo role.

    Dùng chung cho mọi endpoint con của một phiếu (câu hỏi, ghi chú, đánh dấu
    đã xem) để không endpoint nào tự nghĩ ra luật quyền riêng.

    Bệnh nhân chạm vào phiếu của người khác nhận 404 chứ không 403, giống
    endpoint detail: 403 sẽ gián tiếp xác nhận phiếu đó tồn tại, đủ để dò id
    phiếu của bệnh nhân khác.
    """

    report = repo.get_report(db, report_id)

    not_found = HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="Không tìm thấy phiếu xét nghiệm.",
    )

    if report is None:
        raise not_found

    if current_user.role == ROLE_PATIENT and report.patient_id != current_user.user_id:
        raise not_found

    return report


@router.post(
    "/{report_id}/questions/selection",
    response_model=list[ReportQuestionSchema],
)
async def select_report_questions(
    report_id: int,
    payload: QuestionSelectionRequest,
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> list[ReportQuestionSchema]:
    """Bệnh nhân chốt những câu mình muốn mang đi khám.

    Chỉ bệnh nhân sở hữu phiếu gọi được. Bác sĩ không tick hộ: danh sách này thể
    hiện bệnh nhân thật sự quan tâm điều gì, bác sĩ tick hộ thì mất đúng thông
    tin đó.
    """

    report = _load_report_for(db, report_id, current_user)

    questions = repo.select_questions(
        db,
        report,
        payload.question_ids,
    )

    return [repo.question_to_schema(question) for question in questions]


@router.post(
    "/{report_id}/questions/{question_id}/answer",
    response_model=ReportQuestionSchema,
)
async def answer_report_question(
    report_id: int,
    question_id: int,
    payload: QuestionAnswerRequest,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> ReportQuestionSchema:
    """Bác sĩ trả lời một câu hỏi của phiếu.

    Nội dung trả lời do người viết nên không đi qua guardrail. Frontend phải
    hiển thị nó kèm tên bác sĩ, tách khỏi phần do hệ thống sinh.
    """

    report = _load_report_for(db, report_id, current_user)

    question = repo.answer_question(
        db,
        report,
        question_id,
        doctor_id=current_user.user_id,
        answer_text=payload.answer_text,
    )

    if question is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Không tìm thấy câu hỏi trong phiếu này.",
        )

    return repo.question_to_schema(question)


@router.post(
    "/{report_id}/notes",
    response_model=DoctorNoteSchema,
    status_code=status.HTTP_201_CREATED,
)
async def create_doctor_note(
    report_id: int,
    payload: DoctorNoteCreateRequest,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> DoctorNoteSchema:
    """Bác sĩ ghi nhận xét lên một phiếu.

    Chỉ role doctor ghi được; bệnh nhân đọc được nhưng không viết được, vì giá
    trị của ghi chú nằm ở chỗ nó do người có thẩm quyền y khoa viết.

    Mỗi lần ghi tạo một bản ghi mới. Không có endpoint sửa hay xoá ghi chú.

    Phiếu được ghi chú cũng được coi là đã xem, nên không cần bấm thêm nút đánh
    dấu.
    """

    report = _load_report_for(db, report_id, current_user)

    note = repo.add_doctor_note(
        db,
        report,
        doctor_id=current_user.user_id,
        note_text=payload.note_text,
        target_type=payload.target_type,
        target_id=payload.target_id,
    )

    return repo.note_to_schema(note)


@router.post(
    "/{report_id}/review",
    response_model=LabReportDetailSchema,
)
async def mark_report_reviewed(
    report_id: int,
    current_user: CurrentUser = Depends(_doctor_only),
    db: Session = Depends(get_db),
) -> LabReportDetailSchema:
    """Bác sĩ đánh dấu đã xem phiếu, không kèm ghi chú.

    Hành động chủ động, không tự động theo lượt mở trang: bác sĩ lướt qua hoặc
    click nhầm mà hệ thống tự đánh dấu sẽ khiến bệnh nhân nhận tín hiệu sai rằng
    phiếu đã được xem kỹ.

    Idempotent — bấm nhiều lần không sinh thêm dòng.
    """

    report = _load_report_for(db, report_id, current_user)

    repo.mark_report_reviewed(
        db,
        report,
        doctor_id=current_user.user_id,
    )

    return repo.to_detail(repo.get_report(db, report_id))
