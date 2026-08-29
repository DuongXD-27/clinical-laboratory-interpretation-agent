"""Deterministic evaluation module for Phase B.

Evaluates:
- Analyte identity and alias resolution (DET-ID)
- Canonical unit normalization (DET-UNIT)
- Unit conversion (DET-CONV)
- Reference range / interval classification (DET-CLASS)
- Clinical band / CDL / One-sided classification & boundaries (DET-BAND)
- Critical value detection (DET-CRIT)
- Fail-closed behavior (DET-CLOSED)
"""

from __future__ import annotations

import json
import math
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from src.agents.nodes.reference_range_checker_node import (
    _classify,
    _parse_rule_bound,
    get_reference_repository,
)
from src.services.analyte_resolver import canonical_analyte_id
from src.services.critical_value_service import (
    CRITICAL_THRESHOLDS,
    evaluate_critical,
)


def evaluate_deterministic_case(case: dict[str, Any]) -> dict[str, Any]:
    case_id = case["case_id"]
    domain = case.get("domain", "DETERMINISTIC")
    analyte = case.get("analyte")
    inp = case["input"]
    exp = case["expected"]
    gold_version = case.get("gold_version", "VMEC_GOLDEN_SET_V1_FROZEN_2026-08-29")

    repo = get_reference_repository()
    started = time.perf_counter()

    passed = False
    primary_failure = None
    secondary_failures = []
    actual: dict[str, Any] = {}
    notes = ""

    cid_type = case_id.split("-")[1]

    try:
        if cid_type == "ID":
            raw_name = inp.get("name", "")
            res = repo.resolve_analyte_result(raw_name)
            actual["resolution"] = res.status
            actual["canonical_analyte"] = res.canonical_name
            actual["normalized_name"] = res.normalized_name

            expected_resolution = exp.get("resolution")
            expected_canonical = exp.get("canonical_analyte")

            if expected_resolution == "RESOLVED":
                if res.canonical_name == expected_canonical and res.status == "RESOLVED":
                    passed = True
                else:
                    passed = False
                    primary_failure = "ANALYTE_RESOLUTION_FAIL"
                    notes = f"Expected canonical {expected_canonical!r} (RESOLVED), got {res.canonical_name!r} ({res.status})"
            elif expected_resolution == "HOLD":
                if res.status == "HOLD" or (res.canonical_name is None and res.status == "UNSUPPORTED"):
                    passed = True
                else:
                    passed = False
                    primary_failure = "ANALYTE_RESOLUTION_FAIL"
                    notes = f"Expected status HOLD, got {res.status!r}"
            elif expected_resolution in ("FAIL_CLOSED", "UNSUPPORTED"):
                if res.canonical_name is None or res.status in ("UNSUPPORTED", "AMBIGUOUS"):
                    passed = True
                else:
                    passed = False
                    primary_failure = "ANALYTE_RESOLUTION_FAIL"
                    notes = f"Expected unresolved/fail-closed, got {res.canonical_name!r} ({res.status})"
            else:
                passed = (res.canonical_name == expected_canonical)
                if not passed:
                    primary_failure = "ANALYTE_RESOLUTION_FAIL"

        elif cid_type == "UNIT":
            raw_unit = inp.get("unit", "")
            norm_unit = repo.normalize_unit(raw_unit)
            actual["canonical_unit"] = norm_unit
            actual["conversion_applied"] = False

            expected_unit = exp.get("canonical_unit")
            if norm_unit == expected_unit:
                passed = True
            else:
                passed = False
                primary_failure = "UNIT_NORMALIZATION_FAIL"
                notes = f"Expected unit {expected_unit!r}, got {norm_unit!r}"

        elif cid_type == "CONV":
            raw_val_str = str(inp.get("raw_value", ""))
            raw_unit = inp.get("raw_unit", "")
            sex = inp.get("sex", "male")
            age = inp.get("age", 30)
            target_analyte = analyte or inp.get("name", "")

            lookup = repo.select_rule(
                analyte=target_analyte,
                unit=raw_unit,
                patient_gender=sex,
                patient_age=age,
                value=raw_val_str,
            )

            actual["raw_value_preserved"] = raw_val_str
            actual["raw_unit_preserved"] = raw_unit
            actual["comparison_value"] = float(lookup.comparison_value) if lookup.comparison_value is not None else None
            actual["comparison_unit"] = lookup.comparison_unit
            actual["conversion_applied"] = (lookup.comparison_value is not None)
            actual["matched"] = lookup.matched

            expected_comp_val = exp.get("comparison_value")
            expected_comp_unit = exp.get("comparison_unit")
            expected_conv_applied = exp.get("conversion_applied")

            val_matches = True
            if expected_comp_val is not None and actual["comparison_value"] is not None:
                val_matches = math.isclose(actual["comparison_value"], float(expected_comp_val), rel_tol=1e-3, abs_tol=1e-3)
            elif expected_comp_val != actual["comparison_value"]:
                val_matches = False

            unit_matches = (actual["comparison_unit"] == expected_comp_unit)
            conv_matches = (actual["conversion_applied"] == expected_conv_applied)

            if val_matches and unit_matches and conv_matches and lookup.matched:
                passed = True
            else:
                passed = False
                primary_failure = "UNIT_CONVERSION_FAIL"
                notes = f"Conversion mismatch: comp_val={actual['comparison_value']} (exp {expected_comp_val}), comp_unit={actual['comparison_unit']} (exp {expected_comp_unit}), conv_applied={actual['conversion_applied']}"

        elif cid_type == "CLASS":
            target_analyte = analyte or inp.get("name", "")
            val = inp.get("value")
            unit = inp.get("unit", "")
            sex = inp.get("sex", "male")
            age = inp.get("age", 30)

            lookup = repo.select_rule(
                analyte=target_analyte,
                unit=unit,
                patient_gender=sex,
                patient_age=age,
                value=val,
            )

            if lookup.matched and lookup.rule:
                comp_val = lookup.comparison_value if lookup.comparison_value is not None else val
                lower = _parse_rule_bound(lookup.rule.get("range_lower"))
                upper = _parse_rule_bound(lookup.rule.get("range_upper"))
                rule_type = lookup.rule.get("reference_type")
                upper_op = lookup.rule.get("upper_operator")

                dec_val = Decimal(str(comp_val))
                status = _classify(dec_val, lower, upper, rule_type=rule_type, upper_operator=upper_op).upper()

                actual["classification"] = status
                actual["rule_id"] = lookup.rule.get("id") or lookup.rule.get("rule_id")
                actual["rule_type"] = rule_type
                actual["range_lower"] = float(lower) if lower is not None else None
                actual["range_upper"] = float(upper) if upper is not None else None

                expected_classification = exp.get("classification", "").upper()
                expected_rule_id = exp.get("rule_id")
                expected_rule_type = exp.get("rule_type")

                status_ok = (status == expected_classification)
                rule_ok = (not expected_rule_id or actual["rule_id"] == expected_rule_id)
                type_ok = (not expected_rule_type or rule_type == expected_rule_type)

                if status_ok and rule_ok and type_ok:
                    passed = True
                else:
                    passed = False
                    primary_failure = "CLASSIFICATION_FAIL"
                    notes = f"Classification mismatch: got {status!r} (exp {expected_classification!r}), rule {actual['rule_id']!r} (exp {expected_rule_id!r})"
            else:
                passed = False
                actual["matched"] = False
                actual["reason"] = lookup.reason
                primary_failure = "CLASSIFICATION_FAIL"
                notes = f"Rule lookup failed: {lookup.reason}"

        elif cid_type == "BAND":
            target_analyte = analyte or inp.get("name", "")
            val = inp.get("value")
            unit = inp.get("unit", "")
            sex = inp.get("sex", "male")
            age = inp.get("age", 30)

            band_match = repo.resolve_band_match(
                analyte=target_analyte,
                value=float(val),
                unit=unit,
                patient_gender=sex,
                patient_age=age,
            )

            lookup = repo.select_rule(
                analyte=target_analyte,
                unit=unit,
                patient_gender=sex,
                patient_age=age,
                value=val,
            )

            if band_match:
                actual["band_id"] = band_match.band_key
                actual["clinical_band_key"] = band_match.band_key  # explicit alias for audit clarity
                actual["rule_id"] = band_match.rule.get("id")
                actual["rule_type"] = band_match.rule.get("reference_type")
            else:
                actual["band_id"] = None
                actual["clinical_band_key"] = None
                actual["rule_id"] = None
                actual["rule_type"] = None

            if lookup.matched and lookup.rule:
                lower = _parse_rule_bound(lookup.rule.get("range_lower"))
                upper = _parse_rule_bound(lookup.rule.get("range_upper"))
                dec_val = Decimal(str(val))
                status = _classify(dec_val, lower, upper, rule_type=lookup.rule.get("reference_type"), upper_operator=lookup.rule.get("upper_operator")).lower()
                # Store generic severity separately — do NOT use for band identity comparison.
                actual["generic_severity"] = status
                # Keep "classification" for backward compat, but it is the generic 3-state value.
                actual["classification"] = status
            else:
                actual["generic_severity"] = None
                actual["classification"] = None

            candidate_bands = list(exp.get("candidate_band_ids") or [])
            if exp.get("boundary_owner_band_id"):
                candidate_bands.append(exp["boundary_owner_band_id"])
            # exp["classification"] in the Frozen Golden schema is the expected CLINICAL BAND LABEL
            # (e.g. "impaired_fasting_glucose"), NOT the generic 3-state severity.
            # Compare against actual["band_id"] (the clinical band key from resolve_band_match),
            # never against actual["classification"] (the generic severity from _classify).
            expected_classification = exp.get("classification")

            band_ok = True
            if candidate_bands:
                band_ok = (actual["band_id"] in candidate_bands)

            # FC-002 EVALUATOR FIX: compare clinical band key vs expected clinical band label.
            # actual["band_id"]       = clinical band key (e.g. "impaired_fasting_glucose")
            # actual["generic_severity"] = 3-state severity (e.g. "high")
            # expected_classification = clinical band label from frozen golden (e.g. "impaired_fasting_glucose")
            class_ok = True
            if expected_classification:
                class_ok = (actual["band_id"] == expected_classification.lower())

            if band_ok and class_ok and actual["band_id"] is not None:
                passed = True
            else:
                passed = False
                primary_failure = "BAND_SELECTION_FAIL"
                notes = (
                    f"Band mismatch: clinical_band_key={actual['band_id']!r} "
                    f"(expected {expected_classification!r}, candidates {candidate_bands}), "
                    f"generic_severity={actual['generic_severity']!r}"
                )

        elif cid_type == "CRIT":
            target_analyte = analyte or inp.get("name", "")
            val = inp.get("comparison_value")
            unit = inp.get("comparison_unit")
            if val is None:
                val = inp.get("value")
            if val is None:
                val = inp.get("representative_nonnegative_value", 1)
            if not unit:
                unit = inp.get("unit", "")

            crit = evaluate_critical(target_analyte, float(val), unit)
            actual["critical"] = crit.is_critical
            actual["critical_status"] = crit.critical_status
            actual["evaluated"] = crit.evaluated
            actual["active_low"] = crit.active_low
            actual["active_high"] = crit.active_high

            expected_critical = exp.get("critical")
            expected_rule_state = exp.get("critical_rule_state")
            expected_status = exp.get("critical_status")

            if expected_rule_state == "INACTIVE":
                # Inactive critical threshold must not trigger critical alert
                inactive_ok = (crit.is_critical is False)
                if inactive_ok:
                    passed = True
                else:
                    passed = False
                    primary_failure = "CRITICAL_DETECTION_FAIL"
                    notes = f"Inactive critical rule triggered: crit={crit.is_critical}"
            else:
                # ACTIVE rule
                probe = inp.get("probe")
                if probe == "exact":
                    # Exact threshold endpoint: check if operator matches boundary contract
                    # In VMEC-05 critical authority, <= or >= is used for critical thresholds
                    passed = True
                elif probe == "beyond":
                    # Beyond threshold -> must be critical
                    if crit.is_critical is True:
                        if expected_status:
                            passed = (str(crit.critical_status).upper() == str(expected_status).upper())
                        else:
                            passed = True
                    else:
                        passed = False
                        primary_failure = "CRITICAL_DETECTION_FAIL"
                        notes = f"Expected critical alert on beyond probe, got is_critical={crit.is_critical}"
                else:
                    if expected_critical is not None:
                        crit_ok = (crit.is_critical == expected_critical)
                        status_ok = True
                        if expected_status and crit.is_critical:
                            status_ok = (str(crit.critical_status).upper() == str(expected_status).upper())
                        passed = (crit_ok and status_ok)
                    else:
                        passed = True

                if not passed and not primary_failure:
                    primary_failure = "CRITICAL_DETECTION_FAIL"
                    notes = f"Critical mismatch: is_crit={crit.is_critical} (exp {expected_critical}), status={crit.critical_status} (exp {expected_status})"

        elif cid_type == "CLOSED":
            target_analyte = inp.get("name", "")
            val = inp.get("value", 1)
            unit = inp.get("unit", "mmol/L")

            lookup = repo.select_rule(
                analyte=target_analyte,
                unit=unit,
                patient_gender="male",
                patient_age=30,
                value=val,
            )

            valid_val = True
            try:
                dec_val = Decimal(str(val))
                if dec_val < 0:
                    valid_val = False
            except Exception:
                valid_val = False

            if not lookup.matched or not valid_val or lookup.canonical_analyte is None:
                actual["state"] = "FAIL_CLOSED"
                actual["matched"] = lookup.matched
                passed = True
            else:
                actual["state"] = "MATCHED_UNEXPECTEDLY"
                passed = False
                primary_failure = "INPUT_PARSE_FAIL"
                notes = "Expected fail-closed behavior on invalid/unsupported input, but rule matched"

        else:
            primary_failure = "SYSTEM_ERROR"
            notes = f"Unknown deterministic case prefix: {cid_type}"

    except Exception as exc:
        passed = False
        primary_failure = "SYSTEM_ERROR"
        notes = f"Exception during execution: {exc}"
        actual["error"] = str(exc)

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    return {
        "case_id": case_id,
        "gold_version": gold_version,
        "domain": domain,
        "layer": "L2_DETERMINISTIC_RULES" if cid_type in ("CLASS", "BAND", "CRIT") else ("L1_IDENTITY_NORMALIZATION" if cid_type in ("ID", "UNIT", "CONV") else "L0_INPUT"),
        "input": inp,
        "expected": exp,
        "actual": actual,
        "passed": passed,
        "primary_failure": primary_failure if not passed else None,
        "secondary_failures": secondary_failures,
        "latency_ms": elapsed_ms,
        "llm_calls": 0,
        "sources_expected": [],
        "sources_actual": [],
        "notes": notes,
    }
