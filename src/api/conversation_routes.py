"""Quan ly hoi thoai: mo moi, liet ke, doc lai.

## Ranh gioi quyen

Chi `patient`. Khach 403 kem loi moi dang ky -- giong `/history`, va vi cung mot
ly do: hoi thoai la du lieu duoc luu, ma hop dong cua che do khach la khong luu
gi. Bac si va admin cung 403: ho khong co hoi thoai cua rieng minh o V1, va mo
cua cho ho bay gio la them mot o trong ma tran quyen ma khong ai dung.

## 404 chu khong phai 403 khi khong phai chu

Doc hoi thoai cua nguoi khac tra 404. 403 se xac nhan rang id do ton tai, du de
do ra hoi thoai cua benh nhan khac bang cach thu id. Day la quy tac da ap cho
`/history/{report_id}` va giu nguyen o day.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from src.api.deps import CurrentUser, require_roles
from src.models.conversation_schemas import (
    ConversationCreateRequest,
    ConversationDetailResponse,
    ConversationListResponse,
    ConversationMessageSchema,
    ConversationSummarySchema,
)
from src.models.db import ROLE_PATIENT, Conversation, get_db
from src.services import conversation_repository as repo

router = APIRouter(prefix="/conversations", tags=["conversations"])

_patient_only = require_roles(ROLE_PATIENT)

_NOT_FOUND = "Không tìm thấy cuộc trò chuyện."


def _patient_id(current_user: CurrentUser) -> int:
    """Chu so huu, lay tu JWT chu khong tu than request.

    `require_roles(ROLE_PATIENT)` da chan khach, nen den day `user_id` phai la
    int. Van kiem tra: mot token cu ky truoc V3 khong co claim `uid`, va doan do
    khong duoc phep bien thanh `patient_id=None` roi ghi bay dau do.
    """

    user_id = current_user.user_id
    if not isinstance(user_id, int):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Phiên đăng nhập đã cũ, vui lòng đăng nhập lại.",
        )
    return user_id


def resolve_conversation(
    db: Session,
    *,
    current_user: CurrentUser,
    conversation_id: int | None,
) -> Conversation | None:
    """Giai ra hoi thoai cho mot luot noi chuyen. Dung chung boi ca hai route chat.

    Ba nhanh, va su khac nhau giua chung la co chu y:

    - Khong phai benh nhan -> `None`. Khach van chat duoc binh thuong, chi la
      khong co gi duoc luu. Khong nem 403 o day: `/orchestrator/message` van
      phuc vu khach, khac voi `/conversations`.
    - Co `conversation_id` -> phai dung chu, khong thi 404.
    - Khong co `conversation_id` -> hoi thoai gan nhat, tao neu chua co. Giu
      tuong thich cho ban frontend da deploy.
    """

    if current_user.role != ROLE_PATIENT or not isinstance(current_user.user_id, int):
        return None

    if conversation_id is None:
        return repo.get_or_create_latest(db, patient_id=current_user.user_id)

    conversation = repo.get_conversation(
        db,
        conversation_id=conversation_id,
        patient_id=current_user.user_id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return conversation


@router.post("", response_model=ConversationSummarySchema, status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: ConversationCreateRequest | None = None,
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> ConversationSummarySchema:
    """New Chat: mot hang moi, context rong theo cau truc.

    Khong co buoc "xoa context cu" nao o day, va do la diem quan trong nhat cua
    ca tinh nang. Context nam tren hang hoi thoai, nen hang moi khong the mang
    theo `current_analyte` cua hoi thoai truoc. Khac han voi mot ham reset ma ai
    do co the quen goi.
    """

    conversation = repo.create_conversation(
        db,
        patient_id=_patient_id(current_user),
        title=payload.title if payload else None,
    )
    return ConversationSummarySchema.model_validate(conversation)


@router.get("", response_model=ConversationListResponse)
async def list_conversations(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> ConversationListResponse:
    rows, total = repo.list_conversations(
        db,
        patient_id=_patient_id(current_user),
        limit=limit,
        offset=offset,
    )
    return ConversationListResponse(
        items=[ConversationSummarySchema.model_validate(row) for row in rows],
        total=total,
    )


@router.get("/{conversation_id}", response_model=ConversationDetailResponse)
async def get_conversation(
    conversation_id: int,
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> ConversationDetailResponse:
    """Hoi thoai kem transcript -- day la thu lam cho tai lai trang khong mat gi."""

    patient_id = _patient_id(current_user)
    conversation = repo.get_conversation(
        db,
        conversation_id=conversation_id,
        patient_id=patient_id,
    )
    if conversation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)

    messages = repo.list_messages(db, conversation_id=conversation_id, patient_id=patient_id) or []
    return ConversationDetailResponse(
        conversation=ConversationSummarySchema.model_validate(conversation),
        messages=[ConversationMessageSchema.model_validate(m) for m in messages],
    )


@router.get("/{conversation_id}/messages", response_model=list[ConversationMessageSchema])
async def list_conversation_messages(
    conversation_id: int,
    current_user: CurrentUser = Depends(_patient_only),
    db: Session = Depends(get_db),
) -> list[ConversationMessageSchema]:
    """Chi transcript.

    Ton tai rieng canh `GET /conversations/{id}` du hai cai chong nhau mot phan:
    day la endpoint hep nhat de kiem quyen doc TIN NHAN, va CP-08 kiem dung no.
    Gop vao mot endpoint thi "A khong doc duoc tin nhan cua B" chi duoc chung
    minh gian tiep qua endpoint tra ca hai thu.

    `list_messages` tra `None` khi khong phai chu -- phan biet ro voi hoi thoai
    that su rong, tra `[]`. Gop hai truong hop lai thanh `[]` la bien mot loi
    phan quyen thanh mot man hinh trong, khong ai nhan ra.
    """

    messages = repo.list_messages(
        db,
        conversation_id=conversation_id,
        patient_id=_patient_id(current_user),
    )
    if messages is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=_NOT_FOUND)
    return [ConversationMessageSchema.model_validate(m) for m in messages]
