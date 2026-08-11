"""Lược đồ DB: tài khoản thật (users) + lịch sử xét nghiệm của bệnh nhân.

SQLite, tạo bảng qua create_all() (không dùng Alembic — quy mô hiện tại chưa
cần versioned migration). Seed vài tài khoản demo lúc khởi động nếu bảng đang
trống, để bản deploy vẫn dùng thử được sau khi disk bị reset.

Quan hệ:

    users (1) ──< (n) lab_reports (1) ──< (n) lab_report_indicators

- `users.role` phân biệt patient/doctor. Guest KHÔNG có bản ghi ở đây: phiên
  khách chỉ tồn tại trong token (xem `src/services/auth.py`), hết phiên là mất,
  đúng quyết định "Guest không cần persistent user".
- `lab_reports.patient_user_id` là dây nối duy nhất giữa một phiếu xét nghiệm
  và bệnh nhân sở hữu nó; truy vấn lịch sử theo khoảng ngày dùng
  `(patient_user_id, test_date)` nên có index kép cho cặp này.

LƯU Ý VẬN HÀNH: file SQLite nằm trên đĩa cục bộ của container và Railway chưa
gắn Volume — dữ liệu ở đây KHÔNG sống sót qua redeploy trên production. Đủ cho
nghiệm thu local và demo, không dùng cho dữ liệu bệnh nhân thật.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

from src.config import get_settings
from src.services.auth import hash_password

settings = get_settings()

_connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"
PERSISTED_ROLES = (ROLE_PATIENT, ROLE_DOCTOR)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # "patient" | "doctor"
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)

    reports = relationship(
        "LabReport",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="LabReport.test_date.desc()",
    )


class LabReport(Base):
    """Một lần phân tích phiếu xét nghiệm đã lưu cho một bệnh nhân."""

    __tablename__ = "lab_reports"

    id = Column(Integer, primary_key=True, autoincrement=True)
    patient_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Ngày ghi trên phiếu — đây là mốc dùng để lọc lịch sử theo khoảng ngày,
    # không phải created_at (bệnh nhân có thể nhập lại phiếu cũ).
    test_date = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow, index=True)

    patient_age = Column(Integer, nullable=False)
    patient_gender = Column(String, nullable=False)
    language = Column(String, nullable=False, default="vi")

    has_critical_values = Column(Boolean, nullable=False, default=False)
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    summary = Column(Text, nullable=False, default="")
    source = Column(String, nullable=False, default="manual")  # "manual" | "ocr"

    patient = relationship("User", back_populates="reports")
    indicators = relationship(
        "LabReportIndicator",
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="LabReportIndicator.id",
    )


class LabReportIndicator(Base):
    """Một dòng chỉ số trong phiếu đã lưu, kèm kết quả đối chiếu + giải thích."""

    __tablename__ = "lab_report_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    status = Column(String, nullable=False)
    is_abnormal = Column(Boolean, nullable=False, default=False)
    is_critical = Column(Boolean, nullable=False, default=False)
    explanation = Column(Text, nullable=False, default="")
    sources = Column(JSON, nullable=False, default=list)

    report = relationship("LabReport", back_populates="indicators")


# Truy vấn chủ đạo của màn lịch sử: "phiếu của bệnh nhân X trong khoảng ngày
# A..B". Index kép phục vụ đúng cặp cột đó.
Index("ix_lab_reports_patient_test_date", LabReport.patient_user_id, LabReport.test_date)


DEMO_USERS = [
    {"username": "benhnhan", "password": "benhnhan123", "role": ROLE_PATIENT},
    {"username": "bacsi", "password": "bacsi123", "role": ROLE_DOCTOR},
]


def seed_demo_users(db: Session) -> None:
    """Seed tài khoản demo nếu bảng users đang trống.

    Chỉ chạy khi bảng RỖNG: user đăng ký thật không bao giờ bị ghi đè.
    """
    if db.query(User).count() != 0:
        return
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
        # count()==0 không atomic giữa các process — nếu chạy nhiều worker,
        # process khác có thể đã seed xong giữa lúc mình check và commit.
        # Bỏ qua an toàn, không phải lỗi thật.
        db.rollback()


def _upgrade_sqlite_schema() -> None:
    """Thêm cột còn thiếu vào file SQLite đã tồn tại từ trước.

    `create_all()` chỉ tạo bảng mới, không sửa bảng cũ — máy dev nào đang giữ
    `data/app.db` sinh trước V3 sẽ vỡ ngay câu SELECT đầu tiên vì thiếu
    `users.created_at`. Đây là bản vá tối thiểu thay cho Alembic; nếu số lần vá
    kiểu này nhiều thêm thì đã đến lúc đưa migration thật vào.
    """
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(users)")}
        # Bảng chưa tồn tại -> PRAGMA trả rỗng, để create_all() lo.
        if columns and "created_at" not in columns:
            conn.exec_driver_sql("ALTER TABLE users ADD COLUMN created_at DATETIME")
            conn.exec_driver_sql(
                "UPDATE users SET created_at = ? WHERE created_at IS NULL",
                (_utcnow().isoformat(sep=" "),),
            )


def init_db() -> None:
    _upgrade_sqlite_schema()
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_demo_users(db)


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


__all__ = [
    "Base",
    "LabReport",
    "LabReportIndicator",
    "PERSISTED_ROLES",
    "ROLE_DOCTOR",
    "ROLE_PATIENT",
    "SessionLocal",
    "User",
    "engine",
    "get_db",
    "init_db",
    "seed_demo_users",
]

# Gọi ngay lúc import: đảm bảo bảng + seed tồn tại kể cả khi ASGI lifespan
# không được kích hoạt (vd. httpx.ASGITransport trong test không luôn chạy
# lifespan). init_db() idempotent, gọi lại từ lifespan của main.py vẫn an toàn.
init_db()
