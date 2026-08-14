from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from src.models.db import User
from src.models.schemas import PatientProfileUpdateRequest


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

    email = payload.email.strip() if payload.email else None
    if email is not None and "@" not in email:
        raise PatientServiceError("Email chưa hợp lệ.")

    patient.full_name = payload.full_name.strip() if payload.full_name else None
    patient.date_of_birth = payload.date_of_birth
    patient.sex = payload.sex
    patient.email = email
    patient.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(patient)
    return patient
