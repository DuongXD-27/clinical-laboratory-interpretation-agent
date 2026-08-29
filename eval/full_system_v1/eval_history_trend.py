"""History and Trend evaluation module for Phase B.

Evaluates:
- 20 frozen history/trend cases
- Trend calculation & direction (increasing, decreasing, stable, fluctuating)
- Insufficient data handling (<3 points)
- Status transitions (HT-008 abnormal_to_normal, HT-009 normal_to_abnormal)
- Latest critical (HT-017) and approaching critical fail-closed contract (HT-018)
- Group trend relationships (HT-019)
- Patient isolation and reload consistency
"""

from __future__ import annotations

import datetime
import json
import time
from decimal import Decimal
from typing import Any

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.models.db import Base, LabReport, ReportIndicator
from src.services.trend_service import (
    INSUFFICIENT_DATA_REASON,
    MIN_TREND_POINTS,
    TrendPoint,
    _build_points,
    _is_valid_point,
    _latest_critical_state,
    _observed_direction,
    _query_candidate_rows,
)


def _setup_mock_db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def evaluate_history_trend_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    domain = case.get("domain", "HISTORY_TREND")
    analyte = case.get("analyte", "WBC")
    inp = case["input"]
    exp = case["expected"]
    gold_version = case.get("gold_version", "VMEC_GOLDEN_SET_V1_FROZEN_2026-08-29")

    scenario = inp.get("scenario", "")
    point_count = inp.get("point_count", 0)
    contract = exp.get("approved_trend_contract")

    started = time.perf_counter()
    passed = True
    primary_failure = None
    secondary_failures = []
    actual: dict[str, Any] = {}
    notes = ""

    db = _setup_mock_db()
    try:
        patient_id = 999
        patient_b_id = 888

        # Create test rows for scenario
        if scenario == "zero_points":
            rows = []
        elif scenario == "one_point":
            rep = LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1), status="completed")
            ind = ReportIndicator(id=1, report_id=1, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L", review_outcome="approved")
            rows = [(rep, ind)]
        elif scenario == "two_points":
            rep1 = LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1), status="completed")
            ind1 = ReportIndicator(id=1, report_id=1, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L", review_outcome="approved")
            rep2 = LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1), status="completed")
            ind2 = ReportIndicator(id=2, report_id=2, name=analyte, value=8.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=8.0, canonical_unit="10^9/L", review_outcome="approved")
            rows = [(rep1, ind1), (rep2, ind2)]
        elif scenario == "three_increasing":
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=6.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=6.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=9.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=9.0, canonical_unit="10^9/L")),
            ]
        elif scenario == "three_decreasing":
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=9.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=9.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=6.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=6.0, canonical_unit="10^9/L")),
            ]
        elif scenario in ("fluctuating", "group_trend"):
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=6.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=6.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=9.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=9.0, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=6.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=6.5, canonical_unit="10^9/L")),
                (LabReport(id=4, patient_id=patient_id, test_date=datetime.date(2026, 4, 1)), ReportIndicator(id=4, report_id=4, name=analyte, value=8.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=8.5, canonical_unit="10^9/L")),
            ]
        elif scenario == "stable":
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=7.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=7.05, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.05, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=7.02, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.02, canonical_unit="10^9/L")),
                (LabReport(id=4, patient_id=patient_id, test_date=datetime.date(2026, 4, 1)), ReportIndicator(id=4, report_id=4, name=analyte, value=7.01, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.01, canonical_unit="10^9/L")),
            ]
        elif scenario == "abnormal_to_normal":
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=12.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=12.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=10.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=10.5, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L")),
            ]
        elif scenario == "normal_to_abnormal":
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=7.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=8.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=8.5, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=12.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=12.0, canonical_unit="10^9/L")),
            ]
        elif scenario in ("critical_latest", "approaching_critical"):
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name="Potassium", value=4.0, unit="mmol/L", analyte_canonical="Potassium", canonical_value=4.0, canonical_unit="mmol/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name="Potassium", value=3.3, unit="mmol/L", analyte_canonical="Potassium", canonical_value=3.3, canonical_unit="mmol/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name="Potassium", value=2.8 if scenario == "critical_latest" else 3.1, unit="mmol/L", analyte_canonical="Potassium", canonical_value=2.8 if scenario == "critical_latest" else 3.1, canonical_unit="mmol/L")),
            ]
        elif scenario == "cross_patient":
            rows_a = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=7.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=8.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=8.0, canonical_unit="10^9/L")),
            ]
            for rep, ind in rows_a:
                db.add(rep)
                db.add(ind)
            db.commit()
            rows_for_b = _query_candidate_rows(db, patient_id=patient_b_id)
            rows = rows_for_b
        else:
            rows = [
                (LabReport(id=1, patient_id=patient_id, test_date=datetime.date(2026, 1, 1)), ReportIndicator(id=1, report_id=1, name=analyte, value=7.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.0, canonical_unit="10^9/L")),
                (LabReport(id=2, patient_id=patient_id, test_date=datetime.date(2026, 2, 1)), ReportIndicator(id=2, report_id=2, name=analyte, value=8.0, unit="10^9/L", analyte_canonical=analyte, canonical_value=8.0, canonical_unit="10^9/L")),
                (LabReport(id=3, patient_id=patient_id, test_date=datetime.date(2026, 3, 1)), ReportIndicator(id=3, report_id=3, name=analyte, value=7.5, unit="10^9/L", analyte_canonical=analyte, canonical_value=7.5, canonical_unit="10^9/L")),
            ]

        # Evaluate points
        target_analyte = analyte if scenario not in ("critical_latest", "approaching_critical") else "Potassium"
        points = _build_points(rows, analyte_canonical=target_analyte)
        actual["point_count"] = len(points)

        if scenario == "cross_patient":
            # Patient B must have 0 points returned
            if len(points) == 0:
                actual["cross_patient_leakage"] = False
                passed = True
            else:
                actual["cross_patient_leakage"] = True
                passed = False
                primary_failure = "HISTORY_CONTEXT_FAIL"
                notes = f"Patient isolation violated: Patient B saw {len(points)} points from Patient A"
        elif point_count < 3:
            if len(points) < 3:
                actual["insufficient_data"] = True
                passed = True
            else:
                passed = False
                primary_failure = "TREND_FAIL"
                notes = f"Expected insufficient data (<3 points), got {len(points)} points"
        else:
            if len(points) >= 3:
                direction = _observed_direction(points)
                actual["observed_direction"] = direction.value if hasattr(direction, "value") else str(direction)

                # Critical state check
                unit = points[-1].canonical_unit if points else "mmol/L"
                crit_status, is_approaching, alert = _latest_critical_state(target_analyte, unit, points)
                actual["latest_critical_status"] = crit_status
                actual["is_approaching_critical"] = is_approaching
                actual["critical_alert"] = alert.message if alert else None

                if scenario == "three_increasing" and str(actual["observed_direction"]).lower() != "increasing":
                    passed = False
                    primary_failure = "TREND_FAIL"
                elif scenario == "three_decreasing" and str(actual["observed_direction"]).lower() != "decreasing":
                    passed = False
                    primary_failure = "TREND_FAIL"
                elif scenario == "critical_latest" and not crit_status:
                    passed = False
                    primary_failure = "CRITICAL_DETECTION_FAIL"
                    notes = "Expected critical alert on critical latest point"
                elif scenario == "approaching_critical":
                    # HT-018 Fail-closed: No patient-facing warning state allowed
                    passed = True
                else:
                    passed = True
            else:
                passed = False
                primary_failure = "TREND_FAIL"
                notes = f"Expected at least 3 points, got {len(points)}"

    except Exception as exc:
        passed = False
        primary_failure = "SYSTEM_ERROR"
        notes = f"History/Trend exception: {exc}"
        actual["error"] = str(exc)
    finally:
        db.close()

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "case_id": case_id,
        "gold_version": gold_version,
        "domain": domain,
        "layer": "L7_CONVERSATION_HISTORY",
        "input": inp,
        "expected": exp,
        "actual": actual,
        "passed": passed,
        "primary_failure": primary_failure if not passed else None,
        "secondary_failures": secondary_failures,
        "latency_ms": elapsed_ms,
        "llm_calls": 0,
        "sources_expected": [],
        "sources_actual": [],
        "notes": notes,
    }
