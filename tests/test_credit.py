"""Analytic ECL benchmarks, sensitivity invariants, and IFRS stage checks."""

from dataclasses import replace
import math
import unittest

import numpy as np

import _bootstrap
from capital_stack.cecl import CreditSettings, allowances, calibrated_intercept, conditioned_lgd, conditioned_pd, ead_schedule, ifrs_stage, loss_term_structure, provision
from capital_stack.data import reference_scenario, synthetic_bank
from capital_stack.numerics import logit
from capital_stack.scenario import LONG_RUN, Scenario


class CreditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bank = synthetic_bank()
        cls.scenario = reference_scenario()
        cls.pool = replace(cls.bank.portfolios[0], default_fraction=0.)

    def test_calibration_matches_logit(self) -> None:
        for target in (.006, .012, .035, .2):
            self.assertAlmostEqual(calibrated_intercept(target), logit(target), places=8)

    def test_ttc_targets_match_reference_state(self) -> None:
        for pool in self.bank.portfolios:
            self.assertAlmostEqual(conditioned_pd(pool, LONG_RUN), pool.annual_pd, places=10)

    def test_one_quarter_analytic_ecl(self) -> None:
        pool = replace(self.pool, balance=10., maturity_quarters=1, annual_pd=.04, lgd=.5,
                       annual_prepayment=0., effective_rate=.08)
        expected = 10 * (1 - .96 ** .25) * .5 / 1.08 ** .25
        actual = loss_term_structure(pool, self.scenario).expected_loss.sum()
        self.assertAlmostEqual(actual, expected, places=10)

    def test_amortizing_analytic_ecl(self) -> None:
        pool = replace(self.pool, balance=1., maturity_quarters=4, annual_pd=.04, lgd=.5,
                       annual_prepayment=0., effective_rate=0.)
        hazard = 1 - .96 ** .25
        expected = sum(.5 * (1 - (q - 1) / 4) * .96 ** ((q - 1) / 4) * hazard for q in range(1, 5))
        self.assertAlmostEqual(loss_term_structure(pool, self.scenario).expected_loss.sum(), expected, places=10)

    def test_discounted_ecl_benchmark(self) -> None:
        pool = replace(self.pool, maturity_quarters=1, effective_rate=.20, annual_pd=.08)
        expected = pool.balance * pool.lgd * (1 - .92 ** .25) / 1.2 ** .25
        self.assertAlmostEqual(allowances(pool, self.scenario)["cecl"], expected, places=9)

    def test_marginal_default_probability_conservation(self) -> None:
        frame = loss_term_structure(self.pool, self.scenario)
        horizon = self.pool.maturity_quarters
        expected = 1 - (1 - self.pool.annual_pd) ** (horizon / 4)
        self.assertAlmostEqual(frame.marginal_pd.sum(), expected, places=9)
        self.assertTrue((frame.survival.diff().dropna() <= 0).all())

    def test_ead_principal_conservation(self) -> None:
        for prepayment in (0., .2, 1.):
            schedule = ead_schedule(100., 20, prepayment, .06)
            np.testing.assert_allclose(schedule.ead - schedule.scheduled_principal - schedule.prepayment, schedule.closing_ead, atol=1e-10)
            self.assertAlmostEqual(schedule.scheduled_principal.sum() + schedule.prepayment.sum(), 100., places=9)
            self.assertEqual(schedule.closing_ead.iloc[-1], 0.)

    def test_zero_rate_amortization(self) -> None:
        schedule = ead_schedule(100., 4, 0., 0.)
        np.testing.assert_allclose(schedule.ead, [100, 75, 50, 25])

    def test_prepayment_reduces_ecl(self) -> None:
        low = loss_term_structure(replace(self.pool, annual_prepayment=0.), self.scenario).expected_loss.sum()
        high = loss_term_structure(replace(self.pool, annual_prepayment=.5), self.scenario).expected_loss.sum()
        self.assertLess(high, low)

    def test_allowance_monotonic_in_unemployment(self) -> None:
        for pool in self.bank.portfolios:
            values = []
            for unemployment in (4.2, 6.2, 8.2, 10.2):
                frame = self.scenario.frame.copy()
                frame["unemployment"] = unemployment
                scenario = Scenario("stress", frame)
                values.append(allowances(pool, scenario)["cecl"])
            self.assertTrue(all(right > left for left, right in zip(values, values[1:])))

    def test_house_price_drop_increases_allowance(self) -> None:
        pool = self.bank.portfolios[2]
        frame = self.scenario.frame.copy()
        frame["house_prices"] = 70.
        self.assertGreater(allowances(pool, Scenario("house_drop", frame))["cecl"], allowances(pool, self.scenario)["cecl"])

    def test_spread_increase_raises_pd(self) -> None:
        self.assertGreater(conditioned_pd(self.pool, {**LONG_RUN, "bbb_spread": 6.}), conditioned_pd(self.pool, LONG_RUN))

    def test_collateral_lgd_is_bounded(self) -> None:
        for pool in self.bank.portfolios:
            for value in (1., 100., 1000.):
                lgd = conditioned_lgd(pool, {**LONG_RUN, "house_prices": value, "cre_prices": value})
                self.assertGreaterEqual(lgd, 0.)
                self.assertLessEqual(lgd, 1.)

    def test_stage1_is_no_greater_than_cecl(self) -> None:
        for pool in self.bank.portfolios:
            result = allowances(pool, self.scenario)
            self.assertEqual(result["performing_stage"], 1)
            self.assertLessEqual(result["ifrs9"], result["cecl"])
            self.assertAlmostEqual(result["cecl"] - result["ifrs9"], result["difference"])

    def test_stage2_matches_cecl(self) -> None:
        pool = replace(self.pool, origination_pd=self.pool.annual_pd / 3)
        result = allowances(pool, self.scenario)
        self.assertEqual(result["performing_stage"], 2)
        self.assertEqual(result["cecl"], result["ifrs9"])

    def test_stage3_default_benchmark(self) -> None:
        pool = replace(self.pool, default_fraction=1., effective_rate=0.)
        result = allowances(pool, self.scenario)
        self.assertAlmostEqual(result["cecl"], pool.balance * pool.lgd)
        self.assertEqual(result["cecl"], result["ifrs9"])
        self.assertEqual(result["stage3_balance"], pool.balance)

    def test_stage_exposures_sum_to_book(self) -> None:
        for pool in self.bank.portfolios:
            result = allowances(pool, self.scenario)
            self.assertAlmostEqual(result["stage1_balance"] + result["stage2_balance"] + result["stage3_balance"], pool.balance)

    def test_stage_boundary_and_default_precedence(self) -> None:
        self.assertEqual(ifrs_stage(.019, .01), 1)
        self.assertEqual(ifrs_stage(.02, .01), 2)
        self.assertEqual(ifrs_stage(.001, .01, defaulted=True), 3)

    def test_short_life_stage1_equals_lifetime(self) -> None:
        pool = replace(self.pool, maturity_quarters=3)
        result = allowances(pool, self.scenario)
        self.assertEqual(result["cecl"], result["ifrs9"])

    def test_zero_exposure_and_zero_lgd(self) -> None:
        self.assertEqual(allowances(replace(self.pool, balance=0.), self.scenario)["cecl"], 0.)
        self.assertEqual(allowances(replace(self.pool, lgd=0.), self.scenario)["cecl"], 0.)

    def test_expected_loss_bounded_by_exposure(self) -> None:
        self.assertLessEqual(allowances(self.pool, self.scenario)["cecl"], self.pool.balance)

    def test_provision_additivity_across_portfolios(self) -> None:
        opening, closing, chargeoffs = [1., 2., 3.], [2., 1., 4.], [.1, .2, .3]
        total = sum(provision(a, b, c) for a, b, c in zip(opening, closing, chargeoffs))
        self.assertAlmostEqual(total, provision(sum(opening), sum(closing), sum(chargeoffs)))

    def test_allowance_release_can_produce_negative_provision(self) -> None:
        self.assertAlmostEqual(provision(2., 1., .2), -.8)

    def test_invalid_credit_settings_and_inputs(self) -> None:
        with self.assertRaises(ValueError):
            CreditSettings(relative_pd_threshold=1.)
        with self.assertRaises(ValueError):
            ead_schedule(-1., 4, 0.)
        with self.assertRaises(ValueError):
            ifrs_stage(.01, 0.)
        with self.assertRaises(ValueError):
            provision(1., math.nan, 0.)

    def test_extreme_interior_pd_calibration(self) -> None:
        for target in (1e-30, 1e-15, 1 - 1e-15):
            pool = replace(self.pool, annual_pd=target)
            actual = conditioned_pd(pool, LONG_RUN)
            if target <= .5:
                self.assertAlmostEqual(actual / target, 1., places=12)
            else:
                self.assertAlmostEqual((1 - actual) / (1 - target), 1., places=12)

    def test_tiny_rate_amortization_conserves_principal(self) -> None:
        for rate in (1e-14, -1e-14, 1e-9):
            schedule = ead_schedule(100., 80, .1, rate)
            self.assertAlmostEqual(schedule.scheduled_principal.sum() + schedule.prepayment.sum(), 100., places=10)
            self.assertTrue((schedule.ead.diff().dropna() <= 0).all())

    def test_boolean_maturity_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            ead_schedule(100., True, 0.)
