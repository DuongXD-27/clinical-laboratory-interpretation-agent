# VMEC-05 Phase 2B Patch A — Critical Schema Operator Evidence

## 1. Scope

Patch A adds software capability for explicit critical-rule operators, `null`
inactive sides, future provenance fields, and staged final-schema validation.
It intentionally does not migrate ARUP data, alter medical threshold numbers,
add Glucose conversion, or change reference-range behavior.

The Critical Detector already contained the Fix 1 canonicalization, upstream
`unknown`, and unit-safety work in the working tree. Patch A was layered on
that work without removing those invariants.

## 2. Files changed

- `src/agents/nodes/critical_detector_node.py`
- `tests/test_agents/test_critical_detector_node.py`
- `tests/test_data/test_critical_data_quality.py`
- `docs/version-handoff/phase2b-patch-a-critical-schema-operator-evidence.md`

No production data file was edited by Patch A.

## 3. Before behavior

- Low comparisons were effectively hard-coded as `value <= low`.
- High comparisons were effectively hard-coded as `value >= high`.
- Strict ARUP boundaries (`<` and `>`) were not representable.
- Alert evidence hard-coded `<=` or `>=`.
- There was no explicit final-schema validation model for threshold/operator
  pairs or required provenance fields.

## 4. After behavior

- An active side may execute one of `<`, `<=`, `>`, or `>=` exactly.
- `null` thresholds are inactive and never compare or alert.
- Invalid operators fail closed on their own side without preventing a valid
  opposite side from executing.
- Alert text renders the exact explicit or resolved migration operator.
- Unknown extra record fields, including the future provenance fields, remain
  available after loading and do not interfere with detection.
- Final-schema validation is represented and tested using samples without
  prematurely enforcing it against the unmigrated production JSON.

## 5. Operator dispatch implementation

`_compare_critical(value, threshold, operator)` uses explicit deterministic
branches for the four allowlisted operators. It does not use `eval`, dynamic
execution, or operator-string interpolation.

`_resolve_active_side(record, side)` resolves an executable
`(threshold, operator)` pair. Explicit operators are used exactly. Invalid
strings, explicit `null`, and non-string JSON values fail closed.

Verified boundary cases:

| Value | Threshold | Operator | Result |
|---:|---:|:---:|:---:|
| 2.99 | 3.0 | `<` | trigger |
| 3.00 | 3.0 | `<` | no trigger |
| 3.00 | 3.0 | `<=` | trigger |
| 6.11 | 6.1 | `>` | trigger |
| 6.10 | 6.1 | `>` | no trigger |
| 6.10 | 6.1 | `>=` | trigger |

## 6. Null-side behavior

- `threshold == null` makes that side inactive.
- `threshold == null` plus `operator == null` performs no comparison and
  creates no alert.
- A `null` low side does not block an active valid high side.
- A `null`/`null` rule record is safe and creates no alert.
- A non-null operator paired with a `null` threshold is ignored and logged as
  invalid configuration.

Current negative `-1` inactive sentinels remain temporarily non-executable for
migration compatibility. They are not accepted by final-schema validation.

## 7. Legacy migration compatibility

Missing operator fields on current active legacy records use the temporary
`LEGACY_OPERATOR_DEFAULT` behavior:

- low defaults to `<=`
- high defaults to `>=`

The compatibility test is explicitly named and documented as
`LEGACY_MIGRATION_COMPATIBILITY`. This is not a permanent schema contract.
After the Patch C production migration, active production rules must contain
explicit operators. Final validation must then be enforced against production
data; negative sentinel rejection becomes mandatory when the corresponding
Patch C/E data migration removes those sentinels.

## 8. Provenance compatibility

A threshold record containing the planned fields was loaded from a temporary
JSON file, retained intact, and executed successfully:

- `source_id`
- `source_title`
- `source_document_id`
- `source_revision`
- `source_date`
- `source_url`
- `source_page`
- `source_literal`
- `source_analyte_label`
- `population_context`
- `qualifier`

No ARUP provenance was added to production JSON in this patch.

## 9. Tests added

- Exact dispatch and strict-boundary cases for all four operators.
- Invalid-operator fail-closed cases for `==`, `DROP TABLE`, empty string,
  an unknown string, explicit `null`, and a non-string JSON array.
- Inactive low side with an independently active high side.
- Fully inactive `null`/`null` record.
- Explicitly labeled legacy default compatibility.
- Future provenance-field load and execution.
- Exact `<` and `>` alert rendering.
- Current migration-compatibility validation against production data.
- Final-schema sample validation for active/inactive operator pairs, invalid
  `=`, negative sentinels, and provenance completeness.
