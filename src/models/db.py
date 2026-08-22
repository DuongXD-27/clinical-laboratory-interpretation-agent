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
Production chạy **Neon Postgres** từ 2026-08-15 (region Frankfurt, cùng khu với
Railway). `settings.database_url` mặc định `sqlite:///./data/app.db` chỉ là
fallback cho máy dev — đừng đọc giá trị mặc định đó như sự thật của production.

Hệ quả của việc DB nay sống dai hơn code: `create_all()` chỉ tạo bảng còn thiếu,
nó KHÔNG ALTER bảng đã có. Trước kia SQLite bị xoá mỗi lần redeploy nên bảng luôn
được tạo mới và không ai thấy vấn đề. Với Postgres, mỗi lần model thêm cột mà DB
chưa có là production trả 500 `UndefinedColumn` — đã xảy ra thật với
`report_indicators.critical_status`. `add_missing_columns()` bù chỗ đó, nhưng nó
chỉ THÊM được cột; đổi tên, đổi kiểu, xoá cột thì cần Alembic.
"""

from __future__ import annotations

import logging
import time
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
    UniqueConstraint,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker
from sqlalchemy.schema import CreateColumn
from sqlalchemy.types import JSON

from src.config import get_settings
from src.services.auth import hash_password
from src.services.request_timing import get_current_timing

logger = logging.getLogger(__name__)

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

# Admin chi xem duoc du lieu VAN HANH: do tre, so lan goi LLM, ma loi. Khong
# co endpoint nao cho admin doc benh an — `/history` van chi nhan patient va
# doctor. Tach nhu vay co chu y: nguoi lo ha tang khong can, va khong nen, doc
# duoc ket qua xet nghiem cua benh nhan.
ROLE_ADMIN = "admin"

PERSISTED_ROLES = (ROLE_PATIENT, ROLE_DOCTOR, ROLE_ADMIN)


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
    role = Column(String, nullable=False)  # "patient" | "doctor"
    full_name = Column(String, nullable=True)
    date_of_birth = Column(Date, nullable=True)
    sex = Column(String, nullable=True)
    email = Column(String, nullable=True)

    created_at = Column(
    DateTime(timezone=True),
    nullable=False,
    default=_utcnow,
    )

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        onupdate=_utcnow,
    )

    reports = relationship(
        "LabReport",
        back_populates="patient",
        cascade="all, delete-orphan",
        order_by="LabReport.test_date.desc()",
        foreign_keys="LabReport.patient_id",
    )


class LabReport(Base):
    """Một phiếu xét nghiệm đã phân tích, gắn với đúng một patient."""

    __tablename__ = "lab_reports"

    __table_args__ = (
        # Phục vụ đúng query lịch sử thật: WHERE patient_id=:X AND
        # test_date BETWEEN :A AND :B — composite (patient_id, test_date)
        # tự cover luôn query chỉ lọc patient_id (leftmost prefix), nên
        # bỏ index đơn ở patient_id bên dưới, tránh 2 index trùng công dụng.
        Index("ix_lab_reports_patient_id_test_date", "patient_id", "test_date"),
        Index("ix_lab_reports_patient_id_fingerprint", "patient_id", "report_fingerprint"),
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
    status = Column(String, nullable=False, default="NORMAL")
    report_fingerprint = Column(String, nullable=True)
    summary = Column(Text, nullable=False, default="")
    has_critical_values = Column(Boolean, nullable=False, default=False)
    guardrail_passed = Column(Boolean, nullable=False, default=True)
    disclaimer = Column(Text, nullable=False, default="")

    # Doctor verification workflow:
    # "unverified" | "pending_review" | "verified"
    verification_status = Column(String, nullable=False, default="unverified", index=True)
    priority_score = Column(Float, nullable=False, default=0.0)
    queued_at = Column(DateTime, nullable=True, index=True)
    verified_by_doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    verified_at = Column(DateTime, nullable=True)
    findings_total = Column(Integer, nullable=False, default=0)
    findings_reviewed = Column(Integer, nullable=False, default=0)

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    # Bổ sung counterpart cho User.reports(back_populates="patient").
    patient = relationship(
        "User",
        back_populates="reports",
        foreign_keys=[patient_id],
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

    doctor_views = relationship(
        "ReportDoctorView",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    review_flags = relationship(
        "ReviewFlag",
        back_populates="report",
        cascade="all, delete-orphan",
    )

    verified_by = relationship("User", foreign_keys=[verified_by_doctor_id])


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
    analyte_raw = Column(String, nullable=True)
    analyte_canonical = Column(String, nullable=True, index=True)
    raw_value = Column(Float, nullable=True)
    raw_unit = Column(String, nullable=True)
    canonical_value = Column(Float, nullable=True)
    canonical_unit = Column(String, nullable=True)

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

    # Nguồn sự thật cho normal/abnormal (low/high/normal/unknown).
    status = Column(String, nullable=False, default="unknown")
    # Biểu diễn riêng biệt cho critical state ("critical_low" / "critical_high" / None).
    critical_status = Column(String, nullable=True, default=None)

    # Context luật xét nghiệm gốc
    rule_type = Column(String, nullable=True)
    band_id = Column(String, nullable=True)
    upper_operator = Column(String, nullable=True)
    evaluation_reason = Column(String, nullable=True)

    explanation = Column(Text, nullable=False, default="")
    sources = Column(JSON, nullable=False, default=list)

    # Metadata OCR בלבד; không lưu ảnh gốc.
    ocr_confidence = Column(Float, nullable=True)
    ocr_raw_text = Column(Text, nullable=True)

    # Doctor finding-level review:
    # "pending" | "agreed" | "corrected" | "skipped"
    review_outcome = Column(String, nullable=False, default="pending", index=True)
    doctor_note = Column(Text, nullable=True)
    ai_text_snapshot = Column(Text, nullable=True)
    reviewed_by_doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewed_at = Column(DateTime, nullable=True)

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

    review_flags = relationship(
        "ReviewFlag",
        back_populates="finding",
        cascade="all, delete-orphan",
    )

    reviewed_by = relationship("User", foreign_keys=[reviewed_by_doctor_id])

    @property
    def is_abnormal(self) -> bool:
        """Derive từ status/critical_status để tránh hai nguồn sự thật."""
        return self.status in _ABNORMAL_STATUSES or bool(self.critical_status)

    @property
    def is_critical(self) -> bool:
        """Derive từ status/critical_status để tránh hai nguồn sự thật."""
        return bool(self.critical_status) or self.status in _CRITICAL_STATUSES


class OCRReviewLifecycle(Base):
    """Authoritative lifecycle for an OCR HITL review artifact."""

    __tablename__ = "ocr_review_lifecycle"

    __table_args__ = (
        Index("ix_ocr_review_lifecycle_user_status", "owner_user_id", "status", "expires_at"),
        Index("ix_ocr_review_lifecycle_session_status", "owner_session_id", "status", "expires_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    review_id = Column(String, unique=True, nullable=False, index=True)
    owner_subject = Column(String, nullable=False, index=True)
    owner_role = Column(String, nullable=False)
    owner_user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    owner_session_id = Column(String, nullable=True, index=True)
    status = Column(String, nullable=False, default="PENDING", index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=_utcnow)
    expires_at = Column(DateTime(timezone=True), nullable=False, index=True)
    consumed_at = Column(DateTime(timezone=True), nullable=True)


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

    # Nullable có chủ đích: một câu hỏi không phải lúc nào cũng thuộc về đúng
    # một chỉ số. Bộ câu dự phòng của Template Library (khi guardrail chặn) và
    # câu hỏi gộp nhóm nhiều chỉ số đều không có chỉ số duy nhất để trỏ vào.
    indicator_id = Column(
        Integer,
        ForeignKey("report_indicators.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    question_text = Column(Text, nullable=False)

    # "critical" | "abnormal" | "unknown" | "fallback"
    priority = Column(String, nullable=False)

    # Giữ đúng thứ tự ưu tiên lúc sinh; không dựa vào id để sắp xếp.
    display_order = Column(Integer, nullable=False, default=0)

    # "generated" -> "sent_to_doctor" (bệnh nhân tick chọn) -> "answered"
    status = Column(
        String,
        nullable=False,
        default="generated",
    )

    # Bệnh nhân tick chọn câu này để mang đi khám. Cả bộ câu vẫn được lưu, cờ
    # này chỉ đánh dấu câu nào được chọn — mở lại phiếu cũ vẫn thấy đủ bộ.
    is_selected = Column(Boolean, nullable=False, default=False)

    # Bác sĩ trả lời từng câu. Nội dung do người viết, KHÔNG qua guardrail.
    answer_text = Column(Text, nullable=True)

    answered_by_doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    answered_at = Column(DateTime, nullable=True)

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

    answered_by = relationship("User", foreign_keys=[answered_by_doctor_id])


class ReviewFlag(Base):
    """Lý do một phiếu hoặc một luận điểm được đưa vào hàng đợi kiểm chứng."""

    __tablename__ = "review_flags"

    __table_args__ = (
        Index("ix_review_flags_report_code", "report_id", "code"),
        Index("ix_review_flags_finding_code", "finding_id", "code"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    finding_id = Column(
        Integer,
        ForeignKey("report_indicators.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    code = Column(String, nullable=False)
    severity = Column(String, nullable=False)
    detail = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    report = relationship("LabReport", back_populates="review_flags")
    finding = relationship("ReportIndicator", back_populates="review_flags")


class DoctorNote(Base):
    """Ghi chú HITL của bác sĩ, gắn vào report / indicator / report_question.

    ``target_type="report"`` là dạng dùng thật hiện nay: nghiệp vụ quy định ghi
    chú thuộc về một phiếu xét nghiệm cụ thể, không thuộc về bệnh nhân nói
    chung. "Bác sĩ X nhận xét về phiếu ngày 05/08" khác "bác sĩ X nhận xét về
    bệnh nhân Y" — gắn theo phiếu giữ được ngữ cảnh bộ số, và một ghi chú cũ
    không bị đọc như đánh giá tình trạng hiện tại.

    Hai target_type còn lại giữ nguyên cho ghi chú ở mức chi tiết hơn.

    Nội dung ghi chú KHÔNG đi qua guardrail: bác sĩ có thẩm quyền nói đúng
    những điều hệ thống bị cấm (nguyên nhân, hướng điều trị), nên áp guardrail
    lên đây sẽ xoá mất lời chuyên môn hợp lệ. Đổi lại, mọi ghi chú phải hiển
    thị kèm tên người viết và thời điểm, trong khối tách bạch khỏi nội dung do
    hệ thống sinh.
    """

    __tablename__ = "doctor_notes"

    __table_args__ = (
        Index(
            "ix_doctor_notes_target_type_target_id",
            "target_type",
            "target_id",
        ),
    )

    TARGET_REPORT = "report"
    TARGET_INDICATOR = "indicator"
    TARGET_QUESTION = "report_question"

    id = Column(Integer, primary_key=True, autoincrement=True)

    doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "report" | "indicator" | "report_question"
    target_type = Column(String, nullable=False)
    target_id = Column(Integer, nullable=False)

    note_text = Column(Text, nullable=False)

    created_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    doctor = relationship("User")


class ReportDoctorView(Base):
    """Một bác sĩ đã chủ động đánh dấu là đã xem một phiếu.

    Tách khỏi "đã có ghi chú": bác sĩ đọc phiếu thấy mọi thứ bình thường vẫn
    cần báo được cho bệnh nhân là đã có người xem, mà không phải viết một câu
    vô nghĩa cho có.

    Lưu dạng nhiều dòng thay vì một cờ boolean trên ``lab_reports``: nếu bác sĩ
    A xem rồi bác sĩ B xem sau, một cờ chung sẽ mất thông tin bác sĩ B từng
    xem — dữ liệu này có giá trị tương tự ghi chú vì nó là bằng chứng có người
    xem. UNIQUE(report_id, doctor_id) để cùng một bác sĩ bấm nhiều lần không
    sinh thêm dòng.

    Đánh dấu bằng hành động chủ động (bấm nút), không tự động theo lượt mở
    trang: một bác sĩ lướt qua hoặc click nhầm sẽ khiến bệnh nhân nhận tín hiệu
    sai rằng phiếu đã được xem kỹ.
    """

    __tablename__ = "report_doctor_views"

    __table_args__ = (
        UniqueConstraint(
            "report_id",
            "doctor_id",
            name="uq_report_doctor_views_report_doctor",
        ),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    report_id = Column(
        Integer,
        ForeignKey("lab_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    doctor_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    viewed_at = Column(
        DateTime,
        nullable=False,
        default=_utcnow,
    )

    report = relationship("LabReport", back_populates="doctor_views")
    doctor = relationship("User")


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


# Co tinh KHONG co tai khoan admin trong day. Mat khau demo la cong khai voi
# ca cohort; mot admin seed san la mot cua hau ai cung dang nhap duoc. Admin
# chi tao bang `python -m src.scripts.create_admin`, giong cach doctor duoc
# cap phat.

class RequestTrace(Base):
    """Một dòng vận hành cho mỗi request HTTP, phục vụ màn hình admin.

    Vì sao lưu vào DB của mình thay vì đọc ngược từ Langfuse: màn hình admin
    phải xem được kể cả khi Langfuse chưa cấu hình, hết hạn key, hoặc không gọi
    ra ngoài được. Langfuse lo phần sâu (prompt, token, chi phí từng lần gọi);
    bảng này lo phần rộng — mọi request, kể cả request không đụng tới LLM.

    **Bảng này không được chứa dữ liệu bệnh nhân.** Không tên chỉ số, không giá
    trị, không username, không nội dung prompt. Cùng nguyên tắc đã khiến
    listener SQLAlchemy không bao giờ log `statement`/`parameters`. `path` là
    khuôn đường dẫn nên `/history/12` có lộ một id — id đó vô nghĩa nếu không
    có token của đúng chủ nhân, và không có nó thì không phân biệt được request
    chậm thuộc màn hình nào.

    `user_role` lưu vai trò chứ không lưu người: đủ để biết "màn bác sĩ đang
    chậm", không đủ để lần ra ai đã khám gì.
    """

    __tablename__ = "request_traces"

    __table_args__ = (
        # Truy vấn duy nhất màn admin thực sự chạy: lọc theo thời gian, mới
        # nhất trước.
        Index("ix_request_traces_created_at", "created_at"),
        Index("ix_request_traces_request_id", "request_id"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)

    # Chính là id trả về trong header X-Request-ID và trong body lỗi 500. Đây
    # là thứ duy nhất nối "tôi bấm bị lỗi" với một dòng cụ thể ở đây.
    request_id = Column(String(64), nullable=False)

    created_at = Column(DateTime, nullable=False, default=_utcnow)

    method = Column(String(10), nullable=False)
    path = Column(String(255), nullable=False)
    status_code = Column(Integer, nullable=False)
    duration_ms = Column(Float, nullable=False, default=0.0)

    db_query_count = Column(Integer, nullable=False, default=0)
    db_ms = Column(Float, nullable=False, default=0.0)

    llm_call_count = Column(Integer, nullable=False, default=0)
    llm_ms = Column(Float, nullable=False, default=0.0)
    # Field đáng giá nhất: LLM hỏng thì response vẫn 200 và nội dung âm thầm
    # xuống cấp, chỉ bệnh nhân nhận ra.
    llm_error_count = Column(Integer, nullable=False, default=0)

    user_role = Column(String(20), nullable=True)

    # Chuỗi Server-Timing, giữ nguyên để màn chi tiết dựng lại được cây span mà
    # không cần thêm bảng con.
    server_timing = Column(Text, nullable=True)



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


def _sqlite_table_columns(table_name: str) -> set[str]:
    with engine.connect() as conn:
        rows = conn.exec_driver_sql(f"PRAGMA table_info({table_name})").fetchall()
    return {str(row[1]) for row in rows}


def add_missing_columns() -> list[str]:
    """Thêm cột model đã khai nhưng bảng thật chưa có. Chạy cho MỌI dialect.

    ``create_all()`` chỉ tạo bảng còn thiếu, nó **không bao giờ ALTER** bảng đã
    tồn tại. Với SQLite trên Railway thì điều đó vô hại vì đĩa bị xoá mỗi lần
    redeploy nên bảng luôn được tạo mới. Từ khi production chuyển sang Postgres
    (2026-08-15) thì DB sống dai hơn code, và mỗi lần model thêm cột là
    production trả 500 ``UndefinedColumn`` — đã xảy ra thật với
    ``report_indicators.critical_status``.

    Danh sách cột được **suy ra từ chính model**, không phải bảng viết tay. Bản
    trước liệt kê tay theo từng bảng, nên chỉ cần ai thêm cột mà quên cập nhật
    danh sách là lại đứt — đúng cách mà `critical_status` lọt lưới.

    Cột được thêm dạng NULLABLE kể cả khi model khai NOT NULL: bảng có thể đang
    có dòng cũ, thêm NOT NULL mà không có server default sẽ fail. Ứng dụng vẫn
    ghi bình thường vì default nằm ở tầng Python.

    Đây là bản vá tối thiểu cho mô hình create_all, KHÔNG phải migration tool.
    Nó chỉ thêm cột; đổi tên, đổi kiểu và xoá cột đều nằm ngoài khả năng. Khi cần
    những thứ đó thì phải đưa Alembic vào.

    Trả về danh sách "bảng.cột" đã thêm, để test và log kiểm được.
    """

    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    added: list[str] = []

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                # Bảng chưa có: create_all() sẽ tạo đầy đủ, không cần ALTER.
                continue

            db_columns = {column["name"] for column in inspector.get_columns(table.name)}

            for column in table.columns:
                if column.name in db_columns:
                    continue

                ddl = str(CreateColumn(column).compile(engine)).replace(" NOT NULL", "")
                conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN {ddl}'))
                added.append(f"{table.name}.{column.name}")

    if added:
        logger.warning(
            "Schema drift: da them %d cot con thieu -> %s",
            len(added),
            ", ".join(added),
        )

    return added


def backfill_added_column_defaults() -> None:
    """Điền giá trị cho các cột vừa được thêm, vì dòng cũ đang để NULL.

    Chạy cho mọi dialect chứ không riêng SQLite: cột thêm trên Postgres cũng
    NULL y hệt, và một `status` NULL sẽ khiến màn lịch sử hiển thị sai.

    Dùng `text()` với tham số đặt tên thay cho placeholder `?` của SQLite, để
    câu lệnh chạy đúng trên cả hai.
    """

    now = datetime.now(UTC).replace(tzinfo=None)

    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE users SET created_at = COALESCE(created_at, :now), "
                "updated_at = COALESCE(updated_at, :now)"
            ),
            {"now": now},
        )
        conn.execute(
            text(
                "UPDATE lab_reports SET status = COALESCE(status, "
                "CASE WHEN has_critical_values THEN 'CRITICAL' ELSE 'NORMAL' END)"
            )
        )
        conn.execute(
            text(
                "UPDATE lab_reports SET verification_status = "
                "COALESCE(verification_status, 'unverified'), "
                "priority_score = COALESCE(priority_score, 0), "
                "findings_total = COALESCE(findings_total, "
                "(SELECT COUNT(*) FROM report_indicators "
                "WHERE report_indicators.report_id = lab_reports.id)), "
                "findings_reviewed = COALESCE(findings_reviewed, 0)"
            )
        )
        conn.execute(
            text(
                "UPDATE report_indicators SET critical_status = status "
                "WHERE critical_status IS NULL "
                "AND status IN ('critical_low', 'critical_high')"
            )
        )
        conn.execute(
            text(
                "UPDATE report_indicators SET review_outcome = "
                "COALESCE(review_outcome, 'pending')"
            )
        )


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



def init_db() -> None:
    """Tạo bảng còn thiếu, bù cột còn thiếu, rồi seed tài khoản demo.

    Thứ tự bắt buộc: `create_all()` trước để bảng mới tồn tại, rồi
    `add_missing_columns()` mới ALTER được những bảng cũ.
    """

    Base.metadata.create_all(bind=engine)
    add_missing_columns()
    backfill_added_column_defaults()

    with SessionLocal() as db:
        seed_demo_users(db)


# Gắn vào lớp Engine chứ không phải instance `engine` ở trên: test dựng engine
# riêng trên file tạm, và code sau này có thể tạo thêm engine. Đo theo lớp thì
# mọi truy vấn đều được tính, không phụ thuộc ai tạo engine.
@event.listens_for(Engine, "before_cursor_execute")
def _db_query_started(conn, cursor, statement, parameters, context, executemany) -> None:
    context._vmec_started_at = time.perf_counter()


@event.listens_for(Engine, "after_cursor_execute")
def _db_query_finished(conn, cursor, statement, parameters, context, executemany) -> None:
    """Cộng dồn thời gian và số truy vấn của mỗi request.

    Ghi ở mức tổng chứ không mỗi truy vấn một event: một request lịch sử có thể
    bắn hàng chục câu, log từng câu sẽ chìm mất dòng trace. Số đếm mới là thứ
    phát hiện N+1 — đúng loại lỗi vừa gặp ở `_to_summary()`, vô hình khi DB nằm
    cùng đĩa và thành vài giây khi DB ra ngoài mạng.

    Tuyệt đối không ghi `statement` hay `parameters`: tham số chứa giá trị xét
    nghiệm và username của bệnh nhân.
    """

    started_at = getattr(context, "_vmec_started_at", None)
    if started_at is None:
        return

    timing = get_current_timing()
    if timing is None:
        return

    timing.accumulate("db-query", (time.perf_counter() - started_at) * 1000)


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
    "OCRReviewLifecycle",
    "OutOfScopeLog",
    "PERSISTED_ROLES",
    "ROLE_ADMIN",
    "ROLE_DOCTOR",
    "ROLE_PATIENT",
    "ReportCriticalAlert",
    "ReportIndicator",
    "ReportQuestion",
    "RequestTrace",
    "ReviewFlag",
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
