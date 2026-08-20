"""Nhóm chức năng (ADR-010 CRIT-TREND-06) đọc từ data/reference/reference_ranges.json thật."""

from src.services.analyte_sections import (
    CHEMISTRY,
    HEMATOLOGY,
    LIPIDS,
    OTHER,
    analyte_section,
    section_label,
)


def test_hematology_analyte_resolves_to_hematology_section():
    assert analyte_section("WBC") == HEMATOLOGY


def test_fasting_plasma_glucose_is_overridden_to_lipids():
    """ADR-010 CRIT-TREND-06: FPG lệch khỏi cột section gốc của CSV để khớp nhóm
    sản phẩm "Mỡ máu & đường huyết" theo Business Description."""

    assert analyte_section("Fasting plasma glucose") == LIPIDS


def test_chemistry_analyte_resolves_to_chemistry_section():
    assert analyte_section("Creatinine") == CHEMISTRY


def test_unknown_analyte_has_no_section():
    assert analyte_section("Not A Real Analyte") is None


def test_section_label_maps_known_sections_to_vietnamese_display_text():
    assert section_label(HEMATOLOGY) == "Huyết học"
    assert section_label(CHEMISTRY) == "Sinh hóa thận - gan"
    assert section_label(LIPIDS) == "Mỡ máu & đường huyết"
    assert section_label(OTHER) == "Khác"


def test_section_label_of_none_is_none():
    assert section_label(None) is None


def test_section_label_falls_back_to_other_for_unrecognized_key():
    assert section_label("not-a-real-section") == "Khác"
