from datetime import date

import pytest
from sqlalchemy.orm import Session

from src.models.db import LabReport, ReportIndicator
from src.services.history_repository import backfill_legacy_canonical_indicators


@pytest.fixture
def db_session(test_db) -> Session:
    with test_db.session() as s:
        yield s


@pytest.fixture
def clean_report(db_session: Session) -> LabReport:
    """Creates a basic report for testing."""
    report = LabReport(
        patient_id=1,
        test_date=date(2026, 8, 1),
        status="NORMAL",
    )
    db_session.add(report)
    db_session.commit()
    db_session.refresh(report)
    return report


def test_backfill_resolves_wbc(db_session: Session, clean_report: LabReport):
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="Bạch cầu (WBC)",
        value=6.5,
        unit="10^9/L",
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)

    db_session.refresh(ind)
    assert ind.analyte_canonical == "WBC"
    assert ind.canonical_value == 6.5
    assert ind.canonical_unit == "10^9/L"
    assert metrics.get("PARTIAL_ROWS_COMPLETED") == 1
    assert metrics.get("EXACT_ROWS") == 1


def test_backfill_equivalent_unit(db_session: Session, clean_report: LabReport):
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="Creatinine",
        value=75.0,
        unit="umol/l",  # Note lowercase l
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)

    db_session.refresh(ind)
    assert ind.analyte_canonical == "Creatinine"
    assert ind.canonical_value == 75.0
    assert ind.canonical_unit == "umol/L"
    assert metrics.get("EQUIVALENT_ALIAS_ROWS") == 1


def test_backfill_unsupported_analyte(db_session: Session, clean_report: LabReport):
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="Some Unknown Analyte",
        value=1.0,
        unit="mg/L",
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)

    db_session.refresh(ind)
    assert ind.analyte_canonical is None
    assert ind.canonical_value is None
    assert metrics.get("UNSUPPORTED_UNIT_ROWS") == 1


def test_backfill_unsupported_unit(db_session: Session, clean_report: LabReport):
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="WBC",
        value=1.0,
        unit="UNKNOWN_UNIT",
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)

    db_session.refresh(ind)
    assert ind.analyte_canonical is None
    assert ind.canonical_value is None
    assert metrics.get("UNSUPPORTED_UNIT_ROWS") == 1


def test_backfill_idempotent(db_session: Session, clean_report: LabReport):
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="WBC",
        value=6.5,
        unit="10^9/L",
    )
    db_session.add(ind)
    db_session.commit()

    metrics1 = backfill_legacy_canonical_indicators(db_session)
    assert metrics1.get("PARTIAL_ROWS_COMPLETED") == 1

    metrics2 = backfill_legacy_canonical_indicators(db_session)
    assert metrics2 == {}  # Returns empty dict if no partial rows found


def test_backfill_conflict(db_session: Session, clean_report: LabReport):
    # Has a name conflict
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="WBC",
        value=6.5,
        unit="10^9/L",
        analyte_canonical="Creatinine",  # conflicting
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)
    db_session.refresh(ind)
    assert ind.analyte_canonical == "Creatinine"  # Unchanged
    assert ind.canonical_value is None
    assert metrics.get("PARTIAL_ROWS_CONFLICTING") == 1


def test_backfill_partial_null_safe(db_session: Session, clean_report: LabReport):
    # Only canonical_value missing
    ind = ReportIndicator(
        report_id=clean_report.id,
        name="WBC",
        value=6.5,
        unit="10^9/L",
        analyte_canonical="WBC",
        canonical_unit="10^9/L",
    )
    db_session.add(ind)
    db_session.commit()

    metrics = backfill_legacy_canonical_indicators(db_session)
    db_session.refresh(ind)
    assert ind.canonical_value == 6.5
    assert metrics.get("PARTIAL_ROWS_COMPLETED") == 1
