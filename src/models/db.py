"""DB cho auth + lịch sử xét nghiệm bệnh nhân.

SQLite, tạo bảng qua create_all() (không dùng Alembic — quy mô project
này chưa cần versioned migration). Seed vài tài khoản demo lúc khởi động
nếu bảng users đang trống, để hoạt động ổn định kể cả khi disk trên
Render bị reset (free tier không có persistent disk).

users (1) --- (N) lab_reports (1) --- (N) report_indicators
                              (1) --- (N) report_critical_alerts

Guest (request không có JWT hợp lệ) không có row ở bất kỳ bảng nào —
mọi bảng lịch sử đều bắt buộc patient_id NOT NULL trỏ vào users.id thật,
nên guest tự động không lưu được gì mà không cần logic riêng.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.types import JSON

from src.config import get_settings
from src.services.auth import hash_password

settings = get_settings()

_is_sqlite = settings.database_url.startswith("sqlite")
_connect_args = {"check_same_thread": False} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

if _is_sqlite:
    # SQLite bỏ qua ON DELETE CASCADE trừ khi bật pragma này cho từng
    # connection — không bật thì các FK cascade khai báo ở dưới vô tác dụng.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "patient" | "doctor"


class LabReport(Base):
    """Một phiếu xét nghiệm đã phân tích, gắn với đúng 1 patient."""

    __tablename__ = "lab_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    test_date = Column(Date, nullable=False, index=True)
    # Snapshot tuổi/giới tính lúc xét nghiệm — users không lưu tuổi cố định
    # và tuổi/giới tính khai báo có thể khác nhau giữa các lần xét nghiệm.
    patient_age_at_test = Column(Integer, nullable=True)
    patient_gender_at_test = Column(String, nullable=True)
    language = Column(String, nullable=False, default="vi")
    summary = Column(Text, nullable=False, default="")
    has_critical_values = Column(Boolean, nullable=False, default=False)
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    disclaimer = Column(Text, nullable=False, default="")
    questions_for_doctor = Column(JSON, nullable=False, default=list)
    out_of_scope_indicators = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    indicators = relationship(
        "ReportIndicator", back_populates="report", cascade="all, delete-orphan"
    )
    critical_alerts = relationship(
        "ReportCriticalAlert", back_populates="report", cascade="all, delete-orphan"
    )


class ReportIndicator(Base):
    """Một chỉ số trong 1 phiếu — snapshot kết quả phân tích tại thời điểm lưu."""

    __tablename__ = "report_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="unknown")
    is_abnormal = Column(Boolean, nullable=False, default=False)
    is_critical = Column(Boolean, nullable=False, default=False)
    explanation = Column(Text, nullable=False, default="")
    sources = Column(JSON, nullable=False, default=list)

    report = relationship("LabReport", back_populates="indicators")


class ReportCriticalAlert(Base):
    """Cảnh báo khẩn của 1 phiếu (0..N — thường rất ít)."""

    __tablename__ = "report_critical_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    indicator_name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")
    message = Column(Text, nullable=False, default="")

    report = relationship("LabReport", back_populates="critical_alerts")


DEMO_USERS = [
    {"username": "benhnhan", "password": "benhnhan123", "role": "patient"},
    {"username": "bacsi", "password": "bacsi123", "role": "doctor"},
]


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        if db.query(User).count() == 0:
            for u in DEMO_USERS:
                db.add(
                    User(
                        username=u["username"],
                        password_hash=hash_password(u["password"]),
                        role=u["role"],
                    )
                )
            try:
                db.commit()
            except IntegrityError:
                # count()==0 không atomic giữa các process — nếu chạy nhiều
                # worker, process khác có thể đã seed xong giữa lúc mình
                # check và commit. Bỏ qua an toàn, không phải lỗi thật.
                db.rollback()


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Gọi ngay lúc import: đảm bảo bảng + seed tồn tại kể cả khi ASGI lifespan
# không được kích hoạt (vd. httpx.ASGITransport trong test không luôn chạy
# lifespan). init_db() idempotent (kiểm tra count()==0), gọi lại từ
# main.py's lifespan vẫn an toàn.
init_db()
