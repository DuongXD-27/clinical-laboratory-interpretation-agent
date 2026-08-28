from __future__ import annotations

import ast
from datetime import date
from pathlib import Path

import pytest

from src.api import orchestrator_routes
from src.api.deps import CurrentUser
from src.models.db import ROLE_DOCTOR, ROLE_PATIENT, User
from src.models.orchestrator_schemas import (
    AnalysisDataPayload,
    DoctorQuestionsPayload,
    HistorySummaryPayload,
    ReasonCode,
    TrendDataPayload,
)
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, CriticalAlertSchema, IndicatorResultSchema
from src.orchestrator import wrappers
from src.orchestrator.errors import OrchestratorWrapperError
from src.services import history_repository
from src.services.auth import ROLE_GUEST
from src.services.trend_service import MIN_TREND_POINTS

ORCHESTRATOR_ROOT = Path("src/orchestrator")


class QuerySpyDb:
    def __init__(self) -> None:
        self.calls = 0

    def __getattr__(self, name):
        def _counted(*args, **kwargs):
            self.calls += 1
            raise AssertionError(f"unexpected DB call: {name}")

        return _counted


class BrokenDb:
    def scalar(self, *args, **kwargs):
        raise RuntimeError("database unavailable")


def _raise_reason(callable_obj, *args, **kwargs) -> OrchestratorWrapperError:
    with pytest.raises(OrchestratorWrapperError) as exc_info:
        callable_obj(*args, **kwargs)
    return exc_info.value


def _create_patient(test_db, username: str) -> int:
    with test_db.session() as db:
        user = User(username=username, password_hash="hash", role=ROLE_PATIENT)
        db.add(user)
        db.commit()
        db.refresh(user)
        return user.id


def _current_patient(name: str, key: int) -> CurrentUser:
    return CurrentUser(name, ROLE_PATIENT, user_id=key)


def _doctor() -> CurrentUser:
    return CurrentUser("doctor", ROLE_DOCTOR, user_id=999_001)


def _guest() -> CurrentUser:
    return CurrentUser("guest", ROLE_GUEST, session_id="guest-session")


def _request(test_date: date, rows: list[dict]) -> AnalyzeRequest:
    return AnalyzeRequest(
        patient_age=35,
        patient_gender="male",
        test_date=test_date,
        language="vi",
        indicators=[
            {
                "name": row["name"],
                "value": row["value"],
                "unit": row["unit"],
            }
            for row in rows
        ],
    )


def _response(rows: list[dict], *, summary: str = "") -> AnalyzeResponse:
    indicators = []
    for row in rows:
        status = row.get("status", "normal")
        indicators.append(
            IndicatorResultSchema(
                name=row["name"],
                value=row["value"],
                unit=row["unit"],
                analyte_canonical=row.get("analyte_canonical", row["name"]),
                canonical_value=row.get("canonical_value", row["value"]),
                canonical_unit=row.get("canonical_unit", row["unit"]),
                reference_low=row.get("reference_low"),
                reference_high=row.get("reference_high"),
                status=status,
                critical_status=row.get("critical_status"),
                is_abnormal=status in {"low", "high", "critical_low", "critical_high"},
                is_critical=status in {"critical_low", "critical_high"} or bool(row.get("critical_status")),
                explanation=row.get("explanation", ""),
                sources=row.get("sources", []),
            )
        )
    critical_alerts = [
        CriticalAlertSchema(
            indicator_name=row["name"],
            value=row["value"],
            unit=row["unit"],
            message="critical",
        )
        for row in rows
        if row.get("critical_status")
    ]
    return AnalyzeResponse(
        indicators=indicators,
        critical_alerts=critical_alerts,
        has_critical_values=bool(critical_alerts),
        summary=summary,
        guardrail_passed=True,
    )


def _save_report(test_db, owner_name: str, test_date: date, rows: list[dict], *, summary: str = "") -> int:
    with test_db.session() as db:
        owner = db.query(User).filter(User.username == owner_name).one()
        report = history_repository.save_report(
            db,
            patient_id=owner.id,
            request=_request(test_date, rows),
            response=_response(rows, summary=summary),
        )
        return report.id


def _seed_ldl_series(test_db, owner_name: str, *, count: int, start_day: int = 1) -> list[int]:
    report_refs = []
    for offset in range(count):
        report_refs.append(
            _save_report(
                test_db,
                owner_name,
                date(2026, 8, start_day + offset),
                [
                    {
                        "name": "LDL-C",
                        "value": 2.1 + offset / 10,
                        "unit": "mmol/L",
                        "analyte_canonical": "LDL-C",
                        "canonical_unit": "mmol/L",
                    }
                ],
            )
        )
    return report_refs


def test_st1_patient_cannot_read_another_patient_report_without_leakage(test_db):
    patient_a_key = _create_patient(test_db, "patient_a")
    _create_patient(test_db, "patient_b")
    report_b = _save_report(
        test_db,
        "patient_b",
        date(2026, 8, 2),
        [{"name": "SECRET_B_MARKER", "value": 9.9, "unit": "mmol/L"}],
        summary="B_ONLY_SUMMARY",
    )
    with test_db.session() as db:
        error = _raise_reason(wrappers.get_my_report, _current_patient("patient_a", patient_a_key), db, str(report_b))
    assert error.reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED
    assert "SECRET_B_MARKER" not in str(error)
    assert "B_ONLY_SUMMARY" not in str(error)


