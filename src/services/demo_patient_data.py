from __future__ import annotations

import datetime

from sqlalchemy.orm import Session

from src.models.db import LabReport, User
from src.models.schemas import AnalyzeRequest, AnalyzeResponse
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

DEMO_REPORTS = [
    {
        "test_date": "2026-08-12",
        "summary": "Phiếu mẫu có LDL-C cao và các chỉ số còn lại trong vùng tham khảo.",
        "values": {
            "WBC": (7.1, "normal"),
            "RBC": (4.9, "normal"),
            "HGB": (150, "normal"),
            "Fasting plasma glucose": (5.2, "normal"),
            "HbA1c": (5.4, "normal"),
            "LDL-C": (3.4, "high"),
            "HDL-C": (1.3, "normal"),
            "Creatinine": (82, "normal"),
            "Potassium": (4.2, "normal"),
        },
    },
    {
        "test_date": "2026-08-11",
        "summary": "Phiếu mẫu bình thường với đủ 9 chỉ số đã được hỗ trợ.",
        "values": {
            "WBC": (6.8, "normal"),
            "RBC": (5.0, "normal"),
            "HGB": (152, "normal"),
            "Fasting plasma glucose": (5.0, "normal"),
            "HbA1c": (5.2, "normal"),
            "LDL-C": (2.1, "normal"),
            "HDL-C": (1.4, "normal"),
            "Creatinine": (78, "normal"),
            "Potassium": (4.1, "normal"),
        },
    },
    {
        "test_date": "2026-08-10",
        "summary": "Phiếu mẫu có Kali ở mức nguy kịch để kiểm tra trạng thái CRITICAL.",
        "values": {
            "WBC": (9.5, "normal"),
            "RBC": (4.7, "normal"),
            "HGB": (145, "normal"),
            "Fasting plasma glucose": (6.4, "high"),
            "HbA1c": (6.2, "high"),
            "LDL-C": (3.2, "high"),
            "HDL-C": (0.9, "low"),
            "Creatinine": (92, "normal"),
            "Potassium": (7.0, "critical_high"),
        },
    },
    {
        "test_date": "2026-08-09",
        "summary": "Phiếu mẫu dùng alias Glucose để kiểm tra canonical analyte.",
        "raw_names": {"Fasting plasma glucose": "Glucose"},
        "values": {
            "WBC": (5.9, "normal"),
            "RBC": (4.6, "normal"),
            "HGB": (135, "normal"),
            "Fasting plasma glucose": (5.7, "normal"),
            "HbA1c": (5.5, "normal"),
            "LDL-C": (2.4, "normal"),
            "HDL-C": (1.2, "normal"),
            "Creatinine": (70, "normal"),
            "Potassium": (3.8, "normal"),
        },
    },
    {
        "test_date": "2026-08-08",
        "summary": "Phiếu mẫu có HGB thấp để kiểm tra trạng thái ABNORMAL.",
        "raw_names": {"HGB": "Hemoglobin"},
        "values": {
            "WBC": (6.2, "normal"),
            "RBC": (4.3, "low"),
            "HGB": (105, "low"),
            "Fasting plasma glucose": (5.1, "normal"),
            "HbA1c": (5.3, "normal"),
            "LDL-C": (2.0, "normal"),
            "HDL-C": (1.1, "normal"),
            "Creatinine": (65, "normal"),
            "Potassium": (4.0, "normal"),
        },
    },
]


def seed_demo_patient_reports(db: Session) -> int:
    patient = db.query(User).filter(User.username == DEMO_PATIENT_USERNAME, User.role == "patient").first()
    if patient is None:
        return 0

    saved = 0
    for report in DEMO_REPORTS:
        rows = []
        raw_names = report.get("raw_names", {})
        for canonical, unit, low, high in APPROVED_ANALYTES:
            value, status = report["values"][canonical]
            rows.append(
                {
                    "canonical": canonical,
                    "name": raw_names.get(canonical, canonical),
                    "value": value,
                    "unit": unit,
                    "reference_low": low,
                    "reference_high": high,
                    "status": status,
                    "is_abnormal": status in {"low", "high", "critical_low", "critical_high"},
                    "is_critical": status in {"critical_low", "critical_high"},
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
            indicators=[
                {"name": row["name"], "value": row["value"], "unit": row["unit"]}
                for row in rows
            ],
        )
        result = save_analyzed_report(
            db,
            username=DEMO_PATIENT_USERNAME,
            request=request,
            analysis=analysis,
        )
        if result.saved:
            saved += 1
    return saved
