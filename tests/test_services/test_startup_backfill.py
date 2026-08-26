"""START-01 through START-08: Regression tests for backfill_review_flags refactor.

Tests verify:
- START-01  fresh DB + demo seed  → backfill returns 0 (already consistent)
- START-02  legacy report, NO flags → backfill repairs it
- START-03  legacy report WITH stale/wrong flags → backfill repairs (not skipped)
- START-04  already-correct report → no destructive write
- START-05  multiple stale reports → all repaired, batch commit
- START-06  exception → transaction rolls back
- START-07  normal refresh_review_flags unchanged behavior
- START-08  verification_status / priority_score / queued_at semantics preserved
"""
from __future__ import annotations

from datetime import date, datetime
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from src.models.db import (
    LabReport,
    ReportIndicator,
    ReportQuestion,
    ReviewFlag,
    User,
)
from src.services.doctor_review_service import (
    FLAG_CRITICAL,
    FLAG_LOW_OCR,
    FLAG_PATIENT_QUESTIONS,
    VERIFICATION_PENDING,
    VERIFICATION_UNVERIFIED,
    _is_review_state_consistent,
    backfill_review_flags,
    refresh_review_flags,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_session(test_db) -> Session:
    with test_db.session() as s:
        yield s


def _patient_id(db: Session) -> int:
    """Return the id of the seeded 'benhnhan' demo patient."""
    return db.execute(
        select(User.id).where(User.username == "benhnhan")
    ).scalar_one()


def _make_report(
    db: Session,
    *,
    patient_id: int,
    test_date: str = "2026-01-01",
    has_critical: bool = False,
    has_ocr_low: bool = False,
    has_selected_question: bool = False,
    verification_status: str = VERIFICATION_UNVERIFIED,
    priority_score: float = 0.0,
    queued_at: datetime | None = None,
    findings_total: int | None = None,
    findings_reviewed: int = 0,
) -> LabReport:
    """Create a minimal LabReport with the requested indicator/question config."""
    indicator_status = "critical_high" if has_critical else "normal"
    critical_status = "critical_high" if has_critical else None

    indicator = ReportIndicator(
        name="Potassium",
        value=7.0 if has_critical else 4.0,
        unit="mmol/L",
        status=indicator_status,
        critical_status=critical_status,
        reference_low=3.5,
        reference_high=5.3,
        ocr_confidence=0.60 if has_ocr_low else None,
    )
    if has_selected_question:
        question = ReportQuestion(
            question_text="Test question?",
            priority="abnormal",
            display_order=0,
            status="sent_to_doctor",
            is_selected=True,
        )
    else:
        question = None

    report = LabReport(
        patient_id=patient_id,
        test_date=date.fromisoformat(test_date),
        has_critical_values=has_critical,
        guardrail_passed=True,
        summary="",
        disclaimer="",
        verification_status=verification_status,
        priority_score=priority_score,
        queued_at=queued_at,
        findings_total=findings_total if findings_total is not None else 1,
        findings_reviewed=findings_reviewed,
        indicators=[indicator],
        questions=[question] if question else [],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


# ---------------------------------------------------------------------------
# START-01: fresh DB + seeded demo reports → backfill returns 0
# ---------------------------------------------------------------------------


def test_start_01_fresh_db_no_work(db_session: Session):
    """After seed the DB has no reports, so backfill should return 0."""
    # The autouse conftest fixture seeds demo users but NOT reports.
    # No lab reports → nothing to process.
    result = backfill_review_flags(db_session)
    assert result == 0, "No reports to backfill on a fresh DB"


def test_start_01_already_consistent_report(db_session: Session):
    """A report that is already fully consistent must not be counted as changed."""
    pid = _patient_id(db_session)
    report = _make_report(db_session, patient_id=pid, has_critical=True)

    # Apply flags via the normal refresh path first (sets consistent state)
    refresh_review_flags(db_session, report)
    db_session.refresh(report)

    # Backfill should find the report consistent and skip it
    result = backfill_review_flags(db_session)
    assert result == 0, "Consistent report must be skipped"


# ---------------------------------------------------------------------------
# START-02: legacy report with NO flags → backfill repairs it
# ---------------------------------------------------------------------------


def test_start_02_no_flags_repaired(db_session: Session):
    """Unverified report with zero ReviewFlag rows must be repaired."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        verification_status=VERIFICATION_UNVERIFIED,
        queued_at=None,
    )
    # Explicitly ensure no flags exist (matches legacy state pre-migration)
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()

    changed = backfill_review_flags(db_session)

    assert changed == 1
    db_session.refresh(report)
    assert report.verification_status == VERIFICATION_PENDING
    flag_codes = {f.code for f in report.review_flags}
    assert FLAG_CRITICAL in flag_codes
    assert report.queued_at is not None


# ---------------------------------------------------------------------------
# START-03: legacy report WITH stale/wrong flags → repaired (not skipped)
# ---------------------------------------------------------------------------


def test_start_03_stale_flags_repaired_not_skipped(db_session: Session):
    """A report with at least one ReviewFlag but inconsistent state must be repaired.

    This test specifically validates that _is_review_state_consistent does NOT
    treat 'has at least one flag' as sufficient proof of consistency.
    """
    pid = _patient_id(db_session)
    # Report whose indicator is critical but we'll manually inject a WRONG flag
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        verification_status=VERIFICATION_UNVERIFIED,
        priority_score=0.0,  # wrong — should be 50.0 for CRITICAL_VALUE
    )
    # Inject a stale/wrong flag (wrong code for the indicator state)
    wrong_flag = ReviewFlag(
        report_id=report.id,
        finding_id=report.indicators[0].id,
        code=FLAG_LOW_OCR,       # wrong code — should be FLAG_CRITICAL
        severity="medium",
        detail="stale placeholder",
    )
    db_session.add(wrong_flag)
    db_session.commit()

    changed = backfill_review_flags(db_session)

    assert changed == 1, "Stale-flag report must be repaired"
    db_session.refresh(report)
    flag_codes = {f.code for f in report.review_flags}
    assert FLAG_CRITICAL in flag_codes, "CRITICAL_VALUE flag must be present after repair"
    assert FLAG_LOW_OCR not in flag_codes, "Wrong stale flag must be replaced"
    assert report.verification_status == VERIFICATION_PENDING
    assert report.priority_score == 50.0


def test_start_03_wrong_verification_status_repaired(db_session: Session):
    """Report with correct flags but wrong verification_status must be repaired."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=False,
        verification_status=VERIFICATION_PENDING,  # wrong — should be UNVERIFIED
        priority_score=0.0,
    )
    # No critical/ocr/question indicators → no flags → should be UNVERIFIED
    # But we set it to PENDING above.

    changed = backfill_review_flags(db_session)

    assert changed == 1
    db_session.refresh(report)
    assert report.verification_status == VERIFICATION_UNVERIFIED


# ---------------------------------------------------------------------------
# START-04: already-correct report → _is_review_state_consistent returns True
# ---------------------------------------------------------------------------


def test_start_04_consistent_report_not_mutated(db_session: Session):
    """Consistent report must not trigger any DB write."""
    pid = _patient_id(db_session)
    report = _make_report(db_session, patient_id=pid, has_critical=True)
    refresh_review_flags(db_session, report)
    db_session.refresh(report)

    # Capture current DB state
    original_flag_ids = {f.id for f in report.review_flags}
    original_queued_at = report.queued_at
    original_vs = report.verification_status
    original_priority = report.priority_score

    assert _is_review_state_consistent(report), "Pre-condition: report must be consistent"

    backfill_review_flags(db_session)
    db_session.refresh(report)

    # State must be identical — same flag row IDs (no delete/reinsert)
    current_flag_ids = {f.id for f in report.review_flags}
    assert current_flag_ids == original_flag_ids, "Flag rows must not be recreated"
    assert report.queued_at == original_queued_at
    assert report.verification_status == original_vs
    assert report.priority_score == original_priority


# ---------------------------------------------------------------------------
# START-05: multiple stale reports → all repaired, batch commit
# ---------------------------------------------------------------------------


def test_start_05_multiple_stale_reports_batch_commit(db_session: Session):
    """Multiple stale reports are all repaired in a single commit."""
    pid = _patient_id(db_session)

    reports = []
    for _ in range(3):
        r = _make_report(
            db_session,
            patient_id=pid,
            has_critical=True,
            verification_status=VERIFICATION_UNVERIFIED,
            priority_score=0.0,
        )
        # Strip flags to simulate legacy state
        for flag in list(r.review_flags):
            db_session.delete(flag)
        reports.append(r)
    db_session.commit()

    commit_count = 0
    original_commit = db_session.commit

    def counting_commit():
        nonlocal commit_count
        commit_count += 1
        return original_commit()

    db_session.commit = counting_commit
    try:
        changed = backfill_review_flags(db_session)
    finally:
        db_session.commit = original_commit

    assert changed == 3, "All 3 stale reports must be repaired"
    assert commit_count == 1, "Exactly one commit must be issued for the whole batch"

    for r in reports:
        db_session.refresh(r)
        assert r.verification_status == VERIFICATION_PENDING
        assert any(f.code == FLAG_CRITICAL for f in r.review_flags)


# ---------------------------------------------------------------------------
# START-06: exception inside loop → transaction rolls back
# ---------------------------------------------------------------------------


def test_start_06_exception_rolls_back(db_session: Session):
    """If an error occurs during backfill, the transaction must be rolled back."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        verification_status=VERIFICATION_UNVERIFIED,
    )
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()
    original_vs = report.verification_status

    # Inject a failure inside _apply_review_flags_no_commit
    with patch(
        "src.services.doctor_review_service._apply_review_flags_no_commit",
        side_effect=RuntimeError("simulated backfill error"),
    ):
        with pytest.raises(RuntimeError, match="simulated backfill error"):
            backfill_review_flags(db_session)

    db_session.expire(report)
    db_session.refresh(report)
    # DB state must be unchanged after rollback
    assert report.verification_status == original_vs
    assert not report.review_flags, "No flags must be persisted after rollback"


# ---------------------------------------------------------------------------
# START-07: normal refresh_review_flags unchanged behavior
# ---------------------------------------------------------------------------


def test_start_07_refresh_review_flags_unchanged_behavior(db_session: Session):
    """refresh_review_flags must commit immediately and return the refreshed report."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        verification_status=VERIFICATION_UNVERIFIED,
    )
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()

    returned = refresh_review_flags(db_session, report)

    # Must return the LabReport object (same id)
    assert returned.id == report.id
    # State must be applied immediately
    assert returned.verification_status == VERIFICATION_PENDING
    flag_codes = {f.code for f in returned.review_flags}
    assert FLAG_CRITICAL in flag_codes
    assert returned.queued_at is not None
    assert returned.priority_score == 50.0


