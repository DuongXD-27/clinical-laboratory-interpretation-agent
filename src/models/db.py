"""DB cho authentication + lịch sử xét nghiệm bệnh nhân.

SQLite, tạo bảng qua create_all() (không dùng Alembic — quy mô project
hiện tại chưa cần versioned migration). Seed vài tài khoản demo lúc khởi
động nếu bảng users đang trống.

Quan hệ chính:

    users (1) --- (N) lab_reports
                        |
                        +--- (N) report_indicators --- (1) indicator_catalog
                        +--- (N) report_critical_alerts
                        +--- (N) report_questions
                        +--- (N) out_of_scope_log

Guest không có row trong users và không có row lịch sử. Mọi lab_report
persistent đều bắt buộc patient_id NOT NULL trỏ tới users.id thật.

doctor_notes dùng polymorphic association target_type/target_id để trỏ
tới indicator hoặc report_question. Vì target_id không phải FK thật,
tầng ứng dụng chịu trách nhiệm đảm bảo target tồn tại và dọn orphan note
nếu target bị xóa.

LƯU Ý VẬN HÀNH:
SQLite local phù hợp cho nghiệm thu/demo nhưng không nên dùng làm persistence
production nếu Railway không gắn persistent Volume. Trước khi có dữ liệu
người dùng thật cần chuyển sang PostgreSQL hoặc storage persistent tương đương.
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
    Index,
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

engine = create_engine(
    settings.database_url,
    connect_args=_connect_args,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
)


ROLE_PATIENT = "patient"
ROLE_DOCTOR = "doctor"
PERSISTED_ROLES = (ROLE_PATIENT, ROLE_DOCTOR)


def _utcnow() -> datetime:
    return datetime.now(UTC)


if _is_sqlite:

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _) -> None:
        """Bật enforcement Foreign Key cho từng SQLite connection."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


class Base(DeclarativeBase):
    pass


