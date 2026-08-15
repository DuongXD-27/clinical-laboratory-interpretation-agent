# VMEC-05 Phase 2B Patch B — Glucose Conversion Evidence

## 1. Scope

Patch B implements only the software capability needed to compare a future
ARUP glucose critical rule expressed in `mg/dL` against an input measurement in
`mmol/L`. It adds one glucose-specific conversion utility and one explicit,
allowlisted Critical Detector dispatch path.

Patch B does not migrate production critical data, change Reference Range
behavior, add reverse conversion, or introduce a generic unit-conversion
framework.

## 2. Human-approved GLUCOSE-CONV-01

`GLUCOSE-CONV-01 = APPROVED` is implemented as frozen in
`docs/audit/VMEC05_GLUCOSE_CRITICAL_CONVERSION_CONTRACT.md`:

```text
value_mg_dl = Decimal(str(value_mmol_l)) * Decimal("180.1559") / Decimal("10")
```

The future source thresholds remain the ARUP literals `Decimal("55")` and
`Decimal("450")`; Patch B does not write them to production data.

## 3. Files changed

Patch B files:

- `src/services/measurement_conversion.py` — new conversion utility.
- `src/agents/nodes/critical_detector_node.py` — explicit safe dispatch and
  Decimal comparison support.
- `tests/test_services/test_measurement_conversion.py` — new exact conversion
  tests.
- `tests/test_agents/test_critical_detector_node.py` — future-record detector,
  safety, and regression tests.
- `docs/version-handoff/phase2b-patch-b-glucose-conversion-evidence.md` — this
  evidence record.

`tests/test_data/test_critical_data_quality.py` retains the accepted Patch A
working-tree changes and was rerun, but Patch B did not modify it.

## 4. Conversion implementation

`glucose_mmol_l_to_mg_dl()` accepts `float`, `str`, or `Decimal`, parses with
`Decimal(str(value))`, multiplies by `GLUCOSE_MW_NIST = Decimal("180.1559")`,
divides by `Decimal("10")`, and returns `Decimal`.

The source comment identifies NIST Chemistry WebBook, CAS 492-62-6, and
molecular weight 180.1559 g/mol. It explicitly limits NIST authority to the
molecular weight and does not attribute clinical critical thresholds to NIST.

Invalid, empty, and non-finite values raise `ValueError`. The detector catches
that error and skips critical evaluation, preserving fail-closed behavior.

## 5. Decimal arithmetic path

The approved conversion path remains Decimal through final comparison:

1. The original indicator value is passed to the converter.
2. The converter creates `Decimal(str(value))`.
3. Conversion uses `Decimal("180.1559") / Decimal("10")`.
4. Each active threshold is parsed directly from the source record using
   `Decimal(str(threshold_literal))`.
5. Patch A's explicit operator dispatcher compares `Decimal` to `Decimal`.

No converted value or source threshold is cast through `float`, rounded, or
quantized before comparison. Detector tests spy on the final dispatcher and
assert that both converted operands are `Decimal`.

## 6. Conversion dispatch safety

Cross-unit conversion is enabled only when all conditions are true:

- canonical analyte is exactly `Fasting plasma glucose`;
- `vmec_comparison_strategy` is exactly
  `CONVERT_INPUT_TO_SOURCE_UNIT`;
- normalized input unit is exactly `mmol/L`;
- normalized threshold/source unit is exactly `mg/dL`.

Dispatch is an explicit code branch. Configuration function names are not
dynamically executed; there is no `eval`, `globals`, dynamic import, or
configuration-driven `getattr`.

Tests prove the glucose converter is not called for Potassium, LDL-C,
unresolved analytes, `g/L` glucose, missing strategies, empty strategies, or an
unapproved strategy value.

## 7. Same-unit behavior

When input and threshold units normalize identically, the existing direct
comparison path is retained. Isolated future-record tests prove:

