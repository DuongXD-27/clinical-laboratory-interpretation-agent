"""DB cho auth + lịch sử xét nghiệm bệnh nhân.

SQLite, tạo bảng qua create_all() (không dùng Alembic — quy mô project
này chưa cần versioned migration). Seed vài tài khoản demo lúc khởi động
nếu bảng users đang trống, để hoạt động ổn định kể cả khi disk trên
Render bị reset (free tier không có persistent disk).

users (1) --- (N) lab_reports (1) --- (N) report_indicators (N) --- (1) indicator_catalog
                              (1) --- (N) report_critical_alerts
                              (1) --- (N) report_questions (1) --- (N) doctor_notes*
                              (1) --- (N) out_of_scope_log

* doctor_notes dùng polymorphic association (target_type/target_id) để trỏ
  vào "indicator" (report_indicators.id) hoặc "report_question"
  (report_questions.id) mà không cần 2 cột FK nullable riêng. Đánh đổi:
  DB không tự ràng buộc target_id phải tồn tại — tầng ứng dụng chịu trách
  nhiệm đảm bảo tính đúng đắn, không có FK constraint thật cho cột này.

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
    # Chỉ TÊN FILE (label hiển thị) nếu report tới từ luồng OCR, KHÔNG phải
    # đường dẫn/ảnh thật — đúng field `source_image` đã có sẵn trong
    # OCRReviewResponse, vốn đã trả về client rồi nên lưu lại không phát
    # sinh rủi ro privacy mới. Nullable vì input JSON thủ công không có.
    ocr_source_filename = Column(String, nullable=True)
    language = Column(String, nullable=False, default="vi")
    summary = Column(Text, nullable=False, default="")
    has_critical_values = Column(Boolean, nullable=False, default=False)
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    disclaimer = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    indicators = relationship(
        "ReportIndicator", back_populates="report", cascade="all, delete-orphan"
    )
    critical_alerts = relationship(
        "ReportCriticalAlert", back_populates="report", cascade="all, delete-orphan"
    )
    # Thay cho 2 cột JSON questions_for_doctor/out_of_scope_indicators cũ —
    # chuẩn hoá thành bảng riêng để mỗi câu hỏi/chỉ số ngoài phạm vi có PK
    # thật, tránh 2 nguồn sự thật trùng lặp (JSON blob + bảng con).
    questions = relationship(
        "ReportQuestion", back_populates="report", cascade="all, delete-orphan"
    )
    out_of_scope_entries = relationship(
        "OutOfScopeLog", back_populates="report", cascade="all, delete-orphan"
    )


_ABNORMAL_STATUSES = frozenset({"low", "high", "critical_low", "critical_high"})
_CRITICAL_STATUSES = frozenset({"critical_low", "critical_high"})


class ReportIndicator(Base):
    """Một chỉ số trong 1 phiếu — snapshot kết quả phân tích tại thời điểm lưu."""

    __tablename__ = "report_indicators"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    # Nullable: OCR/nhập tay có thể tạo ra tên chưa từng có trong catalog —
    # không được chặn cứng việc lưu report chỉ vì 1 chỉ số chưa canonical hoá.
    indicator_catalog_id = Column(
        Integer, ForeignKey("indicator_catalog.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False, default="")
    reference_low = Column(Float, nullable=True)
    reference_high = Column(Float, nullable=True)
    status = Column(String, nullable=False, default="unknown")
    explanation = Column(Text, nullable=False, default="")
    sources = Column(JSON, nullable=False, default=list)
    # Provenance OCR — CHỈ metadata đã hiển thị cho người dùng ở UI_Review
    # (confidence, text thô đọc được). TUYỆT ĐỐI không lưu ảnh/đường dẫn ảnh
    # ở đây hay bất kỳ đâu khác — vi phạm cam kết "không lưu ảnh gốc" (V3),
    # xem src/api/ocr_routes.py dòng gần "không ghi ra đĩa, không đưa vào DB".
    # Nullable vì input nhập tay (JSON) không có OCR.
    ocr_confidence = Column(Float, nullable=True)
    ocr_raw_text = Column(Text, nullable=True)

    report = relationship("LabReport", back_populates="indicators")
    catalog_entry = relationship("IndicatorCatalog", back_populates="indicators")
    questions = relationship(
        "ReportQuestion", back_populates="indicator", cascade="all, delete-orphan"
    )

    @property
    def is_abnormal(self) -> bool:
        """Derive từ `status` — KHÔNG lưu cột riêng để tránh 2 nguồn sự thật
        có thể mâu thuẫn nhau (status="critical_high" nhưng is_abnormal=False
        do bug tầng ứng dụng). `status` là nguồn sự thật duy nhất."""
        return self.status in _ABNORMAL_STATUSES

    @property
    def is_critical(self) -> bool:
        """Derive từ `status`, cùng lý do với `is_abnormal` ở trên."""
        return self.status in _CRITICAL_STATUSES


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


class IndicatorCatalog(Base):
    """Danh mục chỉ số chuẩn hoá — resolve tên đọc được (OCR/nhập tay) về 1
    canonical_name duy nhất, để trend (so sánh nhiều lần xét nghiệm) match
    đúng theo thời gian thay vì string-match trực tiếp trên report_indicators.name
    (dễ gãy âm thầm nếu OCR đọc "HbA1c" lần này, "Hemoglobin A1c" lần khác).
    """

    __tablename__ = "indicator_catalog"

    id = Column(Integer, primary_key=True, autoincrement=True)
    canonical_name = Column(String, nullable=False, unique=True, index=True)
    canonical_unit = Column(String, nullable=False)
    aliases = Column(JSON, nullable=False, default=list)  # list[str]
    unit_conversions = Column(JSON, nullable=False, default=dict)  # {"mg/dL": 0.0555, ...}
    max_gap_days_for_trend = Column(Integer, nullable=True)

    indicators = relationship("ReportIndicator", back_populates="catalog_entry")


class ReportQuestion(Base):
    """1 câu hỏi gợi ý hỏi bác sĩ, gắn với đúng 1 chỉ số bất thường/nguy kịch
    của 1 report. Thay cho JSON list[str] cũ (lab_reports.questions_for_doctor)
    — cần PK thật để doctor_notes trỏ vào, và cần trạng thái riêng từng câu.
    """

    __tablename__ = "report_questions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    indicator_id = Column(
        Integer, ForeignKey("report_indicators.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_text = Column(Text, nullable=False)
    priority = Column(String, nullable=False)  # "critical" | "abnormal"
    status = Column(String, nullable=False, default="generated")  # "generated" | "sent_to_doctor" | "answered"
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    report = relationship("LabReport", back_populates="questions")
    indicator = relationship("ReportIndicator", back_populates="questions")


class DoctorNote(Base):
    """Ghi chú diễn giải của bác sĩ (Human-in-the-loop) trên 1 chỉ số hoặc
    1 câu hỏi cụ thể. target_type/target_id là polymorphic association —
    xem docstring đầu file về đánh đổi (không có FK constraint thật)."""

    __tablename__ = "doctor_notes"

    id = Column(Integer, primary_key=True, autoincrement=True)
    doctor_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    target_type = Column(String, nullable=False)  # "indicator" | "report_question"
    target_id = Column(Integer, nullable=False)
    note_text = Column(Text, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))


class OutOfScopeLog(Base):
    """Log riêng cho từng chỉ số ngoài phạm vi hỗ trợ, tách khỏi JSON blob
    trong lab_reports để truy vấn được "chỉ số nào out-of-scope nhiều nhất"
    mà không cần parse JSON qua toàn bộ report."""

    __tablename__ = "out_of_scope_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(Integer, ForeignKey("lab_reports.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_indicator_name = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, default=lambda: datetime.now(UTC))

    report = relationship("LabReport", back_populates="out_of_scope_entries")


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
