"""Tests for Critical Detector Node safety and Phase 2B Patch A mechanics.

NOTE ON MEDICAL THRESHOLDS:
Tests in this file verify SOFTWARE MECHANICS ONLY (unit normalization, taxonomy handling,
canonicalization, fail-closed semantics, and sentinel guards).
They do NOT represent clinical endorsement or medical validation of the specific threshold numbers.
"""

import json
from decimal import Decimal
from types import SimpleNamespace

import pytest

import src.agents.nodes.critical_detector_node as critical_detector
from src.agents.nodes.critical_detector_node import detect_critical_values_node
from src.agents.nodes.reference_range_checker_node import reference_range_checker_node
from src.agents.state import AgentState


def _set_test_rule(monkeypatch, record: dict) -> None:
    monkeypatch.setattr(critical_detector, "CRITICAL_THRESHOLDS", {"potassium": record})


def _potassium_state(value: float) -> AgentState:
    return {
        "raw_indicators": [
            {"name": "Potassium", "value": value, "unit": "mmol/L"},
        ],
    }


def _future_glucose_rule(**overrides) -> dict:
    record = {
        "low": 55,
        "low_operator": "<",
        "high": 450,
        "high_operator": ">",
        "unit": "mg/dL",
        "vmec_comparison_strategy": "CONVERT_INPUT_TO_SOURCE_UNIT",
        "vmec_conversion_function": "glucose_mmol_l_to_mg_dl",
    }
    record.update(overrides)
    return record


def _set_future_glucose_rule(monkeypatch, **overrides) -> None:
    monkeypatch.setattr(
        critical_detector,
        "CRITICAL_THRESHOLDS",
        {"fasting plasma glucose": _future_glucose_rule(**overrides)},
    )


def _glucose_state(value: float, unit: str) -> AgentState:
    return {
        "raw_indicators": [
            {"name": "Fasting plasma glucose", "value": value, "unit": unit},
        ],
    }


@pytest.mark.asyncio
async def test_detect_critical_values_node_legacy_mock():
    """Test legacy critical value detector mock state execution."""
    mock_state: AgentState = {
        "raw_indicators": [
            {"name": "Kali", "value": 2.0, "unit": "mmol/L"},        # Production ARUP critical low (<3.0)
            {"name": "Fasting plasma glucose", "value": 30.5, "unit": "mmol/L"},  # Converts above production >450 mg/dL
            {"name": "LDL-C", "value": 3.2, "unit": "mmol/L"},       # Below critical high threshold
            {"name": "WBC", "value": 7.5, "unit": "10^9/L"},         # Within non-critical range
        ]
    }

    result_state = await detect_critical_values_node(mock_state)
    indicators = result_state.get("indicators", [])

    assert len(indicators) == 4

    kali = next(ind for ind in indicators if ind["name"] == "Kali")
    assert kali["status"] == "critical_low"
    assert kali["is_critical"] is True

    glucose = next(ind for ind in indicators if ind["name"] == "Fasting plasma glucose")
    assert glucose["status"] == "critical_high"
    assert glucose["is_critical"] is True

    ldl = next(ind for ind in indicators if ind["name"] == "LDL-C")
    assert ldl["status"] == "unknown"
    assert ldl.get("is_critical") is False

    wbc = next(ind for ind in indicators if ind["name"] == "WBC")
    assert wbc["status"] == "unknown"
    assert wbc.get("is_critical") is False

    assert result_state.get("has_critical_values") is True

    alerts = result_state.get("critical_alerts", [])
    assert len(alerts) == 2
    assert alerts[0]["indicator_name"] == "Kali"
    assert alerts[1]["indicator_name"] == "Fasting plasma glucose"


