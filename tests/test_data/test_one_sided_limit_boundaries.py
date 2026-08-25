from decimal import Decimal

import pytest

from src.agents.nodes.reference_range_checker_node import _classify, _parse_value


class TestOneSidedLimitBoundaries:
    """Boundary tests for ONE_SIDED_LIMIT reference rules (AST, ALT, GGT, Total bilirubin)."""

    @pytest.mark.parametrize(
        ("value", "upper", "expected"),
        [
            (Decimal("39.9999"), Decimal("40"), "normal"),
            (Decimal("40.0000"), Decimal("40"), "high"),
            (Decimal("40.0001"), Decimal("40"), "high"),
            (Decimal("20.0000"), Decimal("40"), "normal"),
            (Decimal("0.0000"),  Decimal("40"), "normal"),
        ],
    )
    def test_ast_boundary_probes(self, value, upper, expected):
        assert _classify(value, None, upper, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == expected

    @pytest.mark.parametrize(
        ("value", "upper", "expected"),
        [
            (Decimal("40.9999"), Decimal("41"), "normal"),
            (Decimal("41.0000"), Decimal("41"), "high"),
            (Decimal("41.0001"), Decimal("41"), "high"),
            (Decimal("20.0000"), Decimal("41"), "normal"),
            (Decimal("0.0000"),  Decimal("41"), "normal"),
        ],
    )
    def test_alt_boundary_probes(self, value, upper, expected):
        assert _classify(value, None, upper, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == expected

    @pytest.mark.parametrize(
        ("value", "upper", "expected"),
        [
            (Decimal("60.9999"), Decimal("61"), "normal"),
            (Decimal("61.0000"), Decimal("61"), "high"),
            (Decimal("61.0001"), Decimal("61"), "high"),
            (Decimal("20.0000"), Decimal("61"), "normal"),
            (Decimal("0.0000"),  Decimal("61"), "normal"),
        ],
    )
    def test_ggt_male_boundary_probes(self, value, upper, expected):
        assert _classify(value, None, upper, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == expected

    @pytest.mark.parametrize(
        ("value", "upper", "expected"),
        [
            (Decimal("35.9999"), Decimal("36"), "normal"),
            (Decimal("36.0000"), Decimal("36"), "high"),
            (Decimal("36.0001"), Decimal("36"), "high"),
            (Decimal("20.0000"), Decimal("36"), "normal"),
            (Decimal("0.0000"),  Decimal("36"), "normal"),
        ],
    )
    def test_ggt_female_boundary_probes(self, value, upper, expected):
        assert _classify(value, None, upper, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == expected

    @pytest.mark.parametrize(
        ("value", "upper", "expected"),
        [
            (Decimal("20.9999"), Decimal("21"), "normal"),
            (Decimal("21.0000"), Decimal("21"), "high"),
            (Decimal("21.0001"), Decimal("21"), "high"),
            (Decimal("10.0000"), Decimal("21"), "normal"),
            (Decimal("0.0000"),  Decimal("21"), "normal"),
        ],
    )
    def test_total_bilirubin_boundary_probes(self, value, upper, expected):
        assert _classify(value, None, upper, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == expected

    @pytest.mark.parametrize(
        "invalid_val",
        [-1, -0.0001, "-5", float("nan"), float("inf"), float("-inf")],
    )
    def test_negative_and_nonfinite_domain_guards(self, invalid_val):
        parsed = _parse_value(invalid_val)
        assert parsed is None

    @pytest.mark.parametrize(
        "bad_op",
        [None, "", "INVALID", "abc", "==", "!=", "123"],
    )
    def test_missing_or_invalid_operator_fails_closed(self, bad_op):
        assert _classify(Decimal("20"), None, Decimal("40"), rule_type="ONE_SIDED_LIMIT", upper_operator=bad_op) == "unknown"
        assert _classify(Decimal("40"), None, Decimal("40"), rule_type="ONE_SIDED_LIMIT", upper_operator=bad_op) == "unknown"
        assert _classify(Decimal("50"), None, Decimal("40"), rule_type="ONE_SIDED_LIMIT", upper_operator=bad_op) == "unknown"

    def test_missing_upper_bound_fails_closed(self):
        assert _classify(Decimal("20"), None, None, rule_type="ONE_SIDED_LIMIT", upper_operator="<") == "unknown"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("39.9999"), "normal"),
            (Decimal("40.0000"), "normal"),  # with <= operator, 40 is normal
            (Decimal("40.0001"), "high"),
            (Decimal("50.0000"), "high"),
        ],
    )
    def test_generic_lte_operator_evaluation(self, value, expected):
        assert _classify(value, None, Decimal("40"), rule_type="ONE_SIDED_LIMIT", upper_operator="<=") == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            (Decimal("40.0001"), "normal"),  # with > operator, >40 is normal
            (Decimal("40.0000"), "low"),
            (Decimal("39.9999"), "low"),
        ],
    )
    def test_generic_gt_operator_evaluation(self, value, expected):
        assert _classify(value, None, Decimal("40"), rule_type="ONE_SIDED_LIMIT", upper_operator=">") == expected

