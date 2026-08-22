from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from src.models.db import User
from src.models.schemas import PatientProfileUpdateRequest
from src.services.email_identity import InvalidEmailError, normalise_email


class PatientServiceError(ValueError):
    pass


class PatientNotFoundError(PatientServiceError):
    pass


def get_patient_by_username(db: Session, username: str) -> User:
    patient = db.query(User).filter(User.username == username, User.role == "patient").first()
    if patient is None:
        raise PatientNotFoundError("Không tìm thấy hồ sơ bệnh nhân.")
    return patient


def update_patient_profile(
    db: Session,
    *,
    username: str,
    payload: PatientProfileUpdateRequest,
) -> User:
    patient = get_patient_by_username(db, username)

    # Dùng chung `normalise_email` với đăng ký và đăng nhập. Trước đây chỗ này
    # chỉ kiểm `"@" in email` và không hạ chữ thường — nghĩa là `Duy@Gmail.com`
    # lưu nguyên, rồi đăng nhập bằng `duy@gmail.com` không ra, mà thông báo lại
    # là "sai mật khẩu".
    try:
        email = normalise_email(payload.email)
    except InvalidEmailError as exc:
        raise PatientServiceError(str(exc)) from None

    patient.full_name = payload.full_name.strip() if payload.full_name else None
    patient.date_of_birth = payload.date_of_birth
    patient.sex = payload.sex
    patient.email = email
    patient.updated_at = datetime.now(UTC)

    try:
        db.commit()
    except IntegrityError:
        # UNIQUE index quyết định, không phải câu SELECT kiểm tra trước — hai
        # bệnh nhân cùng lúc đặt một email thì cả hai đều qua được SELECT.
        db.rollback()
        raise PatientServiceError("Email này đã được dùng cho một tài khoản khác.") from None

    db.refresh(patient)
    return patient