@pytest.mark.asyncio
async def test_kali_approved_checker_high_critical_detector_escalates():
    """Checker returns high; critical detector escalates to critical_high independently."""
    initial_state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Kali", "value": 7.0, "unit": "mmol/L"},
        ],
    }

    checked_state = await reference_range_checker_node(initial_state)
    checked_kali = checked_state["indicators"][0]
    assert checked_kali["status"] == "high"
    assert checked_kali["is_critical"] is False

    critical_state = await detect_critical_values_node({**initial_state, **checked_state})
    critical_kali = critical_state["indicators"][0]
    assert critical_kali["status"] == "critical_high"
    assert critical_kali["is_critical"] is True
    assert critical_state["has_critical_values"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (2.99, "critical_low"),
        (3.00, None),
        (3.01, None),
        (6.09, None),
        (6.10, None),
        (6.11, "critical_high"),
    ],
)
async def test_potassium_exact_critical_boundaries_software_execution(value, expected_status):
    """Production ARUP rule executes strict <3.0 and >6.1 boundaries."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "Potassium", "value": value, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)
    potassium = result["indicators"][0]
    if expected_status is None:
        assert potassium["status"] not in {"critical_low", "critical_high"}
        assert potassium["is_critical"] is False
        assert result["critical_alerts"] == []
    else:
        assert potassium["status"] == expected_status
        assert potassium["is_critical"] is True


# ===========================================================================
# Phase 2B Patch A: Explicit Operator Dispatch
# ===========================================================================

@pytest.mark.parametrize(
    ("value", "threshold", "operator", "expected"),
    [
        (2.99, 3.0, "<", True),
        (3.00, 3.0, "<", False),
        (3.00, 3.0, "<=", True),
        (6.11, 6.1, ">", True),
        (6.10, 6.1, ">", False),
        (6.10, 6.1, ">=", True),
    ],
)
def test_explicit_operator_dispatch(value, threshold, operator, expected):
    assert critical_detector._compare_critical(value, threshold, operator) is expected


@pytest.mark.parametrize(
    "operator",
    ["==", "DROP TABLE", "", "approximately", None, ["<"]],
)
@pytest.mark.asyncio
async def test_invalid_operator_fails_closed_without_alert(monkeypatch, operator):
    _set_test_rule(monkeypatch, {
        "low": 3.0,
        "low_operator": operator,
        "high": None,
        "high_operator": None,
        "unit": "mmol/L",
    })

    result = await detect_critical_values_node(_potassium_state(2.0))
    indicator = result["indicators"][0]

    assert indicator["status"] == "unknown"
    assert indicator["is_critical"] is False
    assert result["has_critical_values"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_null_low_side_is_inactive_while_high_side_still_executes(monkeypatch):
    _set_test_rule(monkeypatch, {
        "low": None,
        "low_operator": None,
        "high": 6.1,
        "high_operator": ">",
        "unit": "mmol/L",
    })

    low_result = await detect_critical_values_node(_potassium_state(-999.0))
    assert low_result["indicators"][0]["is_critical"] is False
    assert low_result["critical_alerts"] == []

    high_result = await detect_critical_values_node(_potassium_state(6.11))
    assert high_result["indicators"][0]["status"] == "critical_high"
    assert high_result["indicators"][0]["is_critical"] is True
    assert len(high_result["critical_alerts"]) == 1


@pytest.mark.asyncio
async def test_null_null_record_is_inactive_without_crash(monkeypatch):
    _set_test_rule(monkeypatch, {
        "low": None,
        "low_operator": None,
        "high": None,
        "high_operator": None,
        "unit": "mmol/L",
    })

    result = await detect_critical_values_node(_potassium_state(999.0))

    assert result["indicators"][0]["status"] == "unknown"
    assert result["indicators"][0]["is_critical"] is False
    assert result["has_critical_values"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_legacy_migration_compatibility_missing_operators_defaults_inclusive(monkeypatch):
    """LEGACY_MIGRATION_COMPATIBILITY: missing operators temporarily mean <= / >=."""
    _set_test_rule(monkeypatch, {
        "low": 3.0,
        "high": 6.1,
        "unit": "mmol/L",
    })

    low_result = await detect_critical_values_node(_potassium_state(3.0))
    high_result = await detect_critical_values_node(_potassium_state(6.1))

    assert low_result["indicators"][0]["status"] == "critical_low"
    assert "3.0 <= 3.0 mmol/L" in low_result["critical_alerts"][0]["message"]
    assert high_result["indicators"][0]["status"] == "critical_high"
    assert "6.1 >= 6.1 mmol/L" in high_result["critical_alerts"][0]["message"]


@pytest.mark.asyncio
async def test_future_provenance_fields_load_and_execute(tmp_path, monkeypatch):
    record = {
        "low": 3.0,
        "low_operator": "<",
        "high": 6.1,
        "high_operator": ">",
        "unit": "mmol/L",
        "source_id": "SRC-CRIT-ARUP-REV46",
        "source_title": "CRITICAL VALUES LIST",
        "source_document_id": "CORP-APPEND-0104A",
        "source_revision": "46",
        "source_date": "2026-04",
        "source_url": "https://www.aruplab.com/files/resources/testing/ARUP_Critical_Values.pdf",
        "source_page": 1,
        "source_literal": "<3.0 or >6.1 mmol/L",
        "source_analyte_label": "Potassium",
        "population_context": None,
        "qualifier": None,
    }
    config_path = tmp_path / "critical_thresholds.json"
    config_path.write_text(json.dumps({"Potassium": record}), encoding="utf-8")
    monkeypatch.setattr(
        critical_detector,
        "get_settings",
        lambda: SimpleNamespace(critical_thresholds_path=str(config_path)),
    )

    loaded = critical_detector.load_critical_thresholds()
    assert loaded["potassium"]["source_revision"] == "46"
    assert loaded["potassium"]["qualifier"] is None

    monkeypatch.setattr(critical_detector, "CRITICAL_THRESHOLDS", loaded)
    result = await detect_critical_values_node(_potassium_state(2.99))

    assert result["indicators"][0]["status"] == "critical_low"
    assert result["indicators"][0]["is_critical"] is True


@pytest.mark.parametrize(
    ("record", "value", "expected_fragment"),
    [
        (
            {
                "low": 3.0,
                "low_operator": "<",
                "high": None,
                "high_operator": None,
                "unit": "mmol/L",
            },
            2.99,
            "2.99 < 3.0 mmol/L",
        ),
        (
            {
                "low": None,
                "low_operator": None,
                "high": 6.1,
                "high_operator": ">",
                "unit": "mmol/L",
            },
            6.11,
            "6.11 > 6.1 mmol/L",
        ),
    ],
)
@pytest.mark.asyncio
async def test_alert_text_renders_explicit_operator(monkeypatch, record, value, expected_fragment):
    _set_test_rule(monkeypatch, record)

    result = await detect_critical_values_node(_potassium_state(value))

    assert expected_fragment in result["critical_alerts"][0]["message"]


# ===========================================================================
# Phase 2B Patch B: GLUCOSE-CONV-01
# ===========================================================================

@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (54.99, "critical_low"),
        (55.00, None),
        (55.01, None),
        (449.99, None),
        (450.00, None),
        (450.01, "critical_high"),
    ],
)
@pytest.mark.asyncio
async def test_production_glucose_source_unit_direct_strict_boundaries(
    monkeypatch,
    value,
    expected_status,
):
    def forbidden_converter(_value):
        raise AssertionError("same-unit mg/dL comparison must not convert")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)

    result = await detect_critical_values_node(_glucose_state(value, "mg/dL"))
    indicator = result["indicators"][0]

    if expected_status is None:
        assert indicator["status"] not in {"critical_low", "critical_high"}
        assert indicator["is_critical"] is False
        assert result["critical_alerts"] == []
    else:
        assert indicator["status"] == expected_status
        assert indicator["is_critical"] is True


@pytest.mark.parametrize(
    ("value", "expected_status"),
    [
        (3.050, "critical_low"),
        (3.053, None),
        (3.054, None),
        (3.055, None),
        (24.97, None),
        (24.99, "critical_high"),
    ],
)
@pytest.mark.asyncio
async def test_production_glucose_mmol_l_conversion_strict_boundaries_use_decimal(
    monkeypatch,
    value,
    expected_status,
):
    original_compare = critical_detector._compare_critical
    compared_operands = []

    def capture_compare(comparison_value, threshold, operator):
        compared_operands.append((comparison_value, threshold, operator))
        return original_compare(comparison_value, threshold, operator)

    monkeypatch.setattr(critical_detector, "_compare_critical", capture_compare)

    result = await detect_critical_values_node(_glucose_state(value, "mmol/L"))
    indicator = result["indicators"][0]

    assert compared_operands
    assert all(isinstance(compared_value, Decimal) for compared_value, _, _ in compared_operands)
    assert all(isinstance(threshold, Decimal) for _, threshold, _ in compared_operands)
    if expected_status is None:
        assert indicator["status"] not in {"critical_low", "critical_high"}
        assert indicator["is_critical"] is False
        assert result["critical_alerts"] == []
    else:
        assert indicator["status"] == expected_status
        assert indicator["is_critical"] is True


@pytest.mark.asyncio
async def test_converted_alert_preserves_original_measurement_fields(monkeypatch):
    result = await detect_critical_values_node(_glucose_state(3.050, "mmol/L"))
    alert = result["critical_alerts"][0]

    assert alert["value"] == 3.050
    assert alert["unit"] == "mmol/L"
    assert "54.9475495 < 55 mg/dL" in alert["message"]


@pytest.mark.asyncio
async def test_glucose_g_l_has_no_approved_conversion_and_fails_closed(monkeypatch):
    _set_future_glucose_rule(monkeypatch)

    def forbidden_converter(_value):
        raise AssertionError("glucose converter must not run for g/L")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)

    result = await detect_critical_values_node(_glucose_state(27.8, "g/L"))

    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_potassium_cannot_use_glucose_converter_with_fake_strategy(monkeypatch):
    _set_test_rule(monkeypatch, _future_glucose_rule())

    def forbidden_converter(_value):
        raise AssertionError("glucose converter must not run for Potassium")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)

    result = await detect_critical_values_node(_potassium_state(2.0))

    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_ldl_c_cannot_use_glucose_converter_with_fake_strategy(monkeypatch):
    monkeypatch.setattr(
        critical_detector,
        "CRITICAL_THRESHOLDS",
        {"ldl-c": _future_glucose_rule()},
    )

    def forbidden_converter(_value):
        raise AssertionError("glucose converter must not run for LDL-C")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)
    state: AgentState = {
        "raw_indicators": [
            {"name": "LDL-C", "value": 2.0, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)

    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_unresolved_analyte_cannot_use_glucose_converter_or_raw_rule(monkeypatch):
    monkeypatch.setattr(
        critical_detector,
        "CRITICAL_THRESHOLDS",
        {"unknown glucose analyte": _future_glucose_rule()},
    )

    def forbidden_converter(_value):
        raise AssertionError("glucose converter must not run for unresolved analyte")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)
    state: AgentState = {
        "raw_indicators": [
            {"name": "Unknown glucose analyte", "value": 3.0, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)

    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.parametrize("strategy", [None, "", "CONVERT_SOURCE_TO_INPUT_UNIT"])
@pytest.mark.asyncio
async def test_glucose_conversion_requires_exact_approved_strategy(monkeypatch, strategy):
    _set_future_glucose_rule(monkeypatch, vmec_comparison_strategy=strategy)

    def forbidden_converter(_value):
        raise AssertionError("glucose converter must not run without approved strategy")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_converter)

    result = await detect_critical_values_node(_glucose_state(3.0, "mmol/L"))

    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_future_glucose_upstream_unknown_skips_comparison_and_conversion(monkeypatch):
    _set_future_glucose_rule(monkeypatch)

    def forbidden_path(*_args):
        raise AssertionError("critical evaluation must not run after upstream unknown")

    monkeypatch.setattr(critical_detector, "glucose_mmol_l_to_mg_dl", forbidden_path)
    monkeypatch.setattr(critical_detector, "_compare_critical", forbidden_path)
    state: AgentState = {
        "indicators": [
            {
                "name": "Fasting plasma glucose",
                "value": 50.0,
                "unit": "mg/dL",
                "reference_low": None,
                "reference_high": None,
                "status": "unknown",
                "is_abnormal": False,
                "is_critical": False,
            },
        ],
    }

    result = await detect_critical_values_node(state)

    assert result["indicators"][0]["status"] == "unknown"
    assert result["indicators"][0]["is_critical"] is False
    assert result["critical_alerts"] == []


@pytest.mark.asyncio
async def test_production_glucose_mmol_l_pipeline_can_escalate_non_unknown():
    state: AgentState = {
        **_glucose_state(3.050, "mmol/L"),
        "patient_age": 35,
        "patient_gender": "male",
    }

    ri_state = await reference_range_checker_node(state)
    assert ri_state["indicators"][0]["status"] != "unknown"

    result = await detect_critical_values_node({**state, **ri_state})

    assert result["indicators"][0]["status"] == "critical_low"
    assert result["indicators"][0]["is_critical"] is True


@pytest.mark.parametrize(
    ("name", "value", "unit"),
    [
        ("WBC", 35.0, "10^9/L"),
        ("HGB", 200.0, "g/L"),
        ("LDL-C", 5.3, "mmol/L"),
        ("HbA1c", 10.0, "%"),
        ("HDL-C", 0.5, "mmol/L"),
        ("Creatinine", 400.0, "umol/L"),
        ("RBC", 100.0, "10^12/L"),
    ],
)
@pytest.mark.asyncio
async def test_production_inactive_analytes_never_create_critical_alert(name, value, unit):
    state: AgentState = {
        "raw_indicators": [
            {"name": name, "value": value, "unit": unit},
        ],
    }

    result = await detect_critical_values_node(state)

    assert result["indicators"][0]["is_critical"] is False
    assert result["indicators"][0]["status"] not in {"critical_low", "critical_high"}
    assert result["has_critical_values"] is False
    assert result["critical_alerts"] == []


@pytest.mark.parametrize(
    "name",
    [
        "Fasting plasma glucose",
        "Fasting Blood Glucose",
        "Đường huyết lúc đói",
        "Glucose máu lúc đói",
    ],
)
@pytest.mark.asyncio
async def test_existing_fpg_aliases_reach_one_production_canonical_rule(name):
    state: AgentState = {
        "raw_indicators": [
            {"name": name, "value": 3.050, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)

    assert result["indicators"][0]["status"] == "critical_low"
    assert result["indicators"][0]["is_critical"] is True


# ===========================================================================
# Check 1 & Blocker 01: Canonical Analyte Equivalence & No Raw-Name Bypass
# ===========================================================================

@pytest.mark.asyncio
async def test_canonical_analyte_equivalence_potassium_and_kali():
    """Software check: 'Potassium' and 'Kali' resolve to same canonical and produce identical critical results."""
    state_potassium: AgentState = {
        "raw_indicators": [{"name": "Potassium", "value": 2.0, "unit": "mmol/L"}],
    }
    state_kali: AgentState = {
        "raw_indicators": [{"name": "Kali", "value": 2.0, "unit": "mmol/L"}],
    }

    res_potassium = await detect_critical_values_node(state_potassium)
    res_kali = await detect_critical_values_node(state_kali)

    ind_p = res_potassium["indicators"][0]
    ind_k = res_kali["indicators"][0]

    assert ind_p["status"] == "critical_low"
    assert ind_k["status"] == "critical_low"
    assert ind_p["is_critical"] is True
    assert ind_k["is_critical"] is True


@pytest.mark.asyncio
async def test_canonical_analyte_equivalence_hgb_and_hemoglobin():
    """HGB aliases resolve identically to the inactive production rule."""
    state_hgb: AgentState = {
        "raw_indicators": [{"name": "HGB", "value": 50.0, "unit": "g/L"}],
    }
    state_hemo: AgentState = {
        "raw_indicators": [{"name": "Hemoglobin", "value": 50.0, "unit": "g/L"}],
    }

    res_hgb = await detect_critical_values_node(state_hgb)
    res_hemo = await detect_critical_values_node(state_hemo)

    assert res_hgb["indicators"][0]["status"] == "unknown"
    assert res_hemo["indicators"][0]["status"] == "unknown"
    assert res_hgb["indicators"][0]["is_critical"] is False
    assert res_hemo["indicators"][0]["is_critical"] is False
    assert res_hgb["critical_alerts"] == []
    assert res_hemo["critical_alerts"] == []


@pytest.mark.asyncio
async def test_unresolvable_analyte_cannot_bypass_canonicalization_via_raw_lookup():
    """Blocker 01: An unresolvable analyte name cannot trigger critical evaluation even if raw name matches a key."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "Unknown_Unapproved_Analyte", "value": 999.0, "unit": "mmol/L"},
            {"name": "SomeRandomKey", "value": 1.0, "unit": "g/L"},
        ],
    }

    result = await detect_critical_values_node(state)
    for ind in result["indicators"]:
        assert ind["is_critical"] is False
        assert ind["status"] not in {"critical_high", "critical_low"}

    assert result["has_critical_values"] is False
    assert len(result["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_generic_glucose_has_no_standalone_raw_name_critical_fallback():
    """Fix 2: generic Glucose is unresolved and cannot reach the FPG rule by raw name."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "Glucose", "value": 3.0, "unit": "mmol/L"},
        ],
    }

    result = await detect_critical_values_node(state)
    glucose = result["indicators"][0]

    assert glucose["status"] == "unknown"
    assert glucose["is_critical"] is False
    assert result["has_critical_values"] is False
    assert result["critical_alerts"] == []


# ===========================================================================
# Check 2 & Blocker 02: Upstream Unknown Preservation (No Critical Escalation)
# ===========================================================================

@pytest.mark.asyncio
async def test_upstream_unknown_is_not_overwritten_by_critical_detector():
    """Blocker 02: If upstream RI checker returned 'unknown', critical detector must NOT escalate it to critical."""
    state: AgentState = {
        "indicators": [
            {
                "name": "Potassium",
                "value": 7.0,
                "unit": "mEq/L",
                "reference_low": None,
                "reference_high": None,
                "status": "unknown",
                "is_abnormal": False,
                "is_critical": False,
            }
        ]
    }

    result = await detect_critical_values_node(state)
    potassium = result["indicators"][0]

    assert potassium["status"] == "unknown"
    assert potassium["is_critical"] is False
    assert result["has_critical_values"] is False
    assert len(result["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_pipeline_potassium_meq_returns_unknown_end_to_end():
    """Blocker 02 & 03: Potassium 6.5 mEq/L in full pipeline returns RI unknown and is NOT escalated to critical."""
    state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Potassium", "value": 6.5, "unit": "mEq/L"},
        ],
    }

    ri_state = await reference_range_checker_node(state)
    assert ri_state["indicators"][0]["status"] == "unknown"

    critical_state = await detect_critical_values_node({**state, **ri_state})
    potassium = critical_state["indicators"][0]

    assert potassium["status"] == "unknown"
    assert potassium["is_critical"] is False
    assert critical_state["has_critical_values"] is False
    assert len(critical_state["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_pipeline_unsupported_wbc_unit_returns_unknown_end_to_end():
    """Blocker 02: WBC 35.0 mg/dL in full pipeline returns RI unknown and is NOT escalated to critical."""
    state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "WBC", "value": 35.0, "unit": "mg/dL"},
        ],
    }

    ri_state = await reference_range_checker_node(state)
    assert ri_state["indicators"][0]["status"] == "unknown"

    critical_state = await detect_critical_values_node({**state, **ri_state})
    wbc = critical_state["indicators"][0]

    assert wbc["status"] == "unknown"
    assert wbc["is_critical"] is False
    assert critical_state["has_critical_values"] is False
    assert len(critical_state["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_pipeline_potassium_6500_umol_returns_unknown_end_to_end():
    """Blocker 02: Potassium 6500 umol/L in full pipeline returns RI unknown and is NOT escalated to critical."""
    state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Potassium", "value": 6500.0, "unit": "umol/L"},
        ],
    }

    ri_state = await reference_range_checker_node(state)
    assert ri_state["indicators"][0]["status"] == "unknown"

    critical_state = await detect_critical_values_node({**state, **ri_state})
    potassium = critical_state["indicators"][0]

    assert potassium["status"] == "unknown"
    assert potassium["is_critical"] is False
    assert critical_state["has_critical_values"] is False
    assert len(critical_state["critical_alerts"]) == 0


# ===========================================================================
# Check 3 & Blocker 03: Shared Normalizer Reuse (No Local Unit Exceptions)
# ===========================================================================

@pytest.mark.asyncio
async def test_shared_unit_normalizer_aliases_execute_correctly(monkeypatch):
    """Fix 1 regression uses isolated active rules; production WBC/Creatinine remain inactive."""
    monkeypatch.setattr(
        critical_detector,
        "CRITICAL_THRESHOLDS",
        {
            "wbc": {
                "low": None,
                "low_operator": None,
                "high": 30.0,
                "high_operator": ">=",
                "unit": "10^9/L",
            },
            "creatinine": {
                "low": None,
                "low_operator": None,
                "high": 353.6,
                "high_operator": ">=",
                "unit": "umol/L",
            },
        },
    )
    state: AgentState = {
        "raw_indicators": [
            {"name": "WBC", "value": 35.0, "unit": "G/L"},              # G/L normalized to 10^9/L by shared normalizer
            {"name": "WBC", "value": 35.0, "unit": "×10^9/L"},          # Symbol normalized to 10^9/L
            {"name": "Creatinine", "value": 400.0, "unit": "µmol/L"},    # Unicode µ normalized to umol/L
        ],
    }

    result = await detect_critical_values_node(state)
    inds = result["indicators"]

    assert inds[0]["status"] == "critical_high"
    assert inds[0]["is_critical"] is True
    assert inds[1]["status"] == "critical_high"
    assert inds[1]["is_critical"] is True
    assert inds[2]["status"] == "critical_high"
    assert inds[2]["is_critical"] is True


@pytest.mark.asyncio
async def test_convertible_units_without_converters_fail_closed_standalone():
    """Blocker 03: unsupported cross-unit inputs fail closed without raw comparison."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "Potassium", "value": 6500.0, "unit": "umol/L"},   # 6500 µmol/L = 6.5 mmol/L, must NOT raw compare 6500 >= 6.5
            {"name": "Fasting plasma glucose", "value": 27.8, "unit": "g/L"},  # No approved g/L -> mg/dL glucose conversion
            {"name": "HGB", "value": 60.0, "unit": "g/dL"},            # 60 g/dL = 600 g/L, must NOT raw compare 60 <= 60
            {"name": "LDL-C", "value": 5.0, "unit": "mg/dL"},           # 5.0 mg/dL != 5.0 mmol/L
            {"name": "Potassium", "value": 6.5, "unit": "mEq/L"},       # mEq/L is not in shared normalize_unit in V1 -> fail closed
        ],
    }

    result = await detect_critical_values_node(state)
    inds = {f"{i['name']}_{i['unit']}": i for i in result["indicators"]}

    for key in [
        "Potassium_umol/L",
        "Fasting plasma glucose_g/L",
        "HGB_g/dL",
        "LDL-C_mg/dL",
        "Potassium_mEq/L",
    ]:
        assert inds[key]["is_critical"] is False
        assert inds[key]["status"] not in {"critical_high", "critical_low"}

    assert result["has_critical_values"] is False
    assert len(result["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_production_registry_only_active_analytes_execute():
    """Canonical units do not activate analytes whose production rules are inactive."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "Potassium", "value": 6.5, "unit": "mmol/L"},
            {"name": "HGB", "value": 60.0, "unit": "g/L"},
            {"name": "WBC", "value": 35.0, "unit": "10^9/L"},
        ],
    }

    result = await detect_critical_values_node(state)
    inds = {i["name"]: i for i in result["indicators"]}

    assert inds["Potassium"]["status"] == "critical_high"
    assert inds["HGB"]["status"] == "unknown"
    assert inds["HGB"]["is_critical"] is False
    assert inds["WBC"]["status"] == "unknown"
    assert inds["WBC"]["is_critical"] is False


# ===========================================================================
# Production inactive null-side regression
# ===========================================================================

@pytest.mark.asyncio
@pytest.mark.parametrize(
    "value",
    [-1.0, 0.0, 0.5, 4.5, 10.0, 100.0],
)
async def test_production_null_inactive_rbc_never_triggers(value):
    """RBC's explicit null/null production rule never triggers a critical alert."""
    state: AgentState = {
        "raw_indicators": [
            {"name": "RBC", "value": value, "unit": "10^12/L"},
        ],
    }

    result = await detect_critical_values_node(state)
    rbc = result["indicators"][0]
    assert rbc["is_critical"] is False
    assert rbc["status"] not in {"critical_high", "critical_low"}
    assert result["has_critical_values"] is False
    assert len(result["critical_alerts"]) == 0


# ===========================================================================
# Non-Critical Happy Paths Preserved
# ===========================================================================

@pytest.mark.asyncio
async def test_non_critical_happy_paths_preserve_existing_ri_status():
    """Software check: indicators within non-critical range retain their RI checker status without false critical alerts."""
    state_normal: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Potassium", "value": 4.2, "unit": "mmol/L"},
            {"name": "WBC", "value": 7.0, "unit": "10^9/L"},
            {"name": "HGB", "value": 150.0, "unit": "g/L"},
        ],
    }

    checked_state = await reference_range_checker_node(state_normal)
    critical_state = await detect_critical_values_node({**state_normal, **checked_state})

    for ind in critical_state["indicators"]:
        assert ind["status"] == "normal"
        assert ind["is_critical"] is False

    assert critical_state["has_critical_values"] is False
    assert len(critical_state["critical_alerts"]) == 0


@pytest.mark.asyncio
async def test_non_critical_high_ri_status_not_escalated_if_below_critical_threshold():
    """Potassium 5.5 is RI-high but below the strict production critical rule >6.1."""
    state: AgentState = {
        "patient_age": 35,
        "patient_gender": "male",
        "raw_indicators": [
            {"name": "Potassium", "value": 5.5, "unit": "mmol/L"},
        ],
    }

    checked_state = await reference_range_checker_node(state)
    assert checked_state["indicators"][0]["status"] == "high"

    critical_state = await detect_critical_values_node({**state, **checked_state})
    potassium = critical_state["indicators"][0]

    assert potassium["status"] == "high"
    assert potassium["is_critical"] is False
    assert critical_state["has_critical_values"] is False
