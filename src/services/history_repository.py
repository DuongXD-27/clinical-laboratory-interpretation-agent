"""Đọc/ghi lịch sử xét nghiệm của bệnh nhân.

Repository này chịu trách nhiệm persistence và patient scoping cho lịch sử.

Schema canonical:
    users.id
        ↓
    lab_reports.patient_id
        ↓
    report_indicators.report_id

Authorization theo role vẫn được quyết định ở API route. Repository không tự
suy diễn role từ request; khi truy vấn lịch sử của một patient cụ thể, caller
phải truyền patient_id rõ ràng.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, object_session, selectinload

from src.models.db import (
    ROLE_PATIENT,
    DoctorNote,
    IndicatorCatalog,
    LabReport,
    OutOfScopeLog,
    ReportCriticalAlert,
    ReportDoctorView,
    ReportIndicator,
    ReportQuestion,
    User,
    _utcnow,
)
from src.models.ocr_schemas import OCRIndicatorDraft
from src.models.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    DoctorNoteSchema,
    IndicatorResultSchema,
    LabReportDetailSchema,
    LabReportSummarySchema,
    ReportDoctorViewSchema,
    ReportQuestionSchema,
)
from src.services.analyte_sections import analyte_section, section_label
from src.services.indicator_catalog_service import (
    IndicatorConfigurationError,
    IndicatorConfigurationService,
    get_indicator_configuration_service,
)
from src.services.medical_citations import get_medical_citation_repository
from src.services.question_templates import GeneratedQuestion
from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError

logger = logging.getLogger(__name__)


def _structured_explanation_sources(indicator: ReportIndicator) -> list[dict]:
    return [
        citation.as_dict()
        for citation in get_medical_citation_repository().resolve_many(
            analyte=indicator.analyte_canonical or indicator.name,
            sources=list(indicator.sources or []),
        )
    ]


def _normalize_indicator_name(name: str) -> str:
    """Chuẩn hóa tối thiểu để ghép metadata OCR với indicator kết quả."""
    return name.strip().casefold()


def _find_ocr_metadata(
    indicator_name: str,
    ocr_drafts: list[OCRIndicatorDraft] | None,
) -> tuple[float | None, str | None]:
    """Tìm metadata OCR tương ứng với một indicator.

    Chỉ gắn metadata khi tên indicator khớp. Không ghép theo index vì graph
    có thể thay đổi/drop/reorder indicator; ghép sai confidence/raw_text còn
    nguy hiểm hơn việc để metadata là NULL.
    """
    if not ocr_drafts:
        return None, None

    normalized_name = _normalize_indicator_name(indicator_name)

    for draft in ocr_drafts:
        if _normalize_indicator_name(draft.name) == normalized_name:
            return draft.confidence, draft.raw_text

    return None, None


def _reference_repository() -> ReferenceRepository | None:
    try:
        return ReferenceRepository.from_default_files()
    except ReferenceRepositoryError:
        return None


def _indicator_configuration_service() -> IndicatorConfigurationService | None:
    try:
        return get_indicator_configuration_service()
    except (IndicatorConfigurationError, ReferenceRepositoryError):
        return None


def _canonical_indicator_snapshot(
    *,
    repository: ReferenceRepository | None,
    indicator: IndicatorResultSchema,
    raw_name: str,
    raw_value: float,
    raw_unit: str,
) -> dict[str, object]:
    canonical_source = indicator.analyte_canonical or raw_name or indicator.name
    resolved_analyte = repository.resolve_analyte(canonical_source) if repository is not None else None
    canonical_unit_source = indicator.canonical_unit or raw_unit or indicator.unit
    canonical_unit = (
        repository.normalize_unit(canonical_unit_source) if repository is not None else canonical_unit_source
    )

    return {
        "analyte_raw": raw_name,
        "analyte_canonical": resolved_analyte or indicator.analyte_canonical,
        "raw_value": raw_value,
        "raw_unit": raw_unit,
        "canonical_value": indicator.canonical_value if indicator.canonical_value is not None else raw_value,
        "canonical_unit": canonical_unit,
    }


def _catalog_entry_for_snapshot(
    db: Session,
    *,
    configuration_service: IndicatorConfigurationService | None,
    canonical_name: object,
    canonical_unit: object,
    cache: dict[str, IndicatorCatalog],
) -> IndicatorCatalog | None:
    """Resolve/create the DB foreign-key target from the validated config facade.

    Unknown indicators and an unexpected unit deliberately remain unlinked: a
    history snapshot is still preserved, but it must not borrow another
    indicator's policy or aliases.
    """
    if configuration_service is None or not isinstance(canonical_name, str):
        return None
    configured = configuration_service.get(canonical_name)
    if configured is None or configured.canonical_unit != canonical_unit:
        return None
    if canonical_name in cache:
        return cache[canonical_name]

    entry = db.scalar(select(IndicatorCatalog).where(IndicatorCatalog.canonical_name == canonical_name))
    if entry is None:
        entry = IndicatorCatalog(
            canonical_name=configured.canonical_name,
            canonical_unit=configured.canonical_unit,
            aliases=list(configured.aliases),
            max_gap_days_for_trend=configured.max_gap_days,
        )
        db.add(entry)
    cache[canonical_name] = entry
    return entry


def save_report(
    db: Session,
    *,
    patient_id: int,
    request: AnalyzeRequest,
    response: AnalyzeResponse,
    questions: Sequence[GeneratedQuestion] | None = None,
    ocr_drafts: list[OCRIndicatorDraft] | None = None,
    ocr_source_filename: str | None = None,
) -> LabReport:
    """Lưu một lần phân tích vào lịch sử của patient.

    Chỉ route của authenticated patient được phép gọi hàm này.

    Không lưu:
    - ảnh OCR gốc;
    - is_abnormal/is_critical thành DB column;
    - source manual/ocr thành DB column.

    is_abnormal/is_critical được derive từ status.
    source được derive từ ocr_source_filename.
    """

    report_indicators: list[ReportIndicator] = []
    repository = _reference_repository()
    configuration_service = _indicator_configuration_service()
    catalog_entries: dict[str, IndicatorCatalog] = {}

    for index, indicator in enumerate(response.indicators):
        raw_input = request.indicators[index] if index < len(request.indicators) else None
        raw_name = raw_input.name if raw_input is not None else indicator.name
        raw_value = raw_input.value if raw_input is not None else indicator.value
        raw_unit = raw_input.unit if raw_input is not None else indicator.unit
        ocr_confidence, ocr_raw_text = _find_ocr_metadata(
            indicator.name,
            ocr_drafts,
        )
        canonical_snapshot = _canonical_indicator_snapshot(
            repository=repository,
            indicator=indicator,
            raw_name=raw_name,
            raw_value=raw_value,
            raw_unit=raw_unit,
        )
        catalog_entry = _catalog_entry_for_snapshot(
            db,
            configuration_service=configuration_service,
            canonical_name=canonical_snapshot["analyte_canonical"],
            canonical_unit=canonical_snapshot["canonical_unit"],
            cache=catalog_entries,
        )

        report_indicators.append(
            ReportIndicator(
                analyte_raw=canonical_snapshot["analyte_raw"],
                analyte_canonical=canonical_snapshot["analyte_canonical"],
                raw_value=canonical_snapshot["raw_value"],
                raw_unit=canonical_snapshot["raw_unit"],
                canonical_value=canonical_snapshot["canonical_value"],
                canonical_unit=canonical_snapshot["canonical_unit"],
                name=indicator.name,
                value=indicator.value,
                unit=indicator.unit,
                reference_low=indicator.reference_low,
                reference_high=indicator.reference_high,
                status=indicator.status,
                critical_status=getattr(indicator, "critical_status", None),
                rule_type=getattr(indicator, "rule_type", None),
                band_id=getattr(indicator, "band_id", None),
                upper_operator=getattr(indicator, "upper_operator", None),
                evaluation_reason=getattr(indicator, "evaluation_reason", None),
                explanation=indicator.explanation or "",
                sources=list(indicator.sources or []),
                catalog_entry=catalog_entry,
                ocr_confidence=ocr_confidence,
                ocr_raw_text=ocr_raw_text,
            )
        )

    critical_alerts = [
        ReportCriticalAlert(
            indicator_name=alert.indicator_name,
            value=alert.value,
            unit=alert.unit,
            message=alert.message,
        )
        for alert in response.critical_alerts
    ]

    out_of_scope_entries = [
        OutOfScopeLog(
            raw_indicator_name=indicator_name,
        )
        for indicator_name in response.out_of_scope_indicators
    ]

    report = LabReport(
        patient_id=patient_id,
        test_date=request.test_date,
        # Snapshot tại thời điểm xét nghiệm.
        patient_age_at_test=request.patient_age,
        patient_gender_at_test=request.patient_gender,
        # None = manual.
        # Có filename = report tới từ OCR.
        ocr_source_filename=ocr_source_filename,
        language=request.language,
        has_critical_values=response.has_critical_values,
        guardrail_passed=response.guardrail_passed,
        summary=response.summary or "",
        disclaimer=response.disclaimer or "",
        indicators=report_indicators,
        critical_alerts=critical_alerts,
        out_of_scope_entries=out_of_scope_entries,
    )

    db.add(report)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(report)

    if questions:
        _attach_questions(db, report, questions)

    return report


def _attach_questions(
    db: Session,
    report: LabReport,
    questions: Sequence[GeneratedQuestion],
) -> None:
    """Lưu bộ câu hỏi gợi ý của phiếu, nối về đúng dòng chỉ số khi nối được.

    Lưu **cả bộ** câu sinh ra, không chỉ những câu bệnh nhân tick chọn: mở lại
    phiếu cũ phải thấy đúng bộ câu của lần đó, vì bệnh nhân có thể đã in ra mang
    đi khám và đang mở lại để đối chiếu. Việc bệnh nhân chọn câu nào được ghi
    riêng bằng cờ ``is_selected``.

    Chạy sau khi report đã commit để ``report_indicators`` có id thật.
    """

    indicator_ids: dict[str, int] = {}

    for indicator in report.indicators:
        key = _normalize_indicator_name(indicator.name)
        # Phiếu có hai dòng cùng tên thì giữ dòng đầu; nối vào dòng nào cũng
        # thuộc đúng phiếu đó nên không rò rỉ sang phiếu khác.
        indicator_ids.setdefault(key, indicator.id)

    for question in questions:
        indicator_id = None

        if question.indicator_name:
            indicator_id = indicator_ids.get(_normalize_indicator_name(question.indicator_name))

        db.add(
            ReportQuestion(
                report_id=report.id,
                indicator_id=indicator_id,
                question_text=question.text,
                priority=question.priority,
                display_order=question.display_order,
                status="generated",
                is_selected=False,
            )
        )

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(report)


def _base_query(
    patient_id: int | None,
    from_date: date | None,
    to_date: date | None,
):
    """Tạo query history với date range inclusive."""

    stmt = select(LabReport)

    if patient_id is not None:
        stmt = stmt.where(LabReport.patient_id == patient_id)

    # Inclusive cả hai đầu:
    # from_date <= test_date <= to_date
    if from_date is not None:
        stmt = stmt.where(LabReport.test_date >= from_date)

    if to_date is not None:
        stmt = stmt.where(LabReport.test_date <= to_date)

    return stmt


def list_reports(
    db: Session,
    *,
    patient_id: int | None = None,
    from_date: date | None = None,
    to_date: date | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[int, list[LabReportSummarySchema]]:
    """Trả về tổng số record và trang history hiện tại.

    patient_id=<id>:
        chỉ lấy report của patient đó.

    patient_id=None:
        không giới hạn patient ở repository level. Chỉ API route được phép
        quyết định role nào có quyền sử dụng chế độ này.
    """

    stmt = _base_query(
        patient_id,
        from_date,
        to_date,
    )

    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0

    rows = (
        db.execute(
            stmt.options(
                selectinload(LabReport.indicators),
                selectinload(LabReport.patient),
                selectinload(LabReport.verified_by),
                # doctor_views nạp sẵn để `_is_reviewed()` không lazy-load từng
                # dòng — cùng lý do với `_report_ids_with_notes()` bên dưới.
                selectinload(LabReport.doctor_views),
            )
            .order_by(
                LabReport.test_date.desc(),
                LabReport.id.desc(),
            )
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )

    # Một truy vấn cho cả trang, thay vì hai truy vấn mỗi phiếu.
    with_notes = _report_ids_with_notes(db, [report.id for report in rows])

    return total, [_to_summary(report, has_notes=report.id in with_notes) for report in rows]


def get_report(
    db: Session,
    report_id: int,
) -> LabReport | None:
    """Lấy một report cùng các child cần cho màn detail."""

    return (
        db.execute(
            select(LabReport)
            .where(LabReport.id == report_id)
            .options(
                selectinload(LabReport.patient),
                selectinload(LabReport.verified_by),
                selectinload(LabReport.indicators).selectinload(ReportIndicator.reviewed_by),
                selectinload(LabReport.critical_alerts),
                selectinload(LabReport.questions).selectinload(ReportQuestion.answered_by),
                selectinload(LabReport.out_of_scope_entries),
                selectinload(LabReport.doctor_views).selectinload(ReportDoctorView.doctor),
            )
        )
    ).scalar_one_or_none()


def resolve_patient_id(
    db: Session,
    username: str,
) -> int | None:
    """Resolve username của patient persistent thành users.id."""

    user = db.execute(
        select(User).where(
            User.username == username,
            User.role == ROLE_PATIENT,
        )
    ).scalar_one_or_none()

    if user is None:
        return None

    return user.id


def _derive_source(report: LabReport) -> str:
    """Presentation value; không phải DB column."""

    if report.ocr_source_filename is not None:
        return "ocr"

    return "manual"


def _notes_for_report(report: LabReport) -> list[DoctorNote]:
    """Ghi chú gắn vào cả phiếu, mới nhất nằm trên.

    Ghi chú ở mức chỉ số hoặc mức câu hỏi (target_type khác) không nằm trong
    khối này; hiện chưa có đường ghi nào tạo ra chúng.

    ``DoctorNote.target_id`` không phải FK thật (polymorphic association) nên
    không có relationship để join — phải truy vấn tay theo cặp
    (target_type, target_id), đúng cặp cột mà index kép trên bảng phục vụ.
    """

    session = object_session(report)

    if session is None:
        return []

    return list(
        session.scalars(
            select(DoctorNote)
            .where(
                DoctorNote.target_type == DoctorNote.TARGET_REPORT,
                DoctorNote.target_id == report.id,
            )
            .order_by(DoctorNote.created_at.desc(), DoctorNote.id.desc())
        )
    )


def _report_ids_with_notes(
    db: Session,
    report_ids: Sequence[int],
) -> set[int]:
    """Trong một truy vấn, trả về những phiếu nào đang có ghi chú.

    Dùng cho màn danh sách. Trước đây `_to_summary()` gọi `_notes_for_report()`
    hai lần cho mỗi phiếu (một lần trực tiếp, một lần qua `_is_reviewed()`), tức
    danh sách 20 phiếu bắn 40 truy vấn phụ. Với SQLite trên cùng đĩa thì không ai
    thấy; với Postgres đặt ngoài mạng thì mỗi truy vấn là một lượt round trip và
    màn lịch sử phình theo số phiếu.

    Chỉ cần biết CÓ hay KHÔNG nên select đúng `target_id`, không lấy nội dung.
    """

    if not report_ids:
        return set()

    return set(
        db.scalars(
            select(DoctorNote.target_id).where(
                DoctorNote.target_type == DoctorNote.TARGET_REPORT,
                DoctorNote.target_id.in_(report_ids),
            )
        )
    )


def _is_reviewed(report: LabReport, *, has_notes: bool) -> bool:
    """Đã xem HOẶC đã có ghi chú.

    Một phiếu có ghi chú thì hiển nhiên đã được xem, kể cả khi bác sĩ không bấm
    nút đánh dấu.

    `has_notes` truyền vào thay vì tự truy vấn, để caller quyết định nạp theo lô
    (màn danh sách) hay nạp lẻ (màn chi tiết).
    """

    return bool(report.doctor_views) or has_notes


def question_to_schema(question: ReportQuestion) -> ReportQuestionSchema:
    return ReportQuestionSchema(
        id=question.id,
        indicator_id=question.indicator_id,
        question_text=question.question_text,
        priority=question.priority,
        status=question.status,
        display_order=question.display_order,
        is_selected=bool(question.is_selected),
        answer_text=question.answer_text,
        answered_at=question.answered_at,
        answered_by_username=(question.answered_by.username if question.answered_by is not None else None),
        created_at=question.created_at,
    )


def note_to_schema(note: DoctorNote) -> DoctorNoteSchema:
    return DoctorNoteSchema(
        id=note.id,
        doctor_id=note.doctor_id,
        target_type=note.target_type,
        target_id=note.target_id,
        note_text=note.note_text,
        created_at=note.created_at,
        doctor_username=(note.doctor.username if note.doctor is not None else None),
    )


def _to_summary(
    report: LabReport,
    *,
    has_notes: bool,
) -> LabReportSummarySchema:
    """Convert ORM report thành history-list item.

    `has_notes` do caller nạp theo lô bằng `_report_ids_with_notes()`, để hàm này
    không sinh truy vấn phụ nào cho mỗi dòng.
    """

    return LabReportSummarySchema(
        id=report.id,
        patient_username=(report.patient.username if report.patient is not None else None),
        test_date=report.test_date,
        created_at=report.created_at,
        indicator_count=len(report.indicators),
        abnormal_count=sum(1 for indicator in report.indicators if indicator.is_abnormal),
        has_critical_values=report.has_critical_values,
        source=_derive_source(report),
        summary=report.summary,
        reviewed_by_doctor=_is_reviewed(report, has_notes=has_notes),
        has_doctor_notes=has_notes,
        verification_status=report.verification_status or "unverified",
        verified_by_username=(report.verified_by.username if report.verified_by is not None else None),
        verified_at=report.verified_at,
    )


def to_detail(
    report: LabReport,
) -> LabReportDetailSchema:
    """Convert ORM report thành response detail đầy đủ."""

    # Nạp một lần rồi dùng lại cho cả ba chỗ (danh sách ghi chú, cờ đã xem, cờ có
    # ghi chú). Trước đây mỗi chỗ tự truy vấn lại cùng một thứ.
    notes = _notes_for_report(report)

    return LabReportDetailSchema(
        id=report.id,
        patient_id=report.patient_id,
        patient_username=(report.patient.username if report.patient is not None else None),
        test_date=report.test_date,
        created_at=report.created_at,
        patient_age_at_test=report.patient_age_at_test,
        patient_gender_at_test=report.patient_gender_at_test,
        language=report.language,
        summary=report.summary,
        has_critical_values=report.has_critical_values,
        guardrail_passed=report.guardrail_passed,
        disclaimer=report.disclaimer,
        indicator_count=len(report.indicators),
        abnormal_count=sum(1 for indicator in report.indicators if indicator.is_abnormal),
        source=_derive_source(report),
        indicators=[
            IndicatorResultSchema(
                name=indicator.name,
                value=indicator.value,
                unit=indicator.unit,
                analyte_raw=indicator.analyte_raw,
                analyte_canonical=indicator.analyte_canonical,
                section=(analyte_section(indicator.analyte_canonical) if indicator.analyte_canonical else None),
                section_label=(
                    section_label(analyte_section(indicator.analyte_canonical)) if indicator.analyte_canonical else None
                ),
                raw_value=indicator.raw_value,
                raw_unit=indicator.raw_unit,
                canonical_value=indicator.canonical_value,
                canonical_unit=indicator.canonical_unit,
                reference_low=indicator.reference_low,
                reference_high=indicator.reference_high,
                status=indicator.status,
                critical_status=indicator.critical_status,
                rule_type=indicator.rule_type,
                band_id=indicator.band_id,
                upper_operator=indicator.upper_operator,
                evaluation_reason=indicator.evaluation_reason,
                is_abnormal=indicator.is_abnormal,
                is_critical=indicator.is_critical,
                explanation=indicator.explanation,
                review_outcome=indicator.review_outcome or "pending",
                doctor_note=indicator.doctor_note,
                ai_text_snapshot=indicator.ai_text_snapshot,
                reviewed_by_username=(indicator.reviewed_by.username if indicator.reviewed_by is not None else None),
                reviewed_at=indicator.reviewed_at,
                sources=list(indicator.sources or []),
                citations=_structured_explanation_sources(indicator),
                explanation_sources=_structured_explanation_sources(indicator),
            )
            for indicator in report.indicators
        ],
        critical_alerts=list(report.critical_alerts),
        questions=[
            question_to_schema(question)
            for question in sorted(
                report.questions,
                key=lambda item: (item.display_order, item.id),
            )
        ],
        out_of_scope_entries=list(report.out_of_scope_entries),
        doctor_notes=[note_to_schema(note) for note in notes],
        doctor_views=[
            ReportDoctorViewSchema(
                doctor_id=view.doctor_id,
                viewed_at=view.viewed_at,
                doctor_username=(view.doctor.username if view.doctor is not None else None),
            )
            for view in sorted(
                report.doctor_views,
                key=lambda item: item.viewed_at,
            )
        ],
        reviewed_by_doctor=_is_reviewed(report, has_notes=bool(notes)),
        has_doctor_notes=bool(notes),
        verification_status=report.verification_status or "unverified",
        verified_by_username=(report.verified_by.username if report.verified_by is not None else None),
        verified_at=report.verified_at,
    )


# ---------------------------------------------------------------------------
# Câu hỏi gợi ý — bệnh nhân chọn, bác sĩ trả lời
# ---------------------------------------------------------------------------


def select_questions(
    db: Session,
    report: LabReport,
    question_ids: Sequence[int],
) -> list[ReportQuestion]:
    """Đánh dấu những câu bệnh nhân muốn mang đi khám.

    Bộ câu vẫn được lưu nguyên; hàm này chỉ bật/tắt cờ ``is_selected``. Câu được
    chọn chuyển sang ``sent_to_doctor`` để bác sĩ biết bệnh nhân đã chuẩn bị sẵn
    thắc mắc gì — đây là ngữ cảnh bác sĩ cần trước khi viết ghi chú.

    Câu đã được bác sĩ trả lời giữ nguyên ``answered``: bỏ tick không xoá được
    câu trả lời đã có.

    ``question_ids`` chỉ áp dụng cho câu thuộc chính phiếu này. Id của phiếu khác
    bị bỏ qua, nên không có đường nào sửa câu hỏi của bệnh nhân khác.
    """

    wanted = set(question_ids)

    for question in report.questions:
        question.is_selected = question.id in wanted

        if question.status == "answered":
            continue

        question.status = "sent_to_doctor" if question.is_selected else "generated"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(report)
    from src.services.doctor_review_service import refresh_review_flags

    refresh_review_flags(db, report)

    return sorted(
        report.questions,
        key=lambda item: (item.display_order, item.id),
    )


def answer_question(
    db: Session,
    report: LabReport,
    question_id: int,
    *,
    doctor_id: int,
    answer_text: str,
) -> ReportQuestion | None:
    """Bác sĩ trả lời một câu hỏi của phiếu.

    Trả None nếu câu hỏi không thuộc phiếu này — route sẽ đổi thành 404 chứ
    không 403, để không xác nhận id đó có tồn tại ở phiếu nào khác.

    Nội dung trả lời KHÔNG đi qua guardrail: bác sĩ có thẩm quyền nói những điều
    hệ thống bị cấm. Thời điểm do máy chủ đặt.
    """

    target = next(
        (question for question in report.questions if question.id == question_id),
        None,
    )

    if target is None:
        return None

    target.answer_text = answer_text.strip()
    target.answered_by_doctor_id = doctor_id
    target.answered_at = _utcnow()
    target.status = "answered"

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(target)

    return target


# ---------------------------------------------------------------------------
# Ghi chú của bác sĩ + đánh dấu đã xem
# ---------------------------------------------------------------------------


def add_doctor_note(
    db: Session,
    report: LabReport,
    *,
    doctor_id: int,
    note_text: str,
    target_type: str = DoctorNote.TARGET_REPORT,
    target_id: int | None = None,
) -> DoctorNote:
    """Thêm một ghi chú mới. Chỉ thêm, không sửa đè, không xoá.

    Muốn đính chính thì viết ghi chú mới. Hồ sơ y tế cần để lại vết: sửa một
    nhận xét bệnh nhân đã đọc và có thể đã làm theo mà không để lại dấu là thay
    đổi thứ người khác đã hành động dựa trên đó.

    Với ``target_type="report"``, ``target_id`` luôn là id của phiếu, lấy từ URL
    chứ không nhận từ body — nếu không, một bác sĩ có thể ghi chú vào phiếu khác
    bằng cách sửa body.

    Hệ thống không tham gia soạn nội dung: không gợi ý, không điền sẵn mẫu câu,
    không tóm tắt hộ. Một ghi chú do hệ thống soạn rồi bác sĩ bấm lưu sẽ được
    bệnh nhân đọc với niềm tin dành cho người có chuyên môn, trong khi nội dung
    vẫn do máy tạo — tức là lách toàn bộ ranh giới an toàn bằng cách mượn tên
    một con người.
    """

    resolved_target_id = report.id if target_type == DoctorNote.TARGET_REPORT else target_id

    if resolved_target_id is None:
        raise ValueError("target_id là bắt buộc khi target_type không phải report")

    note = DoctorNote(
        doctor_id=doctor_id,
        target_type=target_type,
        target_id=resolved_target_id,
        note_text=note_text.strip(),
    )

    db.add(note)

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    db.refresh(note)

    return note


def mark_report_reviewed(
    db: Session,
    report: LabReport,
    *,
    doctor_id: int,
) -> ReportDoctorView:
    """Bác sĩ chủ động đánh dấu đã xem phiếu.

    Idempotent: bấm nhiều lần không sinh thêm dòng và không đổi thời điểm của
    lần xem đầu, nhờ UNIQUE(report_id, doctor_id). Giữ mốc đầu tiên vì câu hỏi
    bệnh nhân quan tâm là "đã có ai xem chưa", không phải "xem lần cuối lúc nào".
    """

    existing = db.execute(
        select(ReportDoctorView).where(
            ReportDoctorView.report_id == report.id,
            ReportDoctorView.doctor_id == doctor_id,
        )
    ).scalar_one_or_none()

    if existing is not None:
        return existing

    view = ReportDoctorView(report_id=report.id, doctor_id=doctor_id)
    db.add(view)

    try:
        db.commit()
    except IntegrityError:
        # Hai request song song của cùng một bác sĩ: dòng kia đã thắng.
        db.rollback()

        return db.execute(
            select(ReportDoctorView).where(
                ReportDoctorView.report_id == report.id,
                ReportDoctorView.doctor_id == doctor_id,
            )
        ).scalar_one()
    except Exception:
        db.rollback()
        raise

    db.refresh(view)

    return view


def backfill_legacy_canonical_indicators(db: Session) -> dict[str, int]:
    """Backfills missing canonical fields on old report indicators."""
    try:
        repo = ReferenceRepository.from_default_files()
    except ReferenceRepositoryError:
        logger.warning("ReferenceRepository missing/invalid during backfill.")
        return {}

    # Target rows where ANY required canonical field is NULL
    indicators = (
        db.execute(
            select(ReportIndicator).where(
                (ReportIndicator.analyte_canonical.is_(None))
                | (ReportIndicator.canonical_value.is_(None))
                | (ReportIndicator.canonical_unit.is_(None))
            )
        )
        .scalars()
        .all()
    )

    if not indicators:
        return {}

    partial_rows_found = len(indicators)
    partial_rows_completed = 0
    partial_rows_conflicting = 0
    exact_rows = 0
    equivalent_alias_rows = 0
    unsupported_unit_rows = 0

    for ind in indicators:
        raw_name = ind.analyte_raw or ind.name
        raw_value = ind.raw_value if ind.raw_value is not None else ind.value
        raw_unit = ind.raw_unit or ind.unit

        resolved_analyte = repo.resolve_analyte(raw_name)

        # If unsupported analyte, fail closed
        if not resolved_analyte:
            unsupported_unit_rows += 1
            continue

        # Check conflicts if canonical fields are already partially set
        conflict = False
        if ind.analyte_canonical is not None and ind.analyte_canonical != resolved_analyte:
            conflict = True

        # Our invariant: we only populate canonical_value if we can map the unit
        resolved_unit = repo.normalize_unit(raw_unit)

        # We must prove that this unit is supported for this analyte in the reference repository.
        # This prevents silently accepting arbitrary units that don't match our allowed constraints.
        rules = getattr(repo, "_rules_by_analyte", {}).get(resolved_analyte, ())
        supported_units = set()
        for r in rules:
            if repo._norm_text(r.get("reference_type")) in repo.allowed_reference_types:
                u = repo._rule_unit(r)
                if u is not None:
                    supported_units.add(u)

        if resolved_unit not in supported_units:
            unsupported_unit_rows += 1
            continue

        if ind.canonical_unit is not None and ind.canonical_unit != resolved_unit:
            conflict = True

        try:
            numeric_val = float(raw_value) if raw_value is not None else None
        except (TypeError, ValueError):
            numeric_val = None

        if ind.canonical_value is not None and ind.canonical_value != numeric_val:
            conflict = True

        if conflict:
            partial_rows_conflicting += 1
            logger.warning(
                "Conflict during legacy backfill for report %s indicator %s. Skipping.", ind.report_id, ind.id
            )
            continue

        if resolved_unit == raw_unit:
            exact_rows += 1
        else:
            equivalent_alias_rows += 1

        ind.analyte_canonical = resolved_analyte
        ind.canonical_value = numeric_val
        ind.canonical_unit = resolved_unit
        partial_rows_completed += 1

    try:
        db.commit()
    except Exception:
        db.rollback()
        raise

    return {
        "PARTIAL_ROWS_FOUND": partial_rows_found,
        "PARTIAL_ROWS_COMPLETED": partial_rows_completed,
        "PARTIAL_ROWS_CONFLICTING": partial_rows_conflicting,
        "EXACT_ROWS": exact_rows,
        "EQUIVALENT_ALIAS_ROWS": equivalent_alias_rows,
        "UNSUPPORTED_UNIT_ROWS": unsupported_unit_rows,
    }
