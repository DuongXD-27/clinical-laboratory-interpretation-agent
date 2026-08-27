from src.services.patient_explanation import (
    LIMITATION_SENTENCE,
    build_patient_explanation,
    filter_patient_education_text,
)


def _explanation(analyte_id: str, name: str, unit: str, supplemental: str = "") -> str:
    return build_patient_explanation(
        analyte_id=analyte_id,
        name=name,
        value=100,
        unit=unit,
        status="low",
        critical_status=None,
        is_critical=False,
        curated_description="",
        supplemental_text=supplemental,
    )


def test_hgb_does_not_infer_unreported_symptoms_or_disease():
    explanation = _explanation(
        "hgb",
        "HGB",
        "g/L",
        "Bạn đang mệt mỏi và có thể bị thiếu máu. Hemoglobin nằm trong hồng cầu.",
    )
    assert "mệt mỏi" not in explanation
    assert "thiếu máu" not in explanation
    assert "Hemoglobin nằm trong hồng cầu" in explanation
    assert explanation.endswith(LIMITATION_SENTENCE)


def test_rbc_and_chloride_use_plain_language_contract():
    rbc = _explanation("rbc", "RBC", "10^12/L")
    chloride = _explanation("chloride", "Chloride", "mmol/L")
    assert rbc.startswith("RBC là số lượng hồng cầu trong máu.")
    assert "giúp đưa oxy đi khắp cơ thể" in rbc
    assert chloride.startswith("Chloride (clorua) là một chất điện giải trong máu.")
    assert "cân bằng nước" in chloride


def test_patient_filter_removes_causes_and_treatment_sentences():
    filtered = filter_patient_education_text(
        "Kali là chất điện giải. Tăng kali có thể do bệnh thận. Bạn nên dùng thuốc."
    )
    assert filtered == "Kali là chất điện giải."
