from __future__ import annotations

import csv
import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest

from src.services.reference_repository import ReferenceRepository, ReferenceRepositoryError


def make_config(
    *,
    approved=None,
    pending=None,
    allowed_reference_types=None,
):
    approved = approved or ["WBC", "RBC", "Fasting plasma glucose", "Creatinine"]
    pending = pending or ["HDL-C", "HbA1c", "LDL-C", "Potassium"]
    aliases = {
        "WBC": "WBC",
        "RBC": "RBC",
        "Fasting plasma glucose": "Fasting plasma glucose",
        "Fasting Blood Glucose": "Fasting plasma glucose",
        "Đường huyết lúc đói": "Fasting plasma glucose",
        "Glucose máu lúc đói": "Fasting plasma glucose",
        "HDL-Cholesterol": "HDL-C",
        "HDL-C": "HDL-C",
        "HDL-cho.": "HDL-C",
        "Creatinine": "Creatinine",
        "Creatinin": "Creatinine",
        "HbA1c": "HbA1c",
        "LDL-C": "LDL-C",
        "LDL-Cholesterol": "LDL-C",
        "LDL-cho.": "LDL-C",
        "Kali": "Potassium",
        "Potassium": "Potassium",
        "Potassium (K+)": "Potassium",
        "K+": "Potassium",
    }
    for analyte in approved + pending:
        aliases.setdefault(analyte, analyte)
    return {
        "config_version": "v2",
        "allowed_reference_types": allowed_reference_types or ["RI"],
        "approved_analytes": approved,
        "pending_analytes": pending,
        "analyte_aliases": aliases,
        "age_scope_aliases": {"Adult": {"min_age": 18, "max_age": 60}},
    }


def make_rule(
    analyte="WBC",
    *,
    sex="A",
    age_scope="18-60",
    unit="10^9/L",
    lower=4,
    upper=10,
    reference_type="RI",
):
    return {
        "rule_id": f"{analyte}-{sex}-{unit}-{lower}-{upper}-{reference_type}",
        "source_row_number": 2,
        "analyte_canonical": analyte,
        "specimen": "Synthetic",
        "fasting_required": "NO",
        "sex": sex,
        "age_scope": age_scope,
        "unit_machine": unit,
        "unit_display_vn": unit,
        "unit_raw": unit,
        "unit_canonical": unit,
        "value_type": "absolute",
        "range_lower": lower,
        "range_upper": upper,
        "reference_type": reference_type,
        "source_priority_tier": "T1",
        "source_url": "https://example.test/source",
        "confidence": "HIGH",
    }


def make_unit_rows(*, hgb_unit="g/L"):
    return [
        {"test_name": "WBC", "standardized_unit": "10^9/L"},
        {"test_name": "RBC", "standardized_unit": "10^12/L"},
        {"test_name": "HGB", "standardized_unit": hgb_unit},
        {"test_name": "Fasting plasma glucose", "standardized_unit": "mmol/L"},
        {"test_name": "Creatinine", "standardized_unit": "µmol/L"},
        {"test_name": "HDL-C", "standardized_unit": "mmol/L"},
    ]


def base_rules():
    return [
        make_rule("WBC", unit="10^9/L"),
        make_rule("RBC", sex="M", unit="10^12/L", lower=4.5, upper=6.2),
        make_rule("RBC", sex="F", unit="10^12/L", lower=4.0, upper=5.5),
        make_rule("Fasting plasma glucose", unit="mmol/L", age_scope="Adult", lower=4.1, upper=6.1),
        make_rule("Fasting plasma glucose", unit="mmol/L", age_scope="Adult", lower=5.6, upper=6.9, reference_type="CDL"),
        make_rule("Creatinine", sex="M", unit="umol/L", age_scope="Adult", lower=59, upper=104),
        make_rule("Creatinine", sex="F", unit="umol/L", age_scope="Adult", lower=45, upper=84),
        make_rule("HDL-C", unit="mmol/L", age_scope="Adult", lower=1.0, upper=1.5, reference_type="CDL"),
    ]


