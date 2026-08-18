"""Test schema/persistence layer của src/models/db.py — trước đây 0 coverage,
mọi lần verify chỉ là script python -c ad-hoc, không có gì chạy lại trong CI.

Dùng SQLite file riêng (tmp_path) cho từng test, monkeypatch engine/SessionLocal
của module db để không đụng vào data/app.db thật.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.models import db as db_module
from src.models.schemas import LabReportDetailSchema


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    """Engine SQLite riêng cho 1 test, có bật PRAGMA foreign_keys=ON giống
    engine thật — không dùng chung file với data/app.db."""
    db_path = tmp_path / "test_schema.db"
    test_engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})

    @event.listens_for(test_engine, "connect")
    def _enable_fk(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    test_session_local = sessionmaker(bind=test_engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(db_module, "engine", test_engine)
    monkeypatch.setattr(db_module, "SessionLocal", test_session_local)

    yield test_engine, test_session_local

    test_engine.dispose()


EXPECTED_TABLES = {
    "users",
    "lab_reports",
    "report_indicators",
    "report_critical_alerts",
    "indicator_catalog",
    "report_questions",
    "review_flags",
    "doctor_notes",
    "report_doctor_views",
    "out_of_scope_log",
}


def test_init_db_creates_all_8_tables(isolated_db):
    test_engine, _ = isolated_db
    db_module.init_db()

    with test_engine.connect() as conn:
        rows = conn.exec_driver_sql("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    table_names = {row[0] for row in rows}

    assert EXPECTED_TABLES <= table_names


def test_init_db_seeds_two_demo_users(isolated_db):
    _, test_session_local = isolated_db
    db_module.init_db()

    with test_session_local() as session:
        users = session.query(db_module.User).all()

    by_username = {u.username: u.role for u in users}
    assert by_username == {"benhnhan": "patient", "bacsi": "doctor"}


def test_cascade_delete_removes_report_and_children_but_orphans_doctor_note(isolated_db):
    """Xoá patient -> lab_report + report_indicators/report_questions/out_of_scope_log
    biến mất (FK cascade thật, nhờ PRAGMA foreign_keys=ON). doctor_notes của
    1 doctor KHÁC trỏ vào indicator đó KHÔNG bị cascade xoá theo (target_id
    không phải FK thật) -> đúng hành vi orphan đã ghi trong docstring db.py."""
    _, test_session_local = isolated_db
    db_module.init_db()

    with test_session_local() as session:
        patient = session.query(db_module.User).filter_by(username="benhnhan").one()
        doctor = session.query(db_module.User).filter_by(username="bacsi").one()

        report = db_module.LabReport(patient_id=patient.id, test_date=datetime.date(2026, 1, 1))
        indicator = db_module.ReportIndicator(
            name="Kali", value=7.0, unit="mmol/L", status="critical_high"
        )
        report.indicators.append(indicator)
        session.add(report)
        session.flush()  # cần indicator.id trước khi tạo question

        question = db_module.ReportQuestion(
            report=report,
            indicator=indicator,
            question_text="Kali cao có cần tái khám gấp không?",
            priority="critical",
        )
        out_of_scope = db_module.OutOfScopeLog(report=report, raw_indicator_name="Unknown Marker X")
        note = db_module.DoctorNote(
            doctor_id=doctor.id,
            target_type="indicator",
            target_id=indicator.id,
            note_text="Đã trao đổi với bệnh nhân qua điện thoại.",
        )
        session.add_all([question, out_of_scope, note])
        session.commit()

        report_id = report.id
        indicator_id = indicator.id
        question_id = question.id
        out_of_scope_id = out_of_scope.id
        note_id = note.id

        session.delete(patient)
        session.commit()

    with test_session_local() as session:
        assert session.get(db_module.User, patient.id) is None
        assert session.get(db_module.LabReport, report_id) is None
        assert session.get(db_module.ReportIndicator, indicator_id) is None
        assert session.get(db_module.ReportQuestion, question_id) is None
        assert session.get(db_module.OutOfScopeLog, out_of_scope_id) is None

        # Orphan có chủ đích: doctor_notes không có FK thật tới target_id,
        # nên vẫn còn đó dù indicator nó trỏ vào đã bị xoá.
        orphan_note = session.get(db_module.DoctorNote, note_id)
        assert orphan_note is not None
        assert orphan_note.target_id == indicator_id


@pytest.mark.parametrize(
    ("status", "expected_abnormal", "expected_critical"),
    [
        ("normal", False, False),
        ("unknown", False, False),
        ("low", True, False),
        ("high", True, False),
        ("critical_low", True, True),
        ("critical_high", True, True),
    ],
)
def test_is_abnormal_is_critical_derive_from_status(status, expected_abnormal, expected_critical):
    indicator = db_module.ReportIndicator(name="X", value=1.0, unit="u", status=status)

    assert indicator.is_abnormal is expected_abnormal
    assert indicator.is_critical is expected_critical


def test_lab_report_detail_schema_validates_from_orm_row(isolated_db):
    """Bảo vệ contract cho Duy: LabReportDetailSchema phải dựng được trực
    tiếp từ 1 LabReport ORM row (from_attributes), kèm indicators/critical_alerts
    /questions/out_of_scope_entries lồng nhau, không cần map tay từng field."""
    _, test_session_local = isolated_db
    db_module.init_db()

    with test_session_local() as session:
        patient = session.query(db_module.User).filter_by(username="benhnhan").one()

        report = db_module.LabReport(
            patient_id=patient.id,
            test_date=datetime.date(2026, 3, 5),
            summary="Tóm tắt test",
        )
        report.indicators.append(
            db_module.ReportIndicator(name="Kali", value=7.0, unit="mmol/L", status="critical_high")
        )
        report.critical_alerts.append(
            db_module.ReportCriticalAlert(
                indicator_name="Kali", value=7.0, unit="mmol/L", message="Nguy kịch"
            )
        )
        session.add(report)
        session.commit()
        session.refresh(report)

        detail = LabReportDetailSchema.model_validate(report)

    assert detail.summary == "Tóm tắt test"
    assert len(detail.indicators) == 1
    assert detail.indicators[0].is_critical is True
    assert detail.indicators[0].is_abnormal is True
    assert len(detail.critical_alerts) == 1
    assert detail.critical_alerts[0].message == "Nguy kịch"