def test_st2_nonexistent_report_and_cross_user_report_are_indistinguishable(test_db):
    patient_a_key = _create_patient(test_db, "patient_a")
    _create_patient(test_db, "patient_b")
    report_b = _save_report(test_db, "patient_b", date(2026, 8, 2), [{"name": "WBC", "value": 7, "unit": "10^9/L"}])
    with test_db.session() as db:
        cross_user = _raise_reason(
            wrappers.get_my_report, _current_patient("patient_a", patient_a_key), db, str(report_b)
        )
        missing = _raise_reason(wrappers.get_my_report, _current_patient("patient_a", patient_a_key), db, "999999")
    assert cross_user.reason_code == missing.reason_code == ReasonCode.REPORT_NOT_FOUND_OR_UNAUTHORIZED
    assert str(cross_user) == str(missing)


def test_st3_identity_comes_from_current_user_and_injection_is_rejected_or_ignored(test_db):
    patient_a_key = _create_patient(test_db, "patient_a")
    patient_b_key = _create_patient(test_db, "patient_b")
    report_a = _save_report(test_db, "patient_a", date(2026, 8, 3), [{"name": "WBC", "value": 6, "unit": "10^9/L"}])
    _save_report(test_db, "patient_b", date(2026, 8, 4), [{"name": "WBC", "value": 99, "unit": "10^9/L"}])
    with test_db.session() as db:
        payload = wrappers.get_my_history(
            _current_patient("patient_a", patient_a_key),
            db,
            filters={"patient_id": patient_b_key, "user_id": patient_b_key},
        )
        with pytest.raises(TypeError):
            wrappers.get_my_history(_current_patient("patient_a", patient_a_key), db, patient_id=patient_b_key)
        with pytest.raises(TypeError):
            wrappers.get_my_report(
                _current_patient("patient_a", patient_a_key), db, str(report_a), user_id=patient_b_key
            )
        with pytest.raises(TypeError):
            wrappers.get_report_questions(
                _current_patient("patient_a", patient_a_key),
                db,
                report_ref=str(report_a),
                ui_context={"patient_id": patient_b_key},
            )
    assert payload.report_ref == str(report_a)


def test_st4_invalid_current_user_maps_to_auth_expired_without_db_access():
    db = QuerySpyDb()
    error = _raise_reason(wrappers.get_my_history, None, db)
    assert error.reason_code == ReasonCode.AUTH_EXPIRED
    assert db.calls == 0


def test_st5_guest_get_my_history_denied_before_db_query():
    db = QuerySpyDb()
    error = _raise_reason(wrappers.get_my_history, _guest(), db)
    assert error.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert db.calls == 0


def test_st6_guest_get_my_indicator_trend_denied_before_db_query():
    db = QuerySpyDb()
    error = _raise_reason(wrappers.get_my_indicator_trend, _guest(), db, "LDL-C")
    assert error.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert db.calls == 0


def test_st7_guest_questions_allow_session_result_but_deny_report_ref(test_db):
    _create_patient(test_db, "patient_a")
    report_a = _save_report(
        test_db, "patient_a", date(2026, 8, 3), [{"name": "WBC", "value": 12, "unit": "10^9/L", "status": "high"}]
    )
    session_result = AnalysisDataPayload(
        indicators=_response([{"name": "WBC", "value": 12, "unit": "10^9/L", "status": "high"}]).indicators
    )
    with test_db.session() as db:
        denied = _raise_reason(wrappers.get_report_questions, _guest(), db, report_ref=str(report_a))
        allowed = wrappers.get_report_questions(_guest(), db, session_result=session_result)
    assert denied.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert isinstance(allowed, DoctorQuestionsPayload)
    assert allowed.questions


def test_st8_insufficient_trend_points_raise_without_payload(test_db):
    patient_key = _create_patient(test_db, "patient_a")
    _seed_ldl_series(test_db, "patient_a", count=MIN_TREND_POINTS - 1)
    with test_db.session() as db:
        error = _raise_reason(wrappers.get_my_indicator_trend, _current_patient("patient_a", patient_key), db, "LDL-C")
    assert error.reason_code == ReasonCode.TREND_INSUFFICIENT_POINTS
    assert not hasattr(error, "payload")


def test_st9_db_outage_maps_to_db_unavailable_without_fallback_content():
    error = _raise_reason(wrappers.get_my_history, _current_patient("patient_a", 1), BrokenDb())
    assert error.reason_code == ReasonCode.DB_UNAVAILABLE
    assert not hasattr(error, "payload")


def test_st10_static_no_orchestrator_function_signature_accepts_patient_or_user_id():
    forbidden = {"patient_id", "user_id"}
    for path in ORCHESTRATOR_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                args = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
                assert forbidden.isdisjoint({arg.arg for arg in args})