- Existing Fix 1 regression coverage remains in the detector test module.

## 10. Commands run

```text
.venv\Scripts\python.exe -m pytest tests\test_agents\test_critical_detector_node.py -v --basetemp .tmp\pytest-patch-a-agent-2
.venv\Scripts\python.exe -m pytest tests\test_data\test_critical_data_quality.py -v --basetemp .tmp\pytest-patch-a-data
.venv\Scripts\python.exe -m pytest tests\test_agents tests\test_services tests\test_api -v --basetemp .tmp\pytest-patch-a-regression
.venv\Scripts\python.exe -m pytest tests\test_agents\test_critical_detector_node.py -q --basetemp .tmp\pytest-patch-a-agent-final
.venv\Scripts\python.exe -m pytest tests\test_data\test_critical_data_quality.py -q --basetemp .tmp\pytest-patch-a-data-final
.venv\Scripts\python.exe -m pytest tests\test_agents tests\test_services tests\test_api -q --basetemp .tmp\pytest-patch-a-regression-final
.venv\Scripts\python.exe -m ruff check src\agents\nodes\critical_detector_node.py tests\test_agents\test_critical_detector_node.py tests\test_data\test_critical_data_quality.py
.venv\Scripts\python.exe -m pytest tests -q --basetemp .tmp\pytest-patch-a-full
git diff --exit-code -- data/reference/critical_thresholds.json
Get-FileHash -Algorithm SHA256 data\reference\critical_thresholds.json
```

Two initial focused-test attempts were also made before the workspace-local
temporary directory existed. They stopped during pytest temporary-directory
setup (`PermissionError` for the user temp root, then a missing `.tmp` parent)
and did not execute tests. Creating the workspace-local `.tmp` parent resolved
the environmental issue.

## 11. Actual results

- Critical Detector focused tests: **40 passed** in 4.92 seconds.
- Critical data-quality focused tests: **18 passed** in 2.10 seconds on the
  final run (the preceding run was 17 passed in 2.59 seconds).
- Agents/services/API regression slice: **234 passed** in 67.77 seconds.
- The required verbose runs were also green before the final extra invalid-value
  cases: **38 passed**, **17 passed**, and **232 passed**, respectively.
- Ruff on all changed Python files: **passed**.
- Threshold JSON unchanged check: **passed** (`git diff --exit-code` returned
  zero).
- Current threshold JSON SHA-256:
  `9AF68E06B037CE327D27FFFA396BD4DEE289E1BFAE48B0E1DBFAF36EEB9E37AE`.
- Optional repository-wide suite: **399 passed, 31 failed, 1 warning** in
  126.66 seconds. The failures are outside Patch A and stem from repository
  test inputs that are absent in this checkout, notably
  `adult_outpatient_laboratory_reference_map.csv` and
  `data/reference/quarantine_v2.csv`, with downstream data-sync/evaluation
  failures. The required Patch A suites and requested regression slice are
  green.

## 12. Known limitations

- Production records still lack explicit operators until Patch C; the
  temporary legacy defaults are therefore still active.
- Production inactive sides still use existing negative sentinels where
  present. Patch A does not rewrite them.
- Final ARUP provenance requirements are validated on target-schema samples,
  not yet enforced against current production JSON.
- No unit conversion was added. Unsupported cross-unit comparisons continue
  to fail closed under the shared `ReferenceRepository` unit policy.
- The optional full test suite cannot be fully green without the unrelated
  missing repository data inputs described above.

## 13. Medical threshold-number confirmation

`data/reference/critical_thresholds.json` has no Patch A diff. No medical
threshold number was changed, no ARUP threshold data was migrated, and no
reference-range rule or data was changed.

## Review flags

```text
PATCH_A_IMPLEMENTED = YES
EXPLICIT_OPERATOR_SUPPORT = YES
STRICT_OPERATOR_BOUNDARIES_SUPPORTED = YES
NULL_INACTIVE_SIDES_SUPPORTED = YES
INVALID_OPERATOR_FAILS_CLOSED = YES
PROVENANCE_FIELDS_LOADER_COMPATIBLE = YES
LEGACY_OPERATOR_COMPATIBILITY_TEMPORARY = YES
FIX1_SAFETY_INVARIANTS_PRESERVED = YES
GLUCOSE_CONVERSION_IMPLEMENTED = NO
CRITICAL_THRESHOLD_NUMBERS_CHANGED = NO
ARUP_DATA_MIGRATED = NO
REFERENCE_RANGE_CHANGED = NO
CODE_TESTS_PASS = YES
READY_FOR_HUMAN_PATCH_A_REVIEW = YES
```