@pytest.fixture
def repository():
    return ReferenceRepository(config=make_config(), rules=base_rules(), unit_rows=make_unit_rows())


def write_json(path: Path, data) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def write_units(path: Path, rows) -> None:
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=["test_name", "standardized_unit"], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def test_r01_config_and_rules_load(tmp_path: Path):
    config = tmp_path / "config.json"
    ranges = tmp_path / "ranges.json"
    units = tmp_path / "units.csv"
    write_json(config, make_config())
    write_json(ranges, base_rules())
    write_units(units, make_unit_rows())

    repo = ReferenceRepository.from_files(config_path=config, ranges_path=ranges, units_path=units)

    assert "WBC" in repo.approved_analytes


def test_r02_missing_config(tmp_path: Path):
    ranges = tmp_path / "ranges.json"
    write_json(ranges, base_rules())

    with pytest.raises(ReferenceRepositoryError):
        ReferenceRepository.from_files(config_path=tmp_path / "missing.json", ranges_path=ranges)


def test_r03_missing_ranges(tmp_path: Path):
    config = tmp_path / "config.json"
    write_json(config, make_config())

    with pytest.raises(ReferenceRepositoryError):
        ReferenceRepository.from_files(config_path=config, ranges_path=tmp_path / "missing.json")


def test_r04_invalid_json(tmp_path: Path):
    config = tmp_path / "config.json"
    ranges = tmp_path / "ranges.json"
    config.write_text("{", encoding="utf-8")
    write_json(ranges, base_rules())

    with pytest.raises(ReferenceRepositoryError):
        ReferenceRepository.from_files(config_path=config, ranges_path=ranges)


@pytest.mark.parametrize(
    ("alias", "canonical"),
    [
        ("K+", "Potassium"),
        ("Kali", "Potassium"),
        ("Potassium", "Potassium"),
        ("Potassium (K+)", "Potassium"),
        ("Creatinin", "Creatinine"),
        ("Creatinine", "Creatinine"),
        ("HDL-cho.", "HDL-C"),
        ("HDL-C", "HDL-C"),
        ("HDL-Cholesterol", "HDL-C"),
        ("LDL-cho.", "LDL-C"),
        ("LDL-C", "LDL-C"),
        ("LDL-Cholesterol", "LDL-C"),
    ],
)
def test_r05_alias_resolution(repository, alias, canonical):
    assert repository.resolve_analyte(alias) == canonical
    assert repository.resolve_analyte(f"  {alias.lower()}  ") == canonical


@pytest.mark.parametrize(
    "invalid_analyte",
    ["Glucose", "Đường huyết", "Unknown", "Unknown Analyte", "", "   ", None],
)
def test_r05b_unsafe_or_unknown_alias_rejected(repository, invalid_analyte):
    assert repository.resolve_analyte(invalid_analyte) is None


@pytest.mark.parametrize(
    ("raw_unit", "expected_normalized"),
    [
        ("mmol/L", "mmol/L"),
        ("mmol/l", "mmol/L"),
        ("µmol/L", "umol/L"),
        ("µmol/l", "umol/L"),
        ("μmol/l", "umol/L"),
        ("umol/l", "umol/L"),
        ("umol/L", "umol/L"),
        ("U/L", "U/L"),
        ("u/l", "U/L"),
        ("U/l", "U/L"),
    ],
)
def test_r05c_unit_normalization_equivalences(raw_unit, expected_normalized):
    assert ReferenceRepository.normalize_unit(raw_unit) == expected_normalized


@pytest.mark.parametrize("analyte", ["HbA1c", "LDL-C", "Potassium", "HDL-C"])
def test_r06_pending_analyte_rejected(repository, analyte):
    result = repository.select_rule(analyte=analyte, unit="mmol/L", patient_gender="male", patient_age=35)

    assert result.matched is False
    assert result.reason == "analyte_not_approved"