def test_st11_doctor_get_my_history_denied_before_repository_call(monkeypatch):
    calls = 0

    def counted_list_reports(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("repository call must not execute")

    monkeypatch.setattr(wrappers.history_repository, "list_reports", counted_list_reports)
    error = _raise_reason(wrappers.get_my_history, _doctor(), QuerySpyDb())
    assert error.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY
    assert calls == 0


def test_st12_doctor_all_other_wrappers_raise_unsupported_capability():
    db = QuerySpyDb()
    calls = [
        lambda: wrappers.get_my_report(_doctor(), db, "1"),
        lambda: wrappers.get_my_indicator_trend(_doctor(), db, "LDL-C"),
        lambda: wrappers.get_report_questions(_doctor(), db, session_result=AnalysisDataPayload(indicators=[])),
    ]
    for call in calls:
        error = _raise_reason(call)
        assert error.reason_code == ReasonCode.UNSUPPORTED_CAPABILITY


def test_st13_static_history_list_reports_call_is_always_patient_scoped():
    calls = []
    for path in ORCHESTRATOR_ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        calls.extend(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "list_reports"
        )
    assert calls
    for call in calls:
        keywords = {keyword.arg: keyword.value for keyword in call.keywords}
        assert "patient_id" in keywords
        assert not isinstance(keywords["patient_id"], ast.Constant) or keywords["patient_id"].value is not None
        assert "patient_username" not in keywords


@pytest.mark.asyncio
async def test_st14_doctor_orchestrator_entrypoint_blocked_before_wrappers(client, monkeypatch):
    calls = 0

    def counted_wrapper(*args, **kwargs):
        nonlocal calls
        calls += 1
        raise AssertionError("wrapper call must not execute")

    monkeypatch.setattr(orchestrator_routes, "handle_message", orchestrator_routes.handle_message)
    monkeypatch.setattr(wrappers, "get_my_history", counted_wrapper)
    monkeypatch.setattr(wrappers, "get_my_report", counted_wrapper)
    monkeypatch.setattr(wrappers, "get_my_indicator_trend", counted_wrapper)
    monkeypatch.setattr(wrappers, "get_report_questions", counted_wrapper)
    login = await client.post(
        "/api/v1/auth/login",
        json={"username": "bacsi", "password": "bacsi123"},
    )
    assert login.status_code == 200
    response = await client.post(
        "/api/v1/orchestrator/message",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
        json={"message": "cho tôi xem lịch sử"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "blocked"
    assert payload["reason_code"] == ReasonCode.UNSUPPORTED_CAPABILITY
    assert calls == 0


def test_st15_static_orchestrator_does_not_read_ocr_drafts_or_build_ocr_analysis_input():
    forbidden_terms = {
        "ocr_drafts",
        "OCRIndicatorDraft",
        "OCRReviewedIndicator",
    }
    for path in ORCHESTRATOR_ROOT.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert forbidden_terms.isdisjoint(source.split())
        for term in forbidden_terms:
            assert term not in source
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.List | ast.Dict | ast.ListComp | ast.DictComp):
                names = {child.id for child in ast.walk(node) if isinstance(child, ast.Name)}
                assert not any("draft" in name.casefold() for name in names)


def test_st16_trend_report_ids_are_owned_by_authenticated_patient(test_db):
    patient_a_key = _create_patient(test_db, "patient_a")
    _create_patient(test_db, "patient_b")
    reports_a = set(_seed_ldl_series(test_db, "patient_a", count=MIN_TREND_POINTS, start_day=1))
    reports_b = set(_seed_ldl_series(test_db, "patient_b", count=MIN_TREND_POINTS, start_day=10))
    with test_db.session() as db:
        payload = wrappers.get_my_indicator_trend(_current_patient("patient_a", patient_a_key), db, "LDL-C")
    returned_refs = {point.report_id for point in payload.trend.points}
    assert isinstance(payload, TrendDataPayload)
    assert returned_refs
    assert returned_refs <= reports_a
    assert returned_refs.isdisjoint(reports_b)


def test_wrappers_return_tip_001_payload_types(test_db):
    patient_key = _create_patient(test_db, "patient_a")
    report_ref = _save_report(
        test_db, "patient_a", date(2026, 8, 3), [{"name": "WBC", "value": 12, "unit": "10^9/L", "status": "high"}]
    )
    _seed_ldl_series(test_db, "patient_a", count=MIN_TREND_POINTS, start_day=10)
    with test_db.session() as db:
        current_user = _current_patient("patient_a", patient_key)
        assert isinstance(wrappers.get_my_history(current_user, db), HistorySummaryPayload)
        assert isinstance(wrappers.get_my_report(current_user, db, str(report_ref)), AnalysisDataPayload)
        assert isinstance(wrappers.get_my_indicator_trend(current_user, db, "LDL-C"), TrendDataPayload)
        assert isinstance(
            wrappers.get_report_questions(current_user, db, report_ref=str(report_ref)), DoctorQuestionsPayload
        )
