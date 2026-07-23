"""Tests for numeric version constraint grammar and evaluation."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from docker.versions import (
    ConstraintSyntaxError,
    VersionSyntaxError,
    NumericVersion,
    ConstraintClause,
    Constraint,
    parse_numeric_version,
    parse_constraint,
    validate_constraint_consistency,
)

from versioning.support.inventory_builder import minimal_toml, write_toml, FIXTURES


class TestNumericVersion(unittest.TestCase):
    """parse_numeric_version returns (major, minor, patch)."""

    def test_simple(self):
        v = parse_numeric_version("3.14.6")
        self.assertEqual(v, NumericVersion(3, 14, 6))

    def test_zeros(self):
        v = parse_numeric_version("0.1.0")
        self.assertEqual(v, NumericVersion(0, 1, 0))

    def test_large_numbers(self):
        v = parse_numeric_version("999.888.777")
        self.assertEqual(v, NumericVersion(999, 888, 777))

    def test_rejects_leading_zero(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("03.14.6")

    def test_rejects_prerelease_numeric(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("3.14.6b1")

    def test_rejects_build_suffix(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("3.14.6+build")

    def test_rejects_rc_suffix(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("3.14.6-rc1")

    def test_rejects_v_prefix(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("v3.14.6")

    def test_rejects_missing_patch(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version("3.14")

    def test_rejects_leading_dot(self):
        with self.assertRaises(VersionSyntaxError):
            parse_numeric_version(".3.14.6")


class TestVersionComparison(unittest.TestCase):
    """NumericVersion tuples compare correctly."""

    def test_equality(self):
        self.assertEqual(
            NumericVersion(3, 14, 6),
            NumericVersion(3, 14, 6),
        )

    def test_lt(self):
        self.assertLess(NumericVersion(3, 14, 6), NumericVersion(3, 15, 0))

    def test_gt(self):
        self.assertGreater(NumericVersion(3, 15, 0), NumericVersion(3, 14, 6))

    def test_lt_diff_minor(self):
        self.assertLess(NumericVersion(3, 14, 0), NumericVersion(3, 14, 6))

    def test_gt_diff_minor(self):
        self.assertGreater(NumericVersion(3, 14, 6), NumericVersion(3, 13, 99))

    def test_lt_diff_major(self):
        self.assertLess(NumericVersion(2, 99, 99), NumericVersion(3, 0, 0))


class TestParseConstraint(unittest.TestCase):
    """parse_constraint handles all supported operators."""

    def test_eq(self):
        c = parse_constraint("==3.14.6")
        self.assertEqual(len(c.clauses), 1)
        self.assertEqual(c.clauses[0].operator, "==")
        self.assertEqual(c.clauses[0].operand, NumericVersion(3, 14, 6))

    def test_gt(self):
        c = parse_constraint(">3.14.6")
        self.assertEqual(c.clauses[0].operator, ">")
        self.assertEqual(c.clauses[0].operand, NumericVersion(3, 14, 6))

    def test_gte(self):
        c = parse_constraint(">=3.14.6")
        self.assertEqual(c.clauses[0].operator, ">=")

    def test_lt(self):
        c = parse_constraint("<4.0.0")
        self.assertEqual(c.clauses[0].operator, "<")

    def test_lte(self):
        c = parse_constraint("<=3.14.6")
        self.assertEqual(c.clauses[0].operator, "<=")

    def test_compound_and(self):
        c = parse_constraint(">=3.14.6,<4.0.0")
        self.assertEqual(len(c.clauses), 2)
        self.assertEqual(c.clauses[0].operator, ">=")
        self.assertEqual(c.clauses[1].operator, "<")

    def test_rejects_empty_string(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("")

    def test_rejects_empty_clause(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6,")

    def test_rejects_leading_comma(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(",>=3.14.6")

    def test_rejects_double_comma(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6,,<4.0.0")

    def test_rejects_or_operator(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6||<4.0.0")

    def test_rejects_caret(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("^3.14.6")

    def test_rejects_tilde(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("~3.14.6")

    def test_rejects_wildcard(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("3.14.*")

    def test_rejects_not_equal(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("!=3.14.6")

    def test_rejects_arrow_operator(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint("=>3.14.6")

    def test_rejects_missing_patch(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14")

    def test_rejects_major_only(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3")

    def test_rejects_prerelease(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6b1")

    def test_rejects_rc_suffix(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6-rc1")

    def test_rejects_v_prefix(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=v3.14.6")

    def test_rejects_build_suffix(self):
        with self.assertRaises(ConstraintSyntaxError):
            parse_constraint(">=3.14.6+build")


class TestConstraintMatching(unittest.TestCase):
    """Constraint.matches evaluates correctly."""

    def test_eq_true(self):
        c = parse_constraint("==3.14.6")
        self.assertTrue(c.matches(NumericVersion(3, 14, 6)))

    def test_eq_false(self):
        c = parse_constraint("==3.14.6")
        self.assertFalse(c.matches(NumericVersion(3, 14, 7)))

    def test_gt_true(self):
        c = parse_constraint(">3.14.6")
        self.assertTrue(c.matches(NumericVersion(3, 14, 7)))

    def test_gt_false(self):
        c = parse_constraint(">3.14.6")
        self.assertFalse(c.matches(NumericVersion(3, 14, 6)))

    def test_gte_true(self):
        c = parse_constraint(">=3.14.6")
        self.assertTrue(c.matches(NumericVersion(3, 14, 6)))

    def test_lt_true(self):
        c = parse_constraint("<4.0.0")
        self.assertTrue(c.matches(NumericVersion(3, 99, 99)))

    def test_lte_true(self):
        c = parse_constraint("<=3.14.6")
        self.assertTrue(c.matches(NumericVersion(3, 14, 6)))

    def test_compound_true(self):
        c = parse_constraint(">=3.14.6,<4.0.0")
        self.assertTrue(c.matches(NumericVersion(3, 15, 0)))

    def test_compound_false(self):
        c = parse_constraint(">=3.14.6,<4.0.0")
        self.assertFalse(c.matches(NumericVersion(4, 0, 0)))

    def test_compound_lower_bound_false(self):
        c = parse_constraint(">=3.14.6,<4.0.0")
        self.assertFalse(c.matches(NumericVersion(3, 14, 5)))


class TestConstraintConsistency(unittest.TestCase):
    """validate_constraint_consistency detects contradictions."""

    def test_valid_simple(self):
        c = parse_constraint(">=3.14.6,<4.0.0")
        validate_constraint_consistency(c)  # should not raise

    def test_valid_equal_loose(self):
        c = parse_constraint(">=3.14.6,<=3.14.6")
        validate_constraint_consistency(c)

    def test_valid_eq_plus_gte(self):
        c = parse_constraint("==3.14.6,>=3.14.6")
        validate_constraint_consistency(c)

    def test_contradictory_gt_lt_same(self):
        c = parse_constraint(">=3.14.6,<3.14.6")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_gt_lte_bound(self):
        c = parse_constraint(">3.14.6,<=3.14.6")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_gt_plus_eq(self):
        c = parse_constraint("==3.14.6,>3.14.6")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_lt_plus_eq(self):
        c = parse_constraint("==3.14.6,<3.14.6")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_two_eq(self):
        c = parse_constraint("==3.14.6,==3.14.7")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    # --- Regression: strict+loose equal operands must not hide strictness ---

    def test_contradictory_strict_loose_lower_equal_with_upper(self):
        """>3.0.0,>=3.0.0,<=3.0.0 — the only candidate (3.0.0) is excluded by >."""
        c = parse_constraint(">3.0.0,>=3.0.0,<=3.0.0")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_strict_loose_upper_equal_with_lower(self):
        """<3.0.0,<=3.0.0,>=3.0.0 — the only candidate (3.0.0) is excluded by <."""
        c = parse_constraint("<3.0.0,<=3.0.0,>=3.0.0")
        with self.assertRaises(ConstraintSyntaxError):
            validate_constraint_consistency(c)

    def test_contradictory_strict_loose_lower_equal_no_upper(self):
        """>3.0.0,>=3.0.0 — stricter bound preserved, no upper to conflict with."""
        c = parse_constraint(">3.0.0,>=3.0.0")
        validate_constraint_consistency(c)

    def test_contradictory_strict_loose_upper_equal_no_lower(self):
        """<3.0.0,<=3.0.0 — stricter bound preserved, no lower to conflict with."""
        c = parse_constraint("<3.0.0,<=3.0.0")
        validate_constraint_consistency(c)

    def test_strict_loose_lower_equal_separate_upper_valid(self):
        """>3.0.0,>=3.0.0,<4.0.0 — strictness preserved, non-empty range."""
        c = parse_constraint(">3.0.0,>=3.0.0,<4.0.0")
        validate_constraint_consistency(c)

    def test_strict_loose_upper_equal_separate_lower_valid(self):
        """<4.0.0,<=4.0.0,>3.0.0 — strictness preserved, non-empty range."""
        c = parse_constraint("<4.0.0,<=4.0.0,>3.0.0")
        validate_constraint_consistency(c)

    def test_strict_loose_both_sides_equal_valid(self):
        """>3.0.0,>=3.0.0,<4.0.0,<=4.0.0 — strict on both sides, non-empty range."""
        c = parse_constraint(">3.0.0,>=3.0.0,<4.0.0,<=4.0.0")
        validate_constraint_consistency(c)


if __name__ == "__main__":
    unittest.main()