def test_r07_unknown_analyte_rejected(repository):
    result = repository.select_rule(analyte="Unknown", unit="mmol/L", patient_gender="male", patient_age=35)

    assert result.reason == "analyte_not_supported"


def test_r08_exact_unit_required(repository):
    result = repository.select_rule(analyte="WBC", unit="mg/dL", patient_gender="male", patient_age=35)

    assert result.reason == "unit_not_supported"


@pytest.mark.parametrize(
    ("rule_unit", "input_unit"),
    [
        ("10^9/L", "×10^9/L"),
        ("10^12/L", "×10^12/L"),
        ("umol/L", "µmol/L"),
        ("umol/L", "μmol/L"),
        ("10^9/L", "G/L"),
        ("10^12/L", "T/L"),
    ],
)
def test_r09_permitted_unit_aliases(rule_unit, input_unit):
    repo = ReferenceRepository(
        config=make_config(approved=["AliasTest"], pending=[]),
        rules=[make_rule("AliasTest", unit=rule_unit)],
    )

    result = repo.select_rule(analyte="AliasTest", unit=input_unit, patient_gender="male", patient_age=35)

    assert result.matched is True


def test_r10_mg_dl_and_mmol_l_distinct():
    repo = ReferenceRepository(
        config=make_config(approved=["Lipid"], pending=[]),
        rules=[make_rule("Lipid", unit="mmol/L")],
    )

    result = repo.select_rule(analyte="Lipid", unit="mg/dL", patient_gender="male", patient_age=35)

    assert result.reason == "unit_not_supported"


@pytest.mark.parametrize("input_unit", ["10^3/uL", "10^3/µL", "10^3/μL"])
def test_u_wbc_01_02_03_legacy_wbc_units_canonicalize(input_unit):
    assert ReferenceRepository.normalize_unit(input_unit) == "10^9/L"


def test_u_wbc_04_wbc_rule_10_9_matches_10_3_ul():
    repo = ReferenceRepository(
        config=make_config(approved=["WBC"], pending=[]),
        rules=[make_rule("WBC", unit="10^9/L")],
        unit_rows=[{"test_name": "WBC", "standardized_unit": "10^9/L"}],
    )

    result = repo.select_rule(analyte="WBC", unit="10^3/uL", patient_gender="male", patient_age=35)

    assert result.matched is True
    assert result.rule is not None
    assert result.rule["unit_canonical"] == "10^9/L"


def test_u_wbc_05_unit_normalization_does_not_change_rule_bounds():
    repo = ReferenceRepository(
        config=make_config(approved=["WBC"], pending=[]),
        rules=[make_rule("WBC", unit="10^9/L", lower=4, upper=10)],
        unit_rows=[{"test_name": "WBC", "standardized_unit": "10^9/L"}],
    )

    result = repo.select_rule(analyte="WBC", unit="10^3/uL", patient_gender="male", patient_age=35)

    assert result.matched is True
    assert result.rule is not None
    assert result.rule["range_lower"] == 4
    assert result.rule["range_upper"] == 10


@pytest.mark.parametrize("rule_unit", ["10^12/L", "g/L"])
def test_u_wbc_06_legacy_wbc_alias_does_not_match_unrelated_units(rule_unit):
    repo = ReferenceRepository(
        config=make_config(approved=["WBC"], pending=[]),
        rules=[make_rule("WBC", unit=rule_unit)],
    )

    result = repo.select_rule(analyte="WBC", unit="10^3/uL", patient_gender="male", patient_age=35)

    assert result.reason == "unit_not_supported"


def test_u_wbc_07_mg_dl_and_mmol_l_remain_distinct_after_wbc_aliases():
    assert ReferenceRepository.normalize_unit("mg/dL") == "mg/dL"
    assert ReferenceRepository.normalize_unit("mmol/L") == "mmol/L"