class User(Base):
    """Tài khoản persistent của patient hoặc doctor."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False, index=True)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
    )

    reports = relationship(
        "LabReport",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="LabReport.test_date.desc()",
    )


class LabReport(Base):
    """Một phiếu xét nghiệm đã phân tích, gắn với đúng một patient."""

    __tablename__ = "lab_reports"

    __table_args__ = (
        # Query lịch sử chủ đạo:
        # WHERE patient_id=:X AND test_date BETWEEN :A AND :B
        Index(
            "ix_lab_reports_patient_id_test_date",
            "patient_id",
            "test_date",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    patient_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Ngày ghi trên phiếu, không phải thời điểm upload/phân tích.
    test_date = Column(Date, nullable=False, index=True)

    # Snapshot thông tin bệnh nhân tại thời điểm xét nghiệm.
    patient_age_at_test = Column(Integer, nullable=True)
    patient_gender_at_test = Column(String, nullable=True)

    # Chỉ lưu tên file hiển thị từ OCR, không lưu ảnh gốc/path ảnh.
    ocr_source_filename = Column(String, nullable=True)

    language = Column(String, nullable=False, default="vi")
    summary = Column(Text, nullable=False, default="")
    has_critical_values = Column(Boolean, nullable=False, default=False)
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    disclaimer = Column(Text, nullable=False, default="")

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    # Bổ sung counterpart cho User.reports(back_populates="patient").
    patient = relationship(
        "User",
        back_populates="reports",
    )

    indicators = relationship(
        "ReportIndicator",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    critical_alerts = relationship(
        "ReportCriticalAlert",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    questions = relationship(
        "ReportQuestion",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    out_of_scope_entries = relationship(
        "OutOfScopeLog",
        back_populates="report",
        cascade="all, delete-orphan",
    )


_ABNORMAL_STATUSES = frozenset(
    {
        "low",
        "high",
        "critical_low",
        "critical_high",
    }
)

_CRITICAL_STATUSES = frozenset(
    {
        "critical_low",
        "critical_high",
    }
)


class ReportIndicator(Base):
    """Snapshot một chỉ số của một phiếu xét nghiệm."""

    __tablename__ = "report_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Nullable vì OCR/nhập tay có thể sinh tên chưa canonical hóa.
    indicator_catalog_id = Column(
        Integer,
        ForeignKey("indicator_catalog.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")

    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)

    # Nguồn sự thật duy nhất cho normal/abnormal/critical.
    status = Column(String, nullable=False, default="unknown")

    explanation = Column(Text, nullable=False, default="")
    sources = Column(JSON, nullable=False, default=list)

    # Metadata OCR בלבד; không lưu ảnh gốc.
    ocr_confidence = Column(Float, nullable=True)
    ocr_raw_text = Column(Text, nullable=True)

    report = relationship(
        "LabReport",
        back_populates="indicators",
    )

    catalog_entry = relationship(
        "IndicatorCatalog",
        back_populates="indicators",
    )

    questions = relationship(
        "ReportQuestion",
        back_populates="indicator",
        cascade="all, delete-orphan",
    )

    @property
    def is_abnormal(self) -> bool:
        """Derive từ status để tránh hai nguồn sự thật."""
        return self.status in _ABNORMAL_STATUSES

    @property
    def is_critical(self) -> bool:
        """Derive từ status để tránh hai nguồn sự thật."""
        return self.status in _CRITICAL_STATUSES


class ReportCriticalAlert(Base):
    """Cảnh báo giá trị nguy kịch của một report."""

    __tablename__ = "report_critical_alerts"

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    indicator_name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")
    message = Column(Text, nullable=False, default="")

    report = relationship(
        "LabReport",
        back_populates="critical_alerts",
    )


class IndicatorCatalog(Base):
    """Danh mục canonical của các chỉ số xét nghiệm.

    Cho phép nhiều alias như HbA1c / Hemoglobin A1c cùng resolve về một
    canonical indicator để theo dõi trend ổn định qua nhiều lần xét nghiệm.
    """

    __tablename__ = "indicator_catalog"

    id = Column(Integer, primary_key=True, autoincrement=True)

    canonical_name = Column(
        String,
        nullable=False,
        unique=True,
        index=True,
    )

    canonical_unit = Column(String, nullable=False)

    aliases = Column(
        JSON,
        nullable=False,
        default=list,
    )

    unit_conversions = Column(
        JSON,
        nullable=False,
        default=dict,
    )

    max_gap_days_for_trend = Column(Integer, nullable=True)

    indicators = relationship(
        "ReportIndicator",
        back_populates="catalog_entry",
    )


class ReportQuestion(Base):
    """Một câu hỏi gợi ý bệnh nhân hỏi bác sĩ."""

    __tablename__ = "report_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    indicator_id = Column(
        Integer,
        ForeignKey("report_indicators.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    question_text = Column(Text, nullable=False)

    # "critical" | "abnormal"
    priority = Column(String, nullable=False)

    # "generated" | "sent_to_doctor" | "answered"
    status = Column(
        String,
        nullable=False,
        default="generated",
    )

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    report = relationship(
        "LabReport",
        back_populates="questions",
    )

    indicator = relationship(
        "ReportIndicator",
        back_populates="questions",
    )


class DoctorNote(Base):
    """Ghi chú HITL của bác sĩ trên indicator hoặc report_question."""

    __tablename__ = "doctor_notes"

    __table_args__ = (
        Index(
            "ix_doctor_notes_target_type_target_id",
            "target_type",
            "target_id",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "indicator" | "report_question"
    target_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=False)

    note_text = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )


class OutOfScopeLog(Base):
    """Một chỉ số nằm ngoài phạm vi thư viện hỗ trợ."""

    __tablename__ = "out_of_scope_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    raw_indicator_name = Column(String, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    report = relationship(
        "LabReport",
        back_populates="out_of_scope_entries",
    )


DEMO_USERS = [
    {
        "username": "benhnhan",
        "password": "benhnhan123",
        "role": ROLE_PATIENT,
    },
    {
        "username": "bacsi",
        "password": "bacsi123",
        "role": ROLE_DOCTOR,
    },
]


def seed_demo_users(db: Session) -> None:
    """Seed tài khoản demo nếu bảng users đang trống.

    Chỉ seed khi bảng hoàn toàn rỗng. User đăng ký thật không bị ghi đè.
    """
    if db.query(User).count() != 0:
        return

    for user_data in DEMO_USERS:
        db.add(
            User(
                username=user_data["username"],
                password_hash=hash_password(user_data["password"]),
                role=user_data["role"],
            )
        )

    try:
        db.commit()
    except IntegrityError:
        # Hai process có thể cùng kiểm tra count()==0 rồi cùng seed.
        # Process đến sau rollback là đủ.
        db.rollback()


def _upgrade_sqlite_schema() -> None:
    """Bản vá tối thiểu cho SQLite cũ thiếu users.created_at.

    create_all() chỉ tạo bảng chưa tồn tại; nó không ALTER bảng cũ.
    Khi project cần nhiều migration hơn nên chuyển sang migration tool thật.
    """
    if engine.dialect.name != "sqlite":
        return

    with engine.begin() as conn:
        columns = {
            row[1]
            for row in conn.exec_driver_sql(
                "PRAGMA table_info(users)"
            )
        }

        # Bảng chưa tồn tại: để create_all() tạo mới.
        if not columns:
            return

        if "created_at" not in columns:
            conn.exec_driver_sql(
                "ALTER TABLE users ADD COLUMN created_at DATETIME"
            )
            conn.exec_driver_sql(
                "UPDATE users "
                "SET created_at = ? "
                "WHERE created_at IS NULL",
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
    "DoctorNote",
    "IndicatorCatalog",
    "LabReport",
    "OutOfScopeLog",
    "PERSISTED_ROLES",
    "ROLE_DOCTOR",
    "ROLE_PATIENT",
    "ReportCriticalAlert",
    "ReportIndicator",
    "ReportQuestion",
    "SessionLocal",
    "User",
    "engine",
    "get_db",
    "init_db",
    "seed_demo_users",
]


# Đảm bảo bảng + seed tồn tại kể cả khi ASGI lifespan không được kích hoạt
# trong một số test transport. init_db() là idempotent.
init_db()