| Input | Rule | Result |
|---:|:---:|:---|
| 54.99 mg/dL | `< 55` | critical low |
| 55.00 mg/dL | `< 55` | not critical |
| 55.01 mg/dL | `< 55` | not critical |
| 449.99 mg/dL | `> 450` | not critical |
| 450.00 mg/dL | `> 450` | not critical |
| 450.01 mg/dL | `> 450` | critical high |

The tests replace the converter with a forbidden-call function, proving this
same-unit path does not convert.

## 8. Unsupported-unit fail-closed behavior

If normalized units differ and the four approved conversion conditions are not
all satisfied, the detector creates no critical alert and performs no raw
cross-unit numeric comparison.

Covered cases include glucose `g/L → mg/dL`, Potassium
`mmol/L → mg/dL`, LDL-C `mmol/L → mg/dL`, unresolved analytes, and missing or
unapproved strategy values.

## 9. Upstream unknown preservation

The Fix 1 upstream-`unknown` guard still runs before threshold lookup,
conversion dispatch, or operator comparison. A future FPG `mg/dL` record with
an upstream `unknown` assessment remains `unknown`, creates no alert, and calls
neither the converter nor comparison function.

Standalone same-unit component capability is not represented as current
end-to-end RI support for `mg/dL`. Patch B does not expand RI unit support.

The original patient measurement remains unchanged in the indicator and alert
fields. For converted alerts, comparison evidence in the message uses the
exact converted Decimal value and source unit.

## 10. Tests added

- Eight exact Decimal conversion results required by GLUCOSE-CONV-01.
- Five invalid/empty/non-finite conversion inputs.
- Six source-unit strict-boundary detector cases.
- Six converted strict-boundary detector cases.
- Final comparison operand-type assertions (`Decimal`/`Decimal`).
- Original alert measurement-field preservation.
- Glucose `g/L`, Potassium, LDL-C, and unresolved-analyte fail-closed cases.
- Exact strategy requirement cases.
- Upstream-`unknown` early-exit proof.
- A contextualized mmol/L RI-to-critical pipeline case proving a non-unknown
  upstream status can reach the approved isolated conversion fixture.
- All Patch A operator/null/legacy/alert tests and Fix 1 regression tests were
  rerun in the same detector module.

## 11. Commands run

```text
.venv\Scripts\python.exe -m pytest tests\test_services\test_measurement_conversion.py -v --basetemp .tmp\pytest-patch-b-conversion-final
.venv\Scripts\python.exe -m pytest tests\test_agents\test_critical_detector_node.py -v --basetemp .tmp\pytest-patch-b-detector-final
.venv\Scripts\python.exe -m pytest tests\test_agents\test_critical_detector_node.py -q --basetemp .tmp\pytest-patch-b-detector-final-2
.venv\Scripts\python.exe -m pytest tests\test_data\test_critical_data_quality.py -v --basetemp .tmp\pytest-patch-b-data
.venv\Scripts\python.exe -m pytest tests\test_agents tests\test_services tests\test_api -v --basetemp .tmp\pytest-patch-b-regression
.venv\Scripts\python.exe -m pytest tests -q --basetemp .tmp\pytest-patch-b-full
.venv\Scripts\python.exe -m ruff check src\services\measurement_conversion.py src\agents\nodes\critical_detector_node.py tests\test_services\test_measurement_conversion.py tests\test_agents\test_critical_detector_node.py
git diff --exit-code -- data/reference/critical_thresholds.json data/reference/reference_ranges.json data/reference/reference_checker_v2_config.json data/reference/units_metric.csv src/agents/nodes/reference_range_checker_node.py
Get-FileHash -Algorithm SHA256 <each protected file>
```

An additional `ruff format --check` diagnostic reported that the consolidated
Patch A detector/test files are not globally Ruff-formatted. No mass formatting
was applied because it would create broad unrelated churn. The required Ruff
lint check itself passed.

## 12. Actual results

- Conversion utility: **13 passed** in 1.96 seconds.
- Final Critical Detector run: **62 passed** in 6.77 seconds.
- Patch A data-quality suite: **18 passed** in 2.45 seconds.
- Agents/services/API regression: **269 passed** in 57.28 seconds.
- Ruff lint: **passed**.
- Protected-file Git diff check: **passed**.
- `git diff --check`: **passed**.