def test_u_wbc_08_units_metric_wbc_is_canonical():
    units_file = Path("data/reference/units_metric.csv")
    rows = list(csv.DictReader(units_file.open(encoding="utf-8-sig")))
    repo = ReferenceRepository.from_default_files()
    wbc_units = {row["standardized_unit"] for row in rows if row["test_name"] == "WBC"}

    assert wbc_units == {"10^9/L"}
    assert "WBC" in repo.approved_analytes
    assert "WBC" not in repo.unit_conflict_analytes


def test_u_wbc_09_hgb_approved_after_tip010():
    # After BONUS-TIP-010: HGB is fully approved — no unit conflict, not pending, matches queries.
    repo = ReferenceRepository.from_default_files()
    result = repo.select_rule(analyte="HGB", unit="g/L", patient_gender="male", patient_age=35)

    assert "HGB" not in repo.unit_conflict_analytes
    assert "HGB" in repo.approved_analytes
    assert "HGB" not in repo.pending_analytes
    assert result.matched is True


def test_unit_g_l_not_mapped_to_count_unit() -> None:
    assert ReferenceRepository.normalize_unit("g/L") == "g/L"
    assert ReferenceRepository.normalize_unit("g/L") != "10^9/L"


def test_unit_g_l_uppercase_maps_to_count() -> None:
    assert ReferenceRepository.normalize_unit("G/L") == "10^9/L"


def test_unit_g_l_not_matched_as_wbc_unit() -> None:
    # g/L must never match a 10^9/L WBC rule — they are different mass vs count units
    repo = ReferenceRepository(
        config=make_config(approved=["WBC"], pending=[]),
        rules=[make_rule("WBC", unit="10^9/L")],
        unit_rows=[{"test_name": "WBC", "standardized_unit": "10^9/L"}],
    )
    result = repo.select_rule(analyte="WBC", unit="g/L", patient_gender="male", patient_age=35)
    assert result.reason == "unit_not_supported"


@pytest.mark.parametrize("age", [18, 60])
def test_r11_r12_numeric_age_boundaries(repository, age):
    result = repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.matched is True


@pytest.mark.parametrize(("age", "reason"), [(17, "age_scope_not_supported"), (61, "age_scope_not_supported")])
def test_r13_r14_age_outside_range(repository, age, reason):
    result = repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.reason == reason


def test_r15_invalid_age_scope_does_not_infer():
    repo = ReferenceRepository(
        config=make_config(approved=["UnknownAge"], pending=[]),
        rules=[make_rule("UnknownAge", age_scope="middle aged")],
    )

    result = repo.select_rule(analyte="UnknownAge", unit="10^9/L", patient_gender="male", patient_age=35)

    assert result.reason == "age_scope_not_supported"


@pytest.mark.parametrize(("sex", "gender", "expected_low"), [("M", "male", 10), ("F", "female", 20)])
def test_r16_r17_exact_sex_over_a(sex, gender, expected_low):
    repo = ReferenceRepository(
        config=make_config(approved=["SexTest"], pending=[]),
        rules=[
            make_rule("SexTest", sex="A", lower=1, upper=2),
            make_rule("SexTest", sex=sex, lower=expected_low, upper=expected_low + 5),
        ],
    )

    result = repo.select_rule(analyte="SexTest", unit="10^9/L", patient_gender=gender, patient_age=35)

    assert result.matched is True
    assert result.rule["range_lower"] == expected_low


def test_r18_a_fallback():
    repo = ReferenceRepository(
        config=make_config(approved=["Fallback"], pending=[]),
        rules=[make_rule("Fallback", sex="A", lower=1, upper=2)],
    )

    result = repo.select_rule(analyte="Fallback", unit="10^9/L", patient_gender="male", patient_age=35)

    assert result.matched is True


def test_r19_other_gender_maps_to_a(repository):
    result = repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="other", patient_age=35)

    assert result.matched is True


