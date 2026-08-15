from src.services.analyte_catalog import get_analyte_catalog


def test_catalog_resolves_reference_canonical_names_without_embeddings():
    catalog = get_analyte_catalog()

    # IDs are now derived from the "name" field (lowercased, spaces/hyphens → underscores)
    assert catalog.resolve("Fasting plasma glucose").analyte_id == "fasting_plasma_glucose"
    assert catalog.resolve("Potassium").analyte_id == "potassium"
    assert catalog.resolve("LDL-C").analyte_id == "ldl_c"
    assert catalog.resolve("WBC").analyte_id == "wbc"


def test_catalog_returns_sources():
    definition = get_analyte_catalog().resolve("WBC")

    assert definition is not None
    assert definition.sources  # sources are URLs extracted from sources[].url


def test_catalog_does_not_semantically_guess_unknown_analyte():
    assert get_analyte_catalog().resolve("white cells maybe-ish") is None


def test_all_nine_supported_analytes_have_curated_descriptions():
    catalog = get_analyte_catalog()
    expected_analytes = [
        "WBC",
        "RBC",
        "HGB",
        "Fasting plasma glucose",
        "HbA1c",
        "LDL-C",
        "HDL-C",
        "Creatinine",
        "Potassium",
    ]
    for analyte in expected_analytes:
        definition = catalog.resolve(analyte)
        assert definition is not None, f"Expected {analyte} in catalog"
        assert len(definition.curated_explanation) > 20, f"Expected description for {analyte}"
        assert definition.description == definition.curated_explanation
        assert len(definition.sources) > 0, f"Expected sources for {analyte}"


def test_status_aware_explanation_selection():
    catalog = get_analyte_catalog()
    wbc = catalog.resolve("WBC")
    assert wbc is not None

    # HIGH picks high_note
    assert wbc.explanation_for_status("high") == wbc.high_note
    assert len(wbc.high_note) > 20

    # LOW picks low_note
    assert wbc.explanation_for_status("low") == wbc.low_note
    assert len(wbc.low_note) > 20

    # NORMAL picks neutral description
    assert wbc.explanation_for_status("normal") == wbc.curated_explanation

    # UNKNOWN picks neutral description
    assert wbc.explanation_for_status("unknown") == wbc.curated_explanation


def test_missing_state_note_falls_back_to_neutral_description():
    catalog = get_analyte_catalog()
    ldl = catalog.resolve("LDL-C")
    assert ldl is not None
    # LDL-C has no low_note in approved data
    assert ldl.low_note == ""
    # explanation_for_status("low") must fall back to neutral description, not invent text
    assert ldl.explanation_for_status("low") == ldl.curated_explanation


def test_critical_status_selection():
    catalog = get_analyte_catalog()
    potassium = catalog.resolve("Potassium")
    assert potassium is not None
    assert potassium.critical_high_note != ""
    assert potassium.critical_low_note != ""

    # CRITICAL_HIGH selects critical_high_note
    assert potassium.explanation_for_status("critical_high") == potassium.critical_high_note
    assert potassium.explanation_for_status("high", critical_status="critical_high") == potassium.critical_high_note
    # CRITICAL_LOW selects critical_low_note
    assert potassium.explanation_for_status("critical_low") == potassium.critical_low_note
    assert potassium.explanation_for_status("low", critical_status="critical_low") == potassium.critical_low_note

