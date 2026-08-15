# VMEC-05 G2 final Critical Detector evaluation

Command scope:

- `tests/test_agents/test_critical_detector_node.py`
- `tests/test_data/test_critical_data_quality.py`

Result: **102 tests run, 102 passed, 0 failed**.

Verified coverage:

- Potassium strict boundaries: `< 3.0 mmol/L` and `> 6.1 mmol/L`; equality does not trigger.
- FPG boundaries in source mg/dL and through the production Decimal mmol/L conversion.
- Inactive analytes/null thresholds do not create false alerts.
- Invalid operators fail closed.
- Unsupported units/conversions fail closed.
- Upstream `unknown` is preserved, including generic Glucose.

Golden accuracy uses only three explicitly parameterized test groups whose cases each carry an `expected_status`: six Potassium boundary outcomes, six FPG mg/dL outcomes, and six FPG mmol/L/Decimal outcomes. All 18 collected golden outcomes passed.

`CRITICAL_GOLDEN_CASE_COUNT = 18`  
`CRITICAL_GOLDEN_CORRECT = 18`  
`CRITICAL_GOLDEN_ACCURACY = 100%`

Complete output: `eval/deterministic/critical_detector_pytest.txt`. Machine-readable denominator: `eval/deterministic/critical_golden_cases.json`.