def test_r20_unknown_internal_gender(repository):
    result = repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="unexpected", patient_age=35)

    assert result.reason == "invalid_patient_gender"


def test_r21_ambiguous_rules():
    repo = ReferenceRepository(
        config=make_config(approved=["Ambiguous"], pending=[]),
        rules=[
            make_rule("Ambiguous", lower=1, upper=2),
            make_rule("Ambiguous", lower=1, upper=2),
        ],
    )

    result = repo.select_rule(analyte="Ambiguous", unit="10^9/L", patient_gender="male", patient_age=35)

    assert result.reason == "ambiguous_reference_rule"


def test_r22_source_order_independence():
    rules = [
        make_rule("OrderTest", sex="A", lower=1, upper=2),
        make_rule("OrderTest", sex="M", lower=10, upper=20),
    ]
    config = make_config(approved=["OrderTest"], pending=[])
    repo_a = ReferenceRepository(config=config, rules=rules)
    repo_b = ReferenceRepository(config=config, rules=list(reversed(rules)))

    result_a = repo_a.select_rule(analyte="OrderTest", unit="10^9/L", patient_gender="male", patient_age=35)
    result_b = repo_b.select_rule(analyte="OrderTest", unit="10^9/L", patient_gender="male", patient_age=35)

    assert result_a.rule["range_lower"] == result_b.rule["range_lower"] == 10


def test_r23_allowed_reference_type_ri_preferred_over_cdl():
    repo = ReferenceRepository(
        config=make_config(approved=["MixedType"], pending=[]),
        rules=[
            make_rule("MixedType", lower=50, upper=60, reference_type="CDL"),
            make_rule("MixedType", lower=1, upper=2, reference_type="RI"),
        ],
    )

    result = repo.select_rule(analyte="MixedType", unit="10^9/L", patient_gender="male", patient_age=35)

    assert result.matched is True
    assert result.rule["reference_type"] == "RI"
    assert result.rule["range_lower"] == 1


def test_r24_no_mutation(repository):
    before = deepcopy(repository._rules)

    repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=35)
    repository.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=35)

    assert repository._rules == before


