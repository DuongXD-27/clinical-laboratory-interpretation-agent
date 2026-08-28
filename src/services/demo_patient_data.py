from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from src.models.db import LabReport, ReportQuestion, User
from src.models.schemas import AnalyzeRequest, AnalyzeResponse
from src.services.doctor_review_service import refresh_review_flags
from src.services.lab_history_service import save_analyzed_report

DEMO_PATIENT_USERNAME = "benhnhan"

APPROVED_ANALYTES = [
    ("WBC", "10^9/L", 4.72, 11.3),
    ("RBC", "10^12/L", 4.45, 6.19),
    ("HGB", "g/L", 128, 183),
    ("Fasting plasma glucose", "mmol/L", 4.1, 6.1),
    ("HbA1c", "%", 4.0, 5.7),
    ("LDL-C", "mmol/L", 0, 2.59),
    ("HDL-C", "mmol/L", 1.0, None),
    ("Creatinine", "µmol/L", 59, 104),
    ("Potassium", "mmol/L", 3.5, 5.3),
]

APPROVED_ANALYTE_META = {
    canonical: {"unit": unit, "reference_low": low, "reference_high": high}
    for canonical, unit, low, high in APPROVED_ANALYTES
}

DEMO_REPORTS = [
    {
        "test_date": "2026-08-12",
        "summary": "Phiếu mẫu gần nhất có đủ 9 chỉ số đã hỗ trợ, phục vụ Dashboard và Trend.",
        "values": {
            "WBC": (7.1, "normal"),
            "RBC": (4.9, "normal"),
            "HGB": (150, "normal"),
            "Fasting plasma glucose": (5.2, "normal"),
            "HbA1c": (5.4, "normal"),
            "LDL-C": (3.4, "high"),
            "HDL-C": (1.3, "normal"),
            "Creatinine": (82, "normal"),
            "Potassium": (7.0, "critical_high"),
        },
    },
    {
        "test_date": "2026-07-28",
        "summary": "Phiếu mẫu có LDL-C cao nhẹ và Creatinine lần thứ hai.",
        "values": {
            "WBC": (6.8, "normal"),
            "Fasting plasma glucose": (5.4, "normal"),
            "HbA1c": (5.3, "normal"),
            "LDL-C": (3.0, "high"),
            "HDL-C": (1.4, "normal"),
            "Creatinine": (78, "normal"),
        },
    },
    {
        "test_date": "2026-07-05",
        "summary": "Phiếu mẫu dùng alias Glucose để kiểm tra canonical analyte trong Trend.",
        "raw_names": {"Fasting plasma glucose": "Glucose"},
        "values": {
            "RBC": (4.7, "normal"),
            "Fasting plasma glucose": (5.8, "normal"),
            "LDL-C": (2.8, "high"),
            "HDL-C": (1.2, "normal"),
        },
    },
    {
        "test_date": "2026-06-10",
        "summary": "Phiếu mẫu có Glucose cao để demo filter 3 tháng gần nhất.",
        "values": {
            "WBC": (9.5, "normal"),
            "Fasting plasma glucose": (6.4, "high"),
            "HbA1c": (6.2, "high"),
            "LDL-C": (3.2, "high"),
        },
    },
    {
        "test_date": "2026-05-15",
        "summary": "Phiếu mẫu nằm trong mốc 3 tháng để Trend có đủ dữ liệu.",
        "raw_names": {"HGB": "Hemoglobin"},
        "values": {
            "WBC": (6.2, "normal"),
            "HGB": (105, "low"),
            "Fasting plasma glucose": (5.1, "normal"),
            "LDL-C": (2.5, "normal"),
        },
    },
    {
        "test_date": "2026-04-10",
        "summary": "Phiếu mẫu cũ hơn 3 tháng, dùng để demo latest5 khác three_months.",
        "values": {
            "LDL-C": (2.3, "normal"),
            "HDL-C": (1.1, "normal"),
        },
    },
]


def seed_demo_patient_reports(db: Session) -> int:
    patient = db.query(User).filter(User.username == DEMO_PATIENT_USERNAME, User.role == "patient").first()
    if patient is None:
        return 0

    saved = 0
    for index, report in enumerate(DEMO_REPORTS):
        rows = []
        raw_names = report.get("raw_names", {})
        for canonical, (value, status) in report["values"].items():
            meta = APPROVED_ANALYTE_META[canonical]
            is_critical = status in {"critical_low", "critical_high"}
            critical_status = status if is_critical else None
            effective_status = "high" if status == "critical_high" else "low" if status == "critical_low" else status
            rows.append(
                {
                    "canonical": canonical,
                    "name": raw_names.get(canonical, canonical),
                    "value": value,
                    "unit": meta["unit"],
                    "reference_low": meta["reference_low"],
                    "reference_high": meta["reference_high"],
                    "status": effective_status,
                    "critical_status": critical_status,
                    "is_abnormal": is_critical or effective_status in {"low", "high"},
                    "is_critical": is_critical,
                    "explanation": f"{canonical} là chỉ số mẫu phục vụ kiểm thử lịch sử xét nghiệm.",
                }
            )

        analysis = AnalyzeResponse(
            indicators=[
                {
                    "name": row["canonical"],
                    "value": row["value"],
                    "unit": row["unit"],
                    "reference_low": row["reference_low"],
                    "reference_high": row["reference_high"],
                    "status": row["status"],
                    "critical_status": row["critical_status"],
                    "is_abnormal": row["is_abnormal"],
                    "is_critical": row["is_critical"],
                    "explanation": row["explanation"],
                    "sources": [],
                }
                for row in rows
            ],
            has_critical_values=any(row["is_critical"] for row in rows),
            summary=report["summary"],
            guardrail_passed=True,
            disclaimer="Dữ liệu mẫu phục vụ phát triển, không phải tư vấn y khoa.",
        )
        request = AnalyzeRequest(
            patient_age=35,
            patient_gender="male",
            test_date=datetime.date.fromisoformat(report["test_date"]),
            language="vi",
            indicators=[{"name": row["name"], "value": row["value"], "unit": row["unit"]} for row in rows],
        )
        result = save_analyzed_report(
            db,
            username=DEMO_PATIENT_USERNAME,
            request=request,
            analysis=analysis,
            source_image=f"demo-ocr-{index + 1}.png" if index < 3 else None,
        )
        report_id = result.report_id or result.existing_report_id
        if report_id is not None:
            saved_report = db.get(LabReport, report_id)
            if saved_report is not None:
                if index < 3 and saved_report.indicators:
                    saved_report.ocr_source_filename = f"demo-ocr-{index + 1}.png"
                    saved_report.indicators[0].ocr_confidence = 0.62 + (index * 0.04)
                    saved_report.indicators[0].ocr_raw_text = saved_report.indicators[0].name

                if index < 3 and not saved_report.questions:
                    db.add(
                        ReportQuestion(
                            report_id=saved_report.id,
                            indicator_id=saved_report.indicators[0].id if saved_report.indicators else None,
                            question_text=(
                                "Tôi nên hỏi bác sĩ điều gì quan trọng nhất về "
                                f"{saved_report.indicators[0].name if saved_report.indicators else 'phiếu này'}?"
                            ),
                            priority="critical" if saved_report.has_critical_values else "abnormal",
                            display_order=0,
                            status="sent_to_doctor",
                            is_selected=True,
                        )
                    )
                    db.commit()

                refresh_review_flags(db, saved_report)

        if result.saved:
            saved += 1
    return saved