def test_start_07_refresh_ocr_and_question_flags(db_session: Session):
    """refresh_review_flags generates LOW_OCR and PATIENT_HAS_QUESTIONS flags."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_ocr_low=True,
        has_selected_question=True,
        has_critical=False,
        verification_status=VERIFICATION_UNVERIFIED,
    )

    refresh_review_flags(db_session, report)
    db_session.refresh(report)

    flag_codes = {f.code for f in report.review_flags}
    assert FLAG_LOW_OCR in flag_codes
    assert FLAG_PATIENT_QUESTIONS in flag_codes
    assert report.verification_status == VERIFICATION_PENDING


# ---------------------------------------------------------------------------
# START-08: verification_status / priority_score / queued_at semantics
# ---------------------------------------------------------------------------


def test_start_08_verified_report_never_touched(db_session: Session):
    """Reports with verification_status == 'verified' must never be touched."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        verification_status="verified",
    )
    # Remove flags to create an 'inconsistent-looking' state
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()

    changed = backfill_review_flags(db_session)

    assert changed == 0, "Verified report must never be processed by backfill"
    db_session.refresh(report)
    assert report.verification_status == "verified"
    assert not report.review_flags


def test_start_08_priority_score_correct_after_backfill(db_session: Session):
    """priority_score must equal sum of PRIORITY_WEIGHTS for active flags."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        priority_score=0.0,  # stale
        verification_status=VERIFICATION_UNVERIFIED,
    )
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()

    backfill_review_flags(db_session)
    db_session.refresh(report)

    # CRITICAL_VALUE weight is 50.0
    assert report.priority_score == 50.0


def test_start_08_queued_at_set_when_flags_appear(db_session: Session):
    """queued_at must be set to a non-None datetime when flags are created."""
    pid = _patient_id(db_session)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=True,
        queued_at=None,
        verification_status=VERIFICATION_UNVERIFIED,
    )
    for flag in list(report.review_flags):
        db_session.delete(flag)
    db_session.commit()

    backfill_review_flags(db_session)
    db_session.refresh(report)

    assert report.queued_at is not None


def test_start_08_queued_at_cleared_when_no_flags(db_session: Session):
    """queued_at must be cleared when a report no longer warrants any flags."""
    from datetime import UTC, datetime

    pid = _patient_id(db_session)
    # Normal (non-critical, no OCR, no questions) report but queued_at is set (stale)
    stale_queued_at = datetime(2026, 1, 1, tzinfo=UTC)
    report = _make_report(
        db_session,
        patient_id=pid,
        has_critical=False,
        verification_status=VERIFICATION_PENDING,  # stale
        queued_at=stale_queued_at,
        priority_score=50.0,  # stale
    )
    # Inject a stale flag (wrong — no indicator warrants it)
    stale_flag = ReviewFlag(
        report_id=report.id,
        finding_id=None,
        code=FLAG_PATIENT_QUESTIONS,
        severity="medium",
        detail="stale",
    )
    db_session.add(stale_flag)
    db_session.commit()

    backfill_review_flags(db_session)
    db_session.refresh(report)

    assert report.queued_at is None
    assert report.verification_status == VERIFICATION_UNVERIFIED
    assert report.priority_score == 0.0
    assert not report.review_flags


def test_start_08_is_consistent_helper_detects_stale(db_session: Session):
    """_is_review_state_consistent must return False for each stale dimension."""
    pid = _patient_id(db_session)
    report = _make_report(db_session, patient_id=pid, has_critical=True)
    refresh_review_flags(db_session, report)
    db_session.refresh(report)

    assert _is_review_state_consistent(report), "Baseline must be consistent"

    # Tamper: wrong priority_score
    report.priority_score = 0.0
    assert not _is_review_state_consistent(report), "Wrong priority_score must be detected"
    report.priority_score = 50.0  # restore

    # Tamper: wrong verification_status
    report.verification_status = VERIFICATION_UNVERIFIED
    assert not _is_review_state_consistent(report), "Wrong verification_status must be detected"
    report.verification_status = VERIFICATION_PENDING  # restore

    # Tamper: missing queued_at
    original_queued_at = report.queued_at
    report.queued_at = None
    assert not _is_review_state_consistent(report), "Missing queued_at must be detected"
    report.queued_at = original_queued_at  # restore

    # Tamper: wrong findings_total
    report.findings_total = 99
    assert not _is_review_state_consistent(report), "Wrong findings_total must be detected"
    report.findings_total = 1  # restore

    # After all restores: should be consistent again
    assert _is_review_state_consistent(report)