@pytest.mark.parametrize("age", [18, 60])
def test_a01_a02_adult_age_boundaries(age):
    repo = ReferenceRepository(
        config=make_config(approved=["AdultAge"], pending=[]),
        rules=[make_rule("AdultAge", age_scope="Adult")],
    )

    result = repo.select_rule(analyte="AdultAge", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.matched is True


@pytest.mark.parametrize("age", [17, 61])
def test_a03_a04_adult_outside_range(age):
    repo = ReferenceRepository(
        config=make_config(approved=["AdultAge"], pending=[]),
        rules=[make_rule("AdultAge", age_scope="Adult")],
    )

    result = repo.select_rule(analyte="AdultAge", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.reason == "age_scope_not_supported"


def test_a05_unknown_age_text():
    repo = ReferenceRepository(
        config=make_config(approved=["UnknownAge"], pending=[]),
        rules=[make_rule("UnknownAge", age_scope="Senior")],
    )

    result = repo.select_rule(analyte="UnknownAge", unit="10^9/L", patient_gender="male", patient_age=65)

    assert result.reason == "age_scope_not_supported"


@pytest.mark.parametrize("age", [18, 18.99])
def test_a06_open_ended_min_age_scope_rejects_under_minimum(age):
    repo = ReferenceRepository(
        config=make_config(approved=["OpenEndedAge"], pending=[]),
        rules=[make_rule("OpenEndedAge", age_scope=">=19")],
    )

    result = repo.select_rule(analyte="OpenEndedAge", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.reason == "age_scope_not_supported"


@pytest.mark.parametrize("age", [19, 90])
def test_a07_open_ended_min_age_scope_accepts_minimum_and_older(age):
    repo = ReferenceRepository(
        config=make_config(approved=["OpenEndedAge"], pending=[]),
        rules=[make_rule("OpenEndedAge", age_scope=">=19")],
    )

    result = repo.select_rule(analyte="OpenEndedAge", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.matched is True


@pytest.mark.parametrize("age", [19, 90])
def test_a08_plus_age_scope_accepts_minimum_and_older(age):
    repo = ReferenceRepository(
        config=make_config(approved=["PlusAge"], pending=[]),
        rules=[make_rule("PlusAge", age_scope="19+")],
    )

    result = repo.select_rule(analyte="PlusAge", unit="10^9/L", patient_gender="male", patient_age=age)

    assert result.matched is True


def test_t01_ri_preferred_over_cdl(repository):
    result = repository.select_rule(
        analyte="Fasting plasma glucose",
        unit="mmol/L",
        patient_gender="male",
        patient_age=35,
    )

    assert result.matched is True
    assert result.canonical_analyte == "Fasting plasma glucose"
    assert result.rule["reference_type"] == "RI"


def test_t02_cdl_only_hdl_c_pending(repository):
    result = repository.select_rule(analyte="HDL-Cholesterol", unit="mmol/L", patient_gender="male", patient_age=35)

    assert repository.resolve_analyte("HDL-Cholesterol") == "HDL-C"
    assert result.reason == "analyte_not_approved"


def test_u01_unit_map_agreement_for_final_approved_analytes(repository):
    assert repository.approved_analytes == {"WBC", "RBC", "Fasting plasma glucose", "Creatinine"}
    assert repository.unit_conflict_analytes == set()


@pytest.mark.parametrize(
    ("ocr_label", "canonical"),
    [
        ("Bạch cầu (WBC)", "WBC"),
        ("Hồng cầu (RBC)", "RBC"),
        ("Đường huyết lúc đói", "Fasting plasma glucose"),
        ("BACH CAU ( WBC )", "WBC"),
    ],
)
def test_u02_default_repository_resolves_ocr_labels(ocr_label, canonical):
    repo = ReferenceRepository.from_default_files()

    assert repo.resolve_analyte(ocr_label) == canonical


@pytest.mark.parametrize("generic_name", ["Glucose", "Đường huyết"])
def test_u02a_default_repository_rejects_generic_glucose_names(generic_name):
    repo = ReferenceRepository.from_default_files()

    assert repo.resolve_analyte(generic_name) is None


@pytest.mark.parametrize(
    "explicit_fasting_name",
    [
        "Fasting plasma glucose",
        "Fasting Blood Glucose",
        "Đường huyết lúc đói",
        "Glucose máu lúc đói",
    ],
)
def test_u02b_default_repository_preserves_explicit_fasting_glucose_aliases(
    explicit_fasting_name,
):
    repo = ReferenceRepository.from_default_files()

    assert repo.resolve_analyte(explicit_fasting_name) == "Fasting plasma glucose"


def test_u03_unit_conflict_isolation():
    repo = ReferenceRepository(
        config=make_config(approved=["WBC", "HGB"], pending=[]),
        rules=[make_rule("WBC", unit="10^9/L"), make_rule("HGB", unit="10^9/L")],
        unit_rows=make_unit_rows(hgb_unit="g/L"),
    )

    hgb = repo.select_rule(analyte="HGB", unit="10^9/L", patient_gender="male", patient_age=35)
    wbc = repo.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=35)

    assert hgb.reason == "unit_data_conflict"
    assert wbc.matched is True


def test_u04_direct_canonical_unit_lookup_all_approved():
    """Verify that default repository activates all Phase B approved analytes using direct canonical names."""
    repo = ReferenceRepository.from_default_files()
    expected_approved = {
        "WBC",
        "RBC",
        "HGB",
        "HCT",
        "MCV",
        "MCH",
        "MCHC",
        "RDW-CV",
        "PLT",
        "Neutrophils %",
        "Neutrophils abs",
        "Lymphocytes %",
        "Lymphocytes abs",
        "Monocytes %",
        "Monocytes abs",
        "Eosinophils %",
        "Eosinophils abs",
        "Sodium",
        "Chloride",
        "Fasting plasma glucose",
        "HbA1c",
        "Creatinine",
        "Urea",
        "AST",
        "ALT",
        "GGT",
        "Total bilirubin",
        "Total protein",
        "Albumin",
        "Total cholesterol",
        "Triglyceride",
        "LDL-C",
        "HDL-C",
        "Potassium",
        "Uric acid",
    }
    assert repo.approved_analytes == expected_approved
    assert repo.unit_conflict_analytes == frozenset()
    assert repo.pending_analytes == frozenset()


def test_u04a_rdw_cv_accepts_percent_cv_unit_alias():
    repo = ReferenceRepository.from_default_files()
    result = repo.select_rule(analyte="RDW", unit="%CV", value=14.0, patient_gender="female", patient_age=35)

    assert result.matched is True
    assert result.canonical_analyte == "RDW-CV"
    assert result.comparison_value is None


@pytest.mark.parametrize(
    ("analyte", "raw_unit", "raw_value", "expected_canonical", "expected_value"),
    [
        ("Total Cholesterol", "mg/dL", 200, "Total cholesterol", "5.1800"),
        ("Triglycerides", "mg/dL", 150, "Triglyceride", "1.6950"),
        ("HDL-C", "mg/dL", 40, "HDL-C", "1.0360"),
        ("LDL-Cholesterol", "mg/dL", 100, "LDL-C", "2.5900"),
    ],
)
def test_u04b_lipid_mg_dl_inputs_use_existing_mmol_conversion(
    analyte,
    raw_unit,
    raw_value,
    expected_canonical,
    expected_value,
):
    repo = ReferenceRepository.from_default_files()
    result = repo.select_rule(
        analyte=analyte,
        unit=raw_unit,
        value=raw_value,
        patient_gender="male",
        patient_age=35,
    )

    assert result.matched is True
    assert result.canonical_analyte == expected_canonical
    assert result.comparison_unit == "mmol/L"
    assert result.comparison_value == Decimal(expected_value)


def test_u05_unit_conflict_demotes_to_pending():
    """Inject incompatible unit in unit_rows -> Potassium must be demoted to pending."""
    repo = ReferenceRepository(
        config=make_config(approved=["WBC", "Potassium"], pending=[]),
        rules=[
            make_rule("WBC", unit="10^9/L"),
            make_rule("Potassium", unit="mmol/L"),
        ],
        unit_rows=[
            {"test_name": "WBC", "standardized_unit": "10^9/L"},
            {"test_name": "Potassium", "standardized_unit": "mg/dL"},  # Incompatible unit
        ],
    )
    assert "Potassium" not in repo.approved_analytes
    assert "Potassium" in repo.pending_analytes
    assert "Potassium" in repo.unit_conflict_analytes

    result = repo.select_rule(analyte="Potassium", unit="mmol/L", patient_gender="male", patient_age=35)
    assert result.matched is False
    assert result.reason == "unit_data_conflict"


def test_u06_missing_unit_row_demotes_to_pending():
    """If unit row for declared-approved analyte is missing -> fail-closed to pending."""
    repo = ReferenceRepository(
        config=make_config(approved=["WBC", "Potassium"], pending=[]),
        rules=[
            make_rule("WBC", unit="10^9/L"),
            make_rule("Potassium", unit="mmol/L"),
        ],
        unit_rows=[
            {"test_name": "WBC", "standardized_unit": "10^9/L"},
            # Potassium row omitted
        ],
    )
    assert "Potassium" not in repo.approved_analytes
    assert "Potassium" in repo.pending_analytes
    assert "Potassium" in repo.unit_conflict_analytes

    result = repo.select_rule(analyte="Potassium", unit="mmol/L", patient_gender="male", patient_age=35)
    assert result.matched is False
    assert result.reason == "unit_data_conflict"
