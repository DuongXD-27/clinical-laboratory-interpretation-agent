# VMEC-05 G2 deterministic evaluation

The first sandbox run could not create pytest's default OS temp directory, so no test body ran. The recorded evidence files were then overwritten by clean reruns using unique workspace-local `--basetemp` paths. The results below are from those valid reruns.

## Reference Range Checker

- Tests run: 101
- Passed: 101
- Failed: 0
- Classification coverage: normal, low, high, unknown; two-sided, lower-only, and upper-only ranges; sex and age rule selection; multi-indicator order.
- Boundary coverage: inclusive lower/upper RI bounds across Potassium, HbA1c, HGB, HDL-C, LDL-C, Creatinine, WBC/RBC and explicit adult age edges.
- Unit/fail-closed coverage: approved unit aliases, unsupported units, unsupported analytes, generic Glucose rejection, missing value, ambiguous rules, out-of-scope age/sex, repository failure, and RI-over-CDL selection.
- Verdict: **PASS**.
- This is software logic coverage, not complete medical-source validation of all current-nine RI rules.
- Complete output: `eval/deterministic/reference_range_pytest.txt`.

## Critical Detector

- Tests run: 102
- Passed: 102
- Failed: 0
- Potassium boundary correctness: `< 3.0 mmol/L` and `> 6.1 mmol/L` trigger; exact `3.0` and `6.1` do not trigger under strict operators.
- FPG boundary correctness: source-unit and exact Decimal mmol/L conversion cases pass, including `3.05 -> critical_low` and `3.053 -> not critical`; conversion provenance/data-quality checks pass.
- Inactive-analyte false-alert behavior: explicit inactive rules, null thresholds, and production inactive analytes produce no false critical alerts.
- Fail-closed behavior: invalid operators, unsupported conversions/units, unresolved analytes, generic Glucose, and upstream unknown status remain non-escalated.
- Explicit golden accuracy: 18/18 = 100%, limited to the three parameterized production boundary groups documented in `critical_golden_cases.json`.
- Verdict: **PASS**.
- Complete output: `eval/deterministic/critical_detector_pytest.txt`.
