import pytest
from datetime import date
from src.models.db import LabReport, ReportIndicator, User, ROLE_PATIENT
from src.models.schemas import AnalyzeRequest, AnalyzeResponse, IndicatorResultSchema, CriticalAlertSchema
from src.services import history_repository as repo

@pytest.fixture
def patient(test_db):
    u = User(username="test_patient", password_hash="hash", role=ROLE_PATIENT)
    with test_db.session() as db:
        db.add(u)
        db.commit()
        db.refresh(u)
    return u

def test_snapshot_persistence_for_35_analyte_contract(test_db, patient):
    """Chứng minh metadata hiển thị được lưu chuẩn theo thiết kế."""
    
    request = AnalyzeRequest(
        test_date=date(2026, 8, 19),
        patient_age=30,
        patient_gender="male",
        indicators=[
            {"name": "WBC", "value": 15.0, "unit": "10^9/L"},
            {"name": "AST", "value": 45.0, "unit": "U/L"},
            {"name": "Triglyceride", "value": 6.0, "unit": "mmol/L"},
            {"name": "HbA1c", "value": 6.0, "unit": "%"},
            {"name": "Fasting plasma glucose", "value": 7.5, "unit": "mmol/L"},
            {"name": "Uric acid", "value": 400.0, "unit": "umol/L"},
            {"name": "Total bilirubin", "value": 300.0, "unit": "umol/L"},
        ]
    )
    
    response = AnalyzeResponse(
        indicators=[
            # A. WBC RI
            IndicatorResultSchema(
                name="WBC", value=15.0, unit="10^9/L", status="high",
                rule_type="RI", reference_low=4.0, reference_high=10.0,
                is_abnormal=True, is_critical=False, explanation=""
            ),
            # B. AST ONE_SIDED_LIMIT
            IndicatorResultSchema(
                name="AST", value=45.0, unit="U/L", status="high",
                rule_type="ONE_SIDED_LIMIT", upper_operator="<", reference_high=40.0,
                is_abnormal=True, is_critical=False, explanation=""
            ),
            # C. Triglyceride BAND
            IndicatorResultSchema(
                name="Triglyceride", value=6.0, unit="mmol/L", status="very_high",
                rule_type="BAND", band_id="very_high",
                is_abnormal=True, is_critical=False, explanation=""
            ),
            # D. HbA1c CDL
            IndicatorResultSchema(
                name="HbA1c", value=6.0, unit="%", status="prediabetes",
                rule_type="CDL", band_id="prediabetes",
                is_abnormal=True, is_critical=False, explanation=""
            ),
            # E. FPG CDL
            IndicatorResultSchema(
                name="Fasting plasma glucose", value=7.5, unit="mmol/L", status="provisional_diabetes",
                rule_type="CDL", band_id="provisional_diabetes",
                is_abnormal=True, is_critical=False, explanation=""
            ),
            # F. Uric acid UNKNOWN
            IndicatorResultSchema(
                name="Uric acid", value=400.0, unit="umol/L", status="unknown",
                rule_type=None, evaluation_reason="analyte_not_supported",
                is_abnormal=False, is_critical=False, explanation=""
            ),
            # G. Total bilirubin critical
            IndicatorResultSchema(
                name="Total bilirubin", value=300.0, unit="umol/L", status="high",
                critical_status="critical_high", rule_type="RI", reference_high=21.0,
                is_abnormal=True, is_critical=True, explanation=""
            ),
        ],
        critical_alerts=[
            CriticalAlertSchema(indicator_name="Total bilirubin", value=300.0, unit="umol/L", message="Nguy kịch")
        ],
        has_critical_values=True,
        guardrail_passed=True,
    )
    
    with test_db.session() as db:
        report = repo.save_report(db, patient_id=patient.id, request=request, response=response)
        
        # Verify DB persistence
        wbc_db = next(i for i in report.indicators if i.name == "WBC")
        assert wbc_db.rule_type == "RI"
        assert wbc_db.reference_low == 4.0
        
        ast_db = next(i for i in report.indicators if i.name == "AST")
        assert ast_db.rule_type == "ONE_SIDED_LIMIT"
        assert ast_db.upper_operator == "<"
        
        tg_db = next(i for i in report.indicators if i.name == "Triglyceride")
        assert tg_db.rule_type == "BAND"
        assert tg_db.band_id == "very_high"
        
        hba1c_db = next(i for i in report.indicators if i.name == "HbA1c")
        assert hba1c_db.rule_type == "CDL"
        
        uric_db = next(i for i in report.indicators if i.name == "Uric acid")
        assert uric_db.rule_type is None
        assert uric_db.evaluation_reason == "analyte_not_supported"
        
        # Verify API mapping
        detail = repo.to_detail(report)
        wbc_api = next(i for i in detail.indicators if i.name == "WBC")
        assert wbc_api.rule_type == "RI"
        assert wbc_api.reference_low == 4.0
        
        ast_api = next(i for i in detail.indicators if i.name == "AST")
        assert ast_api.rule_type == "ONE_SIDED_LIMIT"
        assert ast_api.upper_operator == "<"
    
def test_legacy_history_compatibility(test_db, patient):
    """Test old row without the newly added metadata."""
    
    with test_db.session() as db:
        # Bỏ qua repository layer, insert trực tiếp mô phỏng data cũ
        report = LabReport(
            patient_id=patient.id,
            test_date=date(2026, 1, 1),
            language="vi"
        )
        db.add(report)
        db.flush()
        
        indicator = ReportIndicator(
            report_id=report.id,
            name="Legacy Test",
            value=10.0,
            unit="U/L",
            status="normal",
            reference_low=0.0,
            reference_high=20.0,
            rule_type=None,
            band_id=None,
            upper_operator=None,
            evaluation_reason=None
        )
        db.add(indicator)
        db.commit()
        
        # Verify API mapping does not crash
        detail = repo.to_detail(report)
        assert len(detail.indicators) == 1
        api_ind = detail.indicators[0]
        assert api_ind.rule_type is None
        assert api_ind.band_id is None
        assert api_ind.upper_operator is None
        assert api_ind.evaluation_reason is None
        assert api_ind.reference_low == 0.0
        assert api_ind.reference_high == 20.0
