# VMEC-05 G2 final Reference Range evaluation

Command scope:

- `tests/test_agents/test_reference_range_checker_node.py`
- `tests/test_services/test_reference_repository.py`

Result: **101 tests run, 101 passed, 0 failed**.

Software logic coverage includes normal/low/high/unknown classification, inclusive range boundaries, lower-only and upper-only rules, age/sex selection, RI-over-CDL selection, unit normalization and approved aliases, unsupported units/analytes, ambiguous rules, missing values, repository failure, generic Glucose fail-closed behavior, and immutability/order contracts.

This result is software logic test coverage. It is **not** a claim that all current-nine medical reference rules have been independently source-audited or are 100% medically correct.

Complete output: `eval/deterministic/reference_range_pytest.txt`.
