"""Capital, allowance, loan balance, and revenue reconciliations."""

from dataclasses import replace
import unittest

import numpy as np

import _bootstrap
from capital_stack.cecl import project_credit, provision
from capital_stack.data import loan_balance_paths, reference_scenario
from capital_stack.endgame import current_standardized_rwa
from capital_stack.planning import run_plan
from capital_stack.ppnr import PPNRSettings, project_ppnr
from capital_stack.projection import CapitalSettings, cet1_roll_forward, peak_to_trough, project_capital, project_rwa, stress_capital_buffer
from capital_stack.scenario import Scenario


class ProjectionPPNRTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = run_plan()

    def test_cet1_accounting_identity(self) -> None:
        for name in self.plan.scenarios:
            frame = self.plan.tables[f"capital_{name}"]
            np.testing.assert_allclose(frame.closing_cet1, frame.opening_cet1 + frame.net_income - frame.distributions, atol=1e-10)
            self.assertAlmostEqual(frame.closing_cet1.iloc[-1], self.plan.bank.cet1 + frame.net_income.sum() - frame.distributions.sum())

    def test_cet1_opening_continuity(self) -> None:
        frame = self.plan.tables["capital_severely_adverse"]
        self.assertEqual(frame.opening_cet1.iloc[0], self.plan.bank.cet1)
        np.testing.assert_allclose(frame.opening_cet1.iloc[1:], frame.closing_cet1.iloc[:-1])

    def test_allowance_accounting_identity(self) -> None:
        for name in self.plan.scenarios:
            credit = self.plan.tables[f"credit_{name}"]
            np.testing.assert_allclose(credit.closing_allowance, credit.opening_allowance + credit.provision - credit.net_chargeoffs, atol=1e-10)
            for _, pool in credit.groupby("portfolio"):
                np.testing.assert_allclose(pool.opening_allowance.iloc[1:], pool.closing_allowance.iloc[:-1])

    def test_projected_provision_additivity(self) -> None:
        credit = self.plan.tables["credit_severely_adverse"]
        totals = credit.groupby("quarter")[["opening_allowance", "closing_allowance", "net_chargeoffs", "provision"]].sum()
        for row in totals.itertuples():
            self.assertAlmostEqual(row.provision, provision(row.opening_allowance, row.closing_allowance, row.net_chargeoffs))
        np.testing.assert_allclose(totals.provision, self.plan.tables["capital_severely_adverse"].provision)

    def test_loan_balance_conservation(self) -> None:
        for name in self.plan.scenarios:
            frame = self.plan.tables[f"credit_{name}"]
            closing = frame.opening_balance - frame.default_principal - frame.scheduled_principal - frame.prepayment + frame.originations - frame.extra_runoff
            np.testing.assert_allclose(closing, frame.closing_balance, atol=1e-10)
            np.testing.assert_allclose(frame.net_chargeoffs + frame.recoveries, frame.default_principal, atol=1e-10)

    def test_credit_uses_shared_balance_path(self) -> None:
        credit = self.plan.tables["credit_baseline"].pivot(index="quarter", columns="portfolio", values="closing_balance")
        balances = self.plan.tables["balances_baseline"].set_index("quarter")
        for name in credit.columns:
            np.testing.assert_allclose(credit[name], balances[name].iloc[:9])

    def test_ppnr_identity(self) -> None:
        for name in self.plan.scenarios:
            frame = self.plan.tables[f"ppnr_{name}"]
            np.testing.assert_allclose(frame.ppnr, frame.nii + frame.noninterest_income - frame.noninterest_expense)
            np.testing.assert_allclose(frame.nii, frame.interest_income - frame.interest_expense)
            np.testing.assert_allclose(frame.noninterest_income, frame.transaction_fees + frame.wealth_fees + frame.origination_fees)

    def test_nim_reconciles(self) -> None:
        frame = self.plan.tables["ppnr_baseline"]
        np.testing.assert_allclose(frame.nim * frame.earning_assets / 4, frame.nii)

    def test_deposit_beta_lowers_nii_when_rates_rise(self) -> None:
        bank = self.plan.bank
        frame = reference_scenario().frame.copy()
        frame["rate_3m"] = 6.5
        frame["rate_10y"] = 4.2
        scenario = Scenario("higher_rates", frame)
        balances = loan_balance_paths(bank, scenario)
        low = project_ppnr(bank, scenario, balances, settings=PPNRSettings(deposit_beta=0.))
        high = project_ppnr(bank, scenario, balances, settings=PPNRSettings(deposit_beta=1.))
        self.assertTrue((high.nii < low.nii).all())

    def test_no_common_distributions_in_scb_reference(self) -> None:
        reference = self.plan.tables["scb_reference_capital"]
        actual = self.plan.tables["capital_severely_adverse"]
        self.assertEqual(reference.common_dividends.sum(), 0.)
        self.assertEqual(reference.buybacks.sum(), 0.)
        np.testing.assert_allclose(reference.closing_cet1 - actual.closing_cet1,
                                   (actual.common_dividends + actual.buybacks).cumsum(), atol=1e-10)
        self.assertGreater(reference.preferred_dividends.sum(), 0.)

    def test_taxes_no_unearned_loss_benefit(self) -> None:
        frame = self.plan.tables["capital_severely_adverse"]
        self.assertTrue((frame.taxes >= 0).all())
        self.assertTrue((frame[frame.pretax_income < 0].taxes == 0).all())

    def test_tax_benefit_is_explicit_option(self) -> None:
        bank = self.plan.bank
        frame = project_capital(bank, self.plan.tables["ppnr_severely_adverse"], self.plan.tables["credit_severely_adverse"],
                                self.plan.tables["capital_severely_adverse"][["quarter", "rwa"]],
                                CapitalSettings(recognize_tax_benefit=True, shock_loss_bn=1.5))
        self.assertTrue((frame[frame.pretax_income < 0].taxes < 0).all())

    def test_shock_is_booked_once(self) -> None:
        frame = self.plan.tables["capital_severely_adverse"]
        self.assertAlmostEqual(frame.other_losses.sum(), .5)
        self.assertEqual((frame.other_losses > 0).sum(), 1)

    def test_scb_floor_binds(self) -> None:
        result = stress_capital_buffer(.12, [.13] * 9, [100.] * 9, [0.] * 9)
        self.assertEqual(result["scb"], .025)
        self.assertLess(result["starting_to_minimum_decline"], 0.)

    def test_scb_uses_q4_q7_and_minimum_rwa(self) -> None:
        ratios = [.12, .11, .1, .08, .09, .1, .11, .1, .11]
        rwa = [200., 200., 200., 100., 200., 200., 200., 200., 200.]
        dividends = [99., 99., 99., 1., 2., 3., 4., 99., 99.]
        result = stress_capital_buffer(.12, ratios, rwa, dividends)
        self.assertEqual(result["minimum_quarter"], 4)
        self.assertAlmostEqual(result["dividend_addon"], .1)
        self.assertAlmostEqual(result["scb"], .14)

    def test_scb_starting_to_minimum_is_not_peak_drawdown(self) -> None:
        ratios = [.14, .15, .11, .10, .11, .12, .12, .12, .12]
        result = stress_capital_buffer(.12, ratios, [100.] * 9, [0.] * 9)
        self.assertAlmostEqual(result["starting_to_minimum_decline"], .02)
        self.assertAlmostEqual(peak_to_trough([.12, *ratios]), .05)

    def test_peak_to_trough_respects_time_order(self) -> None:
        self.assertEqual(peak_to_trough([.08, .09, .10]), 0.)
        self.assertAlmostEqual(peak_to_trough([.12, .11, .14, .1]), .04)

    def test_requirement_headroom(self) -> None:
        frame = self.plan.tables["requirements"]
        np.testing.assert_allclose(frame.headroom_ratio, frame.cet1_ratio - frame.planning_hurdle)
        self.assertTrue((frame.planning_hurdle == .045 + self.plan.scb["scb"]).all())
        self.assertFalse(frame[frame.scenario == "severely_adverse"].meets_planning_hurdle.all())

    def test_rwa_stress_migration_increases_same_book_rwa(self) -> None:
        bank = self.plan.bank
        base = reference_scenario()
        frame = base.frame.copy()
        frame["unemployment"] = 10.
        stress = Scenario("migration", frame)
        balances = loan_balance_paths(bank, base)
        self.assertTrue((project_rwa(bank, stress, balances).rwa > project_rwa(bank, base, balances).rwa).all())

    def test_projection_rejects_missing_credit_pool(self) -> None:
        credit = self.plan.tables["credit_baseline"].iloc[1:]
        with self.assertRaises(ValueError):
            project_capital(self.plan.bank, self.plan.tables["ppnr_baseline"], credit,
                            self.plan.tables["capital_baseline"][["quarter", "rwa"]])

    def test_negative_capital_remains_visible(self) -> None:
        self.assertEqual(cet1_roll_forward(1., -2., .1), -1.1)

    def test_invalid_scb_paths(self) -> None:
        with self.assertRaises(ValueError):
            stress_capital_buffer(.12, [.1] * 9, [0.] * 9, [0.] * 9)
        with self.assertRaises(ValueError):
            stress_capital_buffer(.12, [.1] * 4, [100.] * 4, [0.] * 4)

    def test_invalid_deposit_beta_and_capital_settings(self) -> None:
        with self.assertRaises(ValueError):
            PPNRSettings(deposit_beta=1.1)
        with self.assertRaises(ValueError):
            CapitalSettings(tax_rate=-.1)

    def test_all_reconciliation_residuals_are_small(self) -> None:
        frame = self.plan.tables["validation_residuals"].drop(columns="scenario")
        self.assertLess(float(frame.to_numpy().max()), 1e-10)

    def test_supplied_scenario_paths_are_used(self) -> None:
        paths = {"baseline": reference_scenario(), "severely_adverse": reference_scenario()}
        plan = run_plan(scenario_paths=paths)
        np.testing.assert_allclose(plan.tables["ppnr_baseline"].ppnr, plan.tables["ppnr_severely_adverse"].ppnr)
        self.assertAlmostEqual(plan.tables["capital_severely_adverse"].other_losses.sum(), .5)

    def test_seeded_capital_calibration_ranges(self) -> None:
        summary = self.plan.tables["capital_summary"].set_index("scenario")
        baseline = summary.loc["baseline"]
        adverse = summary.loc["severely_adverse"]
        self.assertGreaterEqual(baseline.ending_cet1_ratio, .10)
        self.assertLessEqual(baseline.ending_cet1_ratio, .14)
        self.assertGreaterEqual(adverse.minimum_cet1_ratio, .07)
        self.assertLessEqual(adverse.minimum_cet1_ratio, .10)
        self.assertGreaterEqual(adverse.peak_to_trough_decline, .03)
        self.assertLessEqual(adverse.peak_to_trough_decline, .06)
        self.assertGreaterEqual(self.plan.scb["reference_peak_to_trough_decline"], .03)
        self.assertLessEqual(self.plan.scb["reference_peak_to_trough_decline"], .06)
        self.assertGreaterEqual(self.plan.scb["scb"], .025)
        self.assertLessEqual(self.plan.scb["scb"], .05)

    def test_seeded_credit_loss_calibration_range(self) -> None:
        credit = self.plan.tables["credit_severely_adverse"]
        losses = float(credit.net_chargeoffs.sum())
        opening_loans = sum(pool.balance for pool in self.plan.bank.portfolios)
        self.assertGreaterEqual(losses / opening_loans, .06)
        self.assertLessEqual(losses / opening_loans, .10)
        summary = self.plan.tables["capital_summary"].set_index("scenario").loc["severely_adverse"]
        self.assertAlmostEqual(summary.total_credit_losses_bn, losses)
        self.assertAlmostEqual(summary.credit_losses_to_opening_loans, losses / opening_loans)

    def test_seeded_ppnr_positive_and_lower_under_stress(self) -> None:
        baseline = self.plan.tables["ppnr_baseline"].ppnr
        adverse = self.plan.tables["ppnr_severely_adverse"].ppnr
        self.assertTrue((baseline > 0).all())
        self.assertTrue((adverse > 0).all())
        self.assertTrue((adverse < baseline).all())

    def test_seeded_endgame_increase_and_nonbinding_floor(self) -> None:
        impact = self.plan.tables["endgame_impact"].set_index("framework")
        current = impact.loc["current_standardized_proxy", "total_rwa"]
        for framework in ("requested_illustrative_output_floor", "historical_2023_us_dual_stack_proxy"):
            row = impact.loc[framework]
            self.assertGreaterEqual(row.total_rwa / current - 1, .03)
            self.assertLessEqual(row.total_rwa / current - 1, .15)
            self.assertEqual(row.floor_adjustment_rwa, 0.)

    def test_short_supplied_scenario_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            run_plan(scenario_paths={"baseline": reference_scenario(8), "severely_adverse": reference_scenario()})
