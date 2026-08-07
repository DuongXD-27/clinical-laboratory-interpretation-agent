from __future__ import annotations

import csv
import json
from copy import deepcopy
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
        "Glucose": "Fasting plasma glucose",
        "Fasting plasma glucose": "Fasting plasma glucose",
        "HDL-Cholesterol": "HDL-C",
        "HDL-C": "HDL-C",
        "Creatinine": "Creatinine",
        "HbA1c": "HbA1c",
        "LDL-C": "LDL-C",
        "LDL-Cholesterol": "LDL-C",
        "Kali": "Potassium",
        "Potassium": "Potassium",
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
        "unit_map_aliases": {"Fasting plasma glucose": "Fasting Blood Glucose"},
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
        "range_flag": "OK",
    }


def make_unit_rows(*, hgb_unit="g/L"):
    return [
        {"test_name": "WBC", "standardized_unit": "10^9/L"},
        {"test_name": "RBC", "standardized_unit": "10^12/L"},
        {"test_name": "HGB", "standardized_unit": hgb_unit},
        {"test_name": "Fasting Blood Glucose", "standardized_unit": "mmol/L"},
        {"test_name": "Creatinine", "standardized_unit": "µmol/L"},
        {"test_name": "HDL-Cholesterol", "standardized_unit": "mmol/L"},
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
    [("Glucose", "Fasting plasma glucose"), ("HDL-Cholesterol", "HDL-C"), ("Kali", "Potassium")],
)
def test_r05_alias_resolution(repository, alias, canonical):
    assert repository.resolve_analyte(alias) == canonical
    assert repository.resolve_analyte(f"  {alias.lower()}  ") == canonical


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


def test_unit_G_L_uppercase_maps_to_count() -> None:
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


def test_t01_ri_preferred_over_cdl(repository):
    result = repository.select_rule(
        analyte="Glucose",
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


def test_u02_unit_conflict_isolation():
    repo = ReferenceRepository(
        config=make_config(approved=["WBC", "HGB"], pending=[]),
        rules=[make_rule("WBC", unit="10^9/L"), make_rule("HGB", unit="10^9/L")],
        unit_rows=make_unit_rows(hgb_unit="g/L"),
    )

    hgb = repo.select_rule(analyte="HGB", unit="10^9/L", patient_gender="male", patient_age=35)
    wbc = repo.select_rule(analyte="WBC", unit="10^9/L", patient_gender="male", patient_age=35)

    assert hgb.reason == "unit_data_conflict"
    assert wbc.matched is True
