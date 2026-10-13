"""Independent analytic checks of the numerical utilities."""

import math
import unittest

import _bootstrap
from capital_stack.numerics import annual_to_quarterly, bisect_root, logistic, logit


class NumericsTests(unittest.TestCase):
    def test_logistic_symmetry(self) -> None:
        for score in (-20., -3., 0., 2., 20.):
            self.assertAlmostEqual(logistic(score) + logistic(-score), 1.)

    def test_logit_inverse(self) -> None:
        for probability in (.001, .01, .25, .5, .99):
            self.assertAlmostEqual(logistic(logit(probability)), probability)

    def test_extreme_scores_do_not_overflow(self) -> None:
        self.assertEqual(logistic(1000), 1.)
        self.assertEqual(logistic(-1000), 0.)

    def test_logit_rejects_endpoints(self) -> None:
        for probability in (-1., 0., 1., math.nan):
            with self.assertRaises(ValueError):
                logit(probability)

    def test_bisection_matches_square_root(self) -> None:
        self.assertAlmostEqual(bisect_root(lambda x: x * x - 2, 0., 2.), math.sqrt(2), places=10)

    def test_bisection_endpoint(self) -> None:
        self.assertEqual(bisect_root(lambda x: x, 0., 1.), 0.)

    def test_bisection_requires_bracket(self) -> None:
        with self.assertRaises(ValueError):
            bisect_root(lambda x: x * x + 1, -1., 1.)

    def test_bisection_fails_explicitly_on_nonconvergence(self) -> None:
        with self.assertRaises(RuntimeError):
            bisect_root(lambda x: x * x - 2, 0., 2., max_iterations=1)

    def test_bisection_rejects_nonfinite_values(self) -> None:
        with self.assertRaises(ValueError):
            bisect_root(lambda x: math.nan, 0., 1.)

    def test_annual_hazard_conservation(self) -> None:
        for probability in (0., .01, .5, 1.):
            quarter = annual_to_quarterly(probability)
            self.assertAlmostEqual(1 - (1 - quarter) ** 4, probability)

    def test_invalid_hazard(self) -> None:
        with self.assertRaises(ValueError):
            annual_to_quarterly(1.01)

    def test_tiny_hazard_preserves_relative_accuracy(self) -> None:
        self.assertAlmostEqual(annual_to_quarterly(1e-20) / 2.5e-21, 1., places=14)

    def test_bisection_rejects_fractional_iteration_budget(self) -> None:
        with self.assertRaises(ValueError):
            bisect_root(lambda value: value, -1., 1., max_iterations=1.5)