The first detector attempt had 60 passes and one failure in the optional
end-to-end test because the newly added fixture omitted patient age/sex. The RI
checker correctly returned `unknown`. The fixture was corrected to include the
required RI context, after which the complete detector module passed. No
conversion implementation assertion remained failing.

Optional repository-wide suite: **437 passed, 31 failed, 1 warning** in 88.19
seconds. The 31 failures are unrelated to Patch B and reproduce the known
checkout limitations: absent
`adult_outpatient_laboratory_reference_map.csv`, absent
`data/reference/quarantine_v2.csv`, and cascading data-build/evaluation
evidence failures. All Patch B tests and the required regression slice pass.

## 13. Known limitations

- Production glucose critical data still uses the pre-ARUP mmol/L record.
- Production does not yet declare `CONVERT_INPUT_TO_SOURCE_UNIT`; only isolated
  future-schema fixtures exercise the new conversion path.
- The Reference Range checker still does not support FPG `mg/dL`; end-to-end
  upstream `unknown` remains intentionally fail closed.
- Only mmol/L input to mg/dL source-unit conversion for canonical FPG is
  supported. There is no reverse or unrelated analyte conversion.
- Existing legacy non-conversion critical comparisons remain float-based during
  this transition; the approved converted path alone is Decimal end-to-end.
- Repository-wide data/evaluation tests require the absent source artifacts
  described above.

## 14. Production data unchanged proof

The protected files have no Git diff. Before and after SHA-256 values are
identical:

| Protected file | SHA-256 |
|---|---|
| `data/reference/critical_thresholds.json` | `9AF68E06B037CE327D27FFFA396BD4DEE289E1BFAE48B0E1DBFAF36EEB9E37AE` |
| `data/reference/reference_ranges.json` | `8606EC069E6EDE8ABD90BB969BFC6969FC9BCCCD3866192DE7459D36CD144A25` |
| `data/reference/reference_checker_v2_config.json` | `BEF8FE1E0084428C860D4A5C6B0631247312AEC0BE2BDE346D5BDFB2B918FB30` |
| `data/reference/units_metric.csv` | `10C03743DC14F36D7FEB84931CDB903F8A6BD74314C2A8D44C4EF5D064071903` |
| `src/agents/nodes/reference_range_checker_node.py` | `BF9549EFE37EAABF55AE89181CE5C49E6DEB606AB5AAC8BFD33697EA2A84B930` |

The generic alias remains exactly:

```json
"Glucose": "Fasting plasma glucose"
```

No production critical threshold data or ARUP provenance was migrated.

## Review flags

```text
PATCH_B_IMPLEMENTED = YES
GLUCOSE_CONV_01_IMPLEMENTED = YES
CONVERSION_AUTHORITY_NIST_180_1559 = YES
CONVERT_INPUT_TO_SOURCE_UNIT_IMPLEMENTED = YES
DECIMAL_USED_FOR_CONVERSION = YES
DECIMAL_USED_THROUGH_FINAL_CONVERTED_COMPARISON = YES
ROUNDING_BEFORE_COMPARISON = NO
RAW_CROSS_UNIT_COMPARISON_POSSIBLE = NO
UNAPPROVED_ANALYTE_CONVERSION_POSSIBLE = NO
UPSTREAM_UNKNOWN_PRESERVED = YES
PATCH_A_OPERATOR_BEHAVIOR_PRESERVED = YES
FIX1_SAFETY_INVARIANTS_PRESERVED = YES
REFERENCE_RANGE_CHANGED = NO
GENERIC_GLUCOSE_FPG_ALIAS_CHANGED = NO
CRITICAL_THRESHOLD_DATA_CHANGED = NO
ARUP_PRODUCTION_DATA_MIGRATED = NO
PATCH_B_TESTS_PASS = YES
READY_FOR_HUMAN_PATCH_B_REVIEW = YES
```

