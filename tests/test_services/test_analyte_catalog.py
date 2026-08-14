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
