from src.services.analyte_catalog import get_analyte_catalog


def test_catalog_resolves_reference_canonical_names_without_embeddings():
    catalog = get_analyte_catalog()

    assert catalog.resolve("Glucose").analyte_id == "glucose"
    assert catalog.resolve("Fasting plasma glucose").analyte_id == "glucose"
    assert catalog.resolve("Kali").analyte_id == "kali"
    assert catalog.resolve("Potassium").analyte_id == "kali"
    assert catalog.resolve("LDL-C").analyte_id == "ldl_cholesterol"


def test_catalog_returns_curated_fallback_and_sources():
    definition = get_analyte_catalog().resolve("WBC")

    assert definition is not None
    assert definition.curated_explanation
    assert definition.sources


def test_catalog_does_not_semantically_guess_unknown_analyte():
    assert get_analyte_catalog().resolve("white cells maybe-ish") is None
