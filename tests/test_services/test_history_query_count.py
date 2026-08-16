"""Đếm truy vấn SQL của màn lịch sử.

Từ lúc DB chuyển sang Postgres đặt ngoài mạng, mỗi truy vấn phụ là một lượt round
trip thật. Một hàm map dữ liệu tự bắn truy vấn cho từng dòng sẽ làm màn danh sách
phình theo số phiếu — chuyện vô hình khi còn dùng SQLite trên cùng đĩa.

Test này chốt: số truy vấn của màn danh sách KHÔNG tăng theo số phiếu.
"""

from datetime import date

import pytest
from sqlalchemy import event

from src.models.db import DoctorNote, LabReport, ReportIndicator, User
from src.services import history_repository as repo


@pytest.fixture
def count_queries(test_db):
    """Đếm câu SELECT thật gửi xuống DB trong một khối lệnh."""

    class Counter:
        def __init__(self):
            self.statements: list[str] = []

        def __enter__(self):
            event.listen(test_db.engine, "before_cursor_execute", self._record)
            return self

        def __exit__(self, *_exc):
            event.remove(test_db.engine, "before_cursor_execute", self._record)
            return False

        def _record(self, _conn, _cursor, statement, *_args):
            if statement.lstrip().upper().startswith("SELECT"):
                self.statements.append(statement)

        @property
        def count(self) -> int:
            return len(self.statements)

    return Counter


def seed_reports(db, patient_id: int, how_many: int, *, notes_on: int = 0) -> list[int]:
    """Tạo `how_many` phiếu, trong đó `notes_on` phiếu đầu có ghi chú."""

    ids: list[int] = []

    for index in range(how_many):
        report = LabReport(
            patient_id=patient_id,
            test_date=date(2026, 8, 1),
            language="vi",
            summary="",
            has_critical_values=False,
            guardrail_passed=True,
            disclaimer="",
            indicators=[
                ReportIndicator(
                    name="Kali",
                    value=5.5,
                    unit="mmol/L",
                    status="high",
                    explanation="",
                    sources=[],
                )
            ],
        )
        db.add(report)
        db.commit()
        db.refresh(report)
        ids.append(report.id)

    for report_id in ids[:notes_on]:
        db.add(
            DoctorNote(
                doctor_id=patient_id,
                target_type=DoctorNote.TARGET_REPORT,
                target_id=report_id,
                note_text="ghi chu",
            )
        )
    db.commit()

    return ids


def test_history_list_query_count_does_not_grow_with_report_count(test_db, count_queries):
    """3 phiếu và 12 phiếu phải dùng cùng một số truy vấn.

    Trước khi gộp, `_to_summary()` gọi `_notes_for_report()` hai lần cho mỗi phiếu
    nên 12 phiếu bắn thêm 24 truy vấn so với 3 phiếu.
    """

    with test_db.session() as db:
        patient_id = db.query(User).filter(User.username == "benhnhan").one().id

        seed_reports(db, patient_id, 3, notes_on=2)

        with count_queries() as small:
            total, items = repo.list_reports(
                db,
                patient_id=patient_id,
                from_date=None,
                to_date=None,
                limit=50,
                offset=0,
            )
        assert total == 3
        assert [item.has_doctor_notes for item in items].count(True) == 2

        seed_reports(db, patient_id, 9)

        with count_queries() as large:
            total, items = repo.list_reports(
                db,
                patient_id=patient_id,
                from_date=None,
                to_date=None,
                limit=50,
                offset=0,
            )
        assert total == 12

    assert large.count == small.count, (
        f"số truy vấn tăng theo số phiếu: {small.count} -> {large.count}. "
        "Có hàm map đang tự truy vấn cho từng dòng."
    )


def test_report_ids_with_notes_uses_a_single_query(test_db, count_queries):
    with test_db.session() as db:
        patient_id = db.query(User).filter(User.username == "benhnhan").one().id
        ids = seed_reports(db, patient_id, 5, notes_on=3)

        with count_queries() as counter:
            found = repo._report_ids_with_notes(db, ids)

    assert found == set(ids[:3])
    assert counter.count == 1


def test_detail_loads_notes_once_not_three_times(test_db, count_queries):
    """`to_detail()` đọc ghi chú một lần rồi dùng lại cho cả ba field."""

    with test_db.session() as db:
        patient_id = db.query(User).filter(User.username == "benhnhan").one().id
        report_id = seed_reports(db, patient_id, 1, notes_on=1)[0]

        report = repo.get_report(db, report_id)

        with count_queries() as counter:
            detail = repo.to_detail(report)

    assert len(detail.doctor_notes) == 1
    assert detail.has_doctor_notes is True
    assert detail.reviewed_by_doctor is True
    # Đúng một truy vấn cho bảng doctor_notes; các quan hệ khác đã eager-load.
    assert counter.count == 1, counter.statements
