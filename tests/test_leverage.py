"""Independent numeric leverage benchmarks and existing-plan integration checks."""

from dataclasses import replace
import math
import unittest

import numpy as np
import pandas as pd

import _bootstrap
from capital_stack import leverage_config as config
from capital_stack.data import synthetic_bank, synthetic_leverage_inputs
from capital_stack.leverage import (LeverageInputs, custodial_exclusion, derivative_pfe,
                                    derivative_replacement_cost, gross_repo_receivables,
                                    leverage_buffer, leverage_buffer_requirement, leverage_ratios,
                                    leverage_sensitivities, max_payout_ratio, monthly_exposure_components,
                                    off_balance_sheet_exposure, on_balance_sheet_assets,
                                    project_leverage, repo_counterparty_exposure, scale_leverage_inputs,
                                    sold_credit_protection, total_leverage_exposure)
from capital_stack.leverage_config import LeverageSettings
from capital_stack.planning import run_plan

# Config: hand-computed test fixtures use arbitrary monetary units, not bank observations.
TEST_START = "2026-01-01"
TEST_END = "2026-03-31"
TEST_MONTHS = pd.date_range(TEST_START, TEST_END, freq=pd.offsets.MonthEnd())
TEST_DAYS = pd.date_range(TEST_START, TEST_END, freq="D")
CHECK = "check"
MINIMUM_BN = "minimum_bn"
RWA = "rwa"
RISK_TIER1_RATIO = "tier1_ratio"


def snapshots(frame: pd.DataFrame) -> pd.DataFrame:
    return pd.concat([frame.assign(**{config.MONTH: month}) for month in TEST_MONTHS], ignore_index=True)


def derivative(value: float = 20., addon: float = 10.) -> pd.DataFrame:
    return pd.DataFrame({config.NETTING_SET: ["one"], config.COUNTERPARTY_TYPE: ["financial"],
                         config.END_USER: [False], config.V: [value], config.ADDON: [addon],
                         config.CVM_RECEIVED: [15.], config.CVM_POSTED: [0.], config.CVM_ELIGIBLE: [True]})


def repos(qmna: bool = True) -> pd.DataFrame:
    return pd.DataFrame({config.COUNTERPARTY: ["dealer", "dealer"], config.REPO_NETTING_SET: ["one", "one"],
                         config.QMNA: [qmna, qmna], config.E: [50., 30.], config.C: [45., 40.],
                         config.GROSS_RECEIVABLE: [50., 30.], config.ON_BALANCE_RECEIVABLE: [50., 30.],
                         config.NETTING_MET: [True, True]})


def toy_inputs() -> LeverageInputs:
    daily = pd.DataFrame({config.DATE: TEST_DAYS, **{column: 0. for column in config.DAILY_AMOUNT_COLUMNS}})
    daily[config.ASSETS], daily[config.DERIVATIVE_ASSETS] = 1000., 30.
    protection = pd.DataFrame({config.REFERENCE: ["one"], config.SOLD: [50.], config.PURCHASED: [20.],
                               config.MATCHED_HEDGE: [True], config.CET1_LOSS: [0.]})
    repo = repos().copy()
    repo[config.E], repo[config.C] = [55., 50.], [50., 50.]
    commitments = pd.DataFrame({config.COMMITMENT_TYPE: [config.UNCANCELABLE, config.COMMITMENT, config.FINANCIAL_LC],
                                config.MATURITY: [.5, 2., 2.], config.NOTIONAL: [100., 40., 10.]})
    return LeverageInputs(daily, snapshots(derivative()), snapshots(protection), snapshots(repo), snapshots(commitments))


class LeverageComponentTests(unittest.TestCase):
    def test_toy_total_and_slr(self) -> None:
        reconciliation = total_leverage_exposure(toy_inputs())
        total = float(reconciliation[config.AMOUNT].sum())
        self.assertEqual(total, 1066.)
        amounts = reconciliation.set_index(config.COMPONENT)[config.AMOUNT]
        self.assertEqual(amounts.loc["derivative_replacement_cost"], 7.)
        self.assertEqual(amounts.loc["derivative_pfe"], 14.)
        self.assertEqual(amounts.loc["sold_credit_protection"], 30.)
        self.assertEqual(amounts.loc["repo_counterparty_exposure"], 5.)
        self.assertEqual(amounts.loc["off_balance_commitments"], 40.)
        self.assertEqual(amounts.loc[config.DERIVATIVE_ASSETS], -30.)
        ratio = leverage_ratios(60., 1000., 0., total)
        self.assertAlmostEqual(ratio[config.SLR].item(), .0562852, delta=1e-6)
        self.assertEqual(ratio[config.LEVERAGE_RATIO].item(), .06)
        self.assertEqual(list(reconciliation.columns), [config.COMPONENT, config.RULE, config.AMOUNT])

    def test_negative_value_pfe_multiplier(self) -> None:
        result = derivative_pfe(derivative(-10.))
        self.assertAlmostEqual(result[config.MULTIPLIER].item(), .6112386, delta=1e-7)
        self.assertAlmostEqual(result[config.AMOUNT].item(), 8.557341, delta=1e-6)

    def test_pfe_positive_value_caps_without_overflow(self) -> None:
        result = derivative_pfe(derivative(1e300))
        self.assertEqual(result[config.MULTIPLIER].item(), 1.)
        self.assertEqual(result[config.AMOUNT].item(), 14.)

    def test_zero_addon_pfe(self) -> None:
        for value in (-10., 0., 20.):
            self.assertEqual(derivative_pfe(derivative(value, 0.))[config.AMOUNT].item(), 0.)

    def test_commercial_end_user_has_no_alpha(self) -> None:
        frame = derivative().assign(**{config.END_USER: True})
        self.assertEqual(derivative_pfe(frame)[config.AMOUNT].item(), 10.)
        self.assertEqual(derivative_replacement_cost(frame)[config.AMOUNT].item(), 5.)

    def test_cash_margin_eligibility_and_posted_sign(self) -> None:
        frame = derivative().assign(**{config.CVM_POSTED: 2.})
        self.assertAlmostEqual(derivative_replacement_cost(frame)[config.AMOUNT].item(), 9.8)
        frame[config.CVM_ELIGIBLE] = False
        self.assertEqual(derivative_replacement_cost(frame)[config.AMOUNT].item(), 28.)

    def test_replacement_cost_floor(self) -> None:
        self.assertEqual(derivative_replacement_cost(derivative(-10.))[config.AMOUNT].item(), 0.)

    def test_repo_without_qmna(self) -> None:
        self.assertEqual(repo_counterparty_exposure(repos(False))[config.AMOUNT].sum(), 5.)

    def test_repo_with_qmna(self) -> None:
        self.assertEqual(repo_counterparty_exposure(repos(True))[config.AMOUNT].sum(), 0.)

    def test_repo_cannot_net_across_agreements_or_counterparties(self) -> None:
        for column in (config.REPO_NETTING_SET, config.COUNTERPARTY):
            frame = repos(True).assign(**{column: ["one", "two"]})
            self.assertEqual(repo_counterparty_exposure(frame)[config.AMOUNT].sum(), 5.)

    def test_gross_repo_avoids_double_counting(self) -> None:
        frame = repos().assign(**{config.NETTING_MET: False, config.ON_BALANCE_RECEIVABLE: [40., 20.]})
        self.assertEqual(gross_repo_receivables(frame)[config.AMOUNT].sum(), 20.)
        frame[config.NETTING_MET] = True
        self.assertEqual(gross_repo_receivables(frame)[config.AMOUNT].sum(), 0.)

    def test_protection_hedges_losses_and_zero_floor(self) -> None:
        frame = toy_inputs().credit_protection.loc[lambda data: data[config.MONTH] == TEST_MONTHS.min()].copy()
        frame[config.CET1_LOSS] = 5.
        self.assertEqual(sold_credit_protection(frame)[config.AMOUNT].item(), 25.)
        frame[config.MATCHED_HEDGE] = False
        self.assertEqual(sold_credit_protection(frame)[config.AMOUNT].item(), 45.)
        frame[config.CET1_LOSS] = 100.
        self.assertEqual(sold_credit_protection(frame)[config.AMOUNT].item(), 0.)

    def test_daily_and_monthly_averaging(self) -> None:
        inputs = toy_inputs()
        daily = inputs.daily_assets.head(3).copy()
        daily[config.ASSETS], daily[config.DERIVATIVE_ASSETS] = [100., 110., 120.], 0.
        self.assertEqual(on_balance_sheet_assets(daily)[config.AMOUNT].sum(), 110.)
        commitments = pd.DataFrame({config.MONTH: TEST_MONTHS, config.COMMITMENT_TYPE: config.GUARANTEE,
                                    config.MATURITY: 1., config.NOTIONAL: [9., 12., 15.]})
        monthly = monthly_exposure_components(replace(inputs, commitments=commitments))
        result = monthly.loc[monthly[config.COMPONENT] == "off_balance_commitments", config.AMOUNT]
        self.assertEqual(result.tolist(), [9., 12., 15.])
        self.assertEqual(result.mean(), 12.)

    def test_monthly_mean_is_not_transaction_weighted(self) -> None:
        inputs = toy_inputs()
        frame = inputs.commitments.copy()
        extra = frame.loc[frame[config.MONTH] == TEST_MONTHS.min()].copy()
        extra[config.NOTIONAL] = 0.
        before = total_leverage_exposure(inputs)[config.AMOUNT].sum()
        after = total_leverage_exposure(replace(inputs, commitments=pd.concat([frame, extra])))[config.AMOUNT].sum()
        self.assertEqual(before, after)

    def test_ccf_types_maturity_boundary_and_floor(self) -> None:
        kinds = [config.UNCANCELABLE, config.COMMITMENT, config.COMMITMENT, config.TRADE,
                 config.TRANSACTION, config.PERFORMANCE_BOND, config.PERFORMANCE_LC, config.GUARANTEE, config.FINANCIAL_LC]
        frame = pd.DataFrame({config.COMMITMENT_TYPE: kinds, config.MATURITY: [.5, 1., 1.01, 1., 2., 2., 2., 2., 2.],
                              config.NOTIONAL: 100.})
        result = off_balance_sheet_exposure(frame)
        np.testing.assert_allclose(result[config.CCF], [.1, .2, .5, .2, .5, .5, .5, 1., 1.])
        np.testing.assert_allclose(result[config.AMOUNT], [10., 20., 50., 20., 50., 50., 50., 100., 100.])
        self.assertGreaterEqual(result[config.CCF].min(), .1)

    def test_custodial_exclusion_uses_daily_lesser_amount(self) -> None:
        daily = toy_inputs().daily_assets.head(2).copy()
        daily[config.CENTRAL_BANK], daily[config.CUSTODIAL_DEPOSITS] = [8., 2.], [6., 7.]
        self.assertEqual(custodial_exclusion(daily)[config.AMOUNT].item(), 0.)
        result = custodial_exclusion(daily, LeverageSettings(custodial_banking_organization=True))
        self.assertEqual(result[config.AMOUNT].item(), -4.)

    def test_deductions_once_in_denominator_and_not_twice_in_capital(self) -> None:
        inputs = toy_inputs()
        inputs.daily_assets[config.DEDUCTIONS] = 5.
        total = total_leverage_exposure(inputs)[config.AMOUNT].sum()
        self.assertEqual(total, 1061.)
        result = leverage_ratios(60., 1000., 5., total)
        self.assertEqual(result[config.TIER1].item(), 60.)
        self.assertEqual(result[config.LEVERAGE_DENOMINATOR].item(), 995.)

    def test_sales_treatment_and_received_securities_adjustments(self) -> None:
        daily = toy_inputs().daily_assets.copy()
        daily[config.SALES], daily[config.RECEIVED_SECURITIES] = 12., 7.
        self.assertEqual(on_balance_sheet_assets(daily)[config.AMOUNT].sum(), 975.)


class LeverageBufferTests(unittest.TestCase):
    def test_buffer_and_payout_benchmarks(self) -> None:
        result = leverage_buffer(.036, .01)
        self.assertAlmostEqual(result[config.BUFFER].item(), .006)
        self.assertAlmostEqual(result[config.BUFFER_FRACTION].item(), .6)
        self.assertEqual(result[config.PAYOUT].item(), .4)
        low = leverage_buffer(.029, .01)
        self.assertEqual(low[config.BUFFER].item(), 0.)
        self.assertEqual(low[config.PAYOUT].item(), 0.)
        high = leverage_buffer(.056, .01)
        self.assertTrue(high[config.NO_LIMIT].item())
        self.assertTrue(math.isnan(high[config.PAYOUT].item()))

    def test_payout_boundaries(self) -> None:
        for fraction, expected in ((0., 0.), (.25, 0.), (.25001, .2), (.5, .2), (.50001, .4),
                                   (.75, .4), (.75001, .6), (1., .6)):
            with self.subTest(fraction=fraction):
                self.assertEqual(max_payout_ratio(fraction * .01, .01)[config.PAYOUT].item(), expected)
        self.assertTrue(max_payout_ratio(.010001, .01)[config.NO_LIMIT].item())

    def test_zero_requirement_has_no_leverage_buffer_restriction(self) -> None:
        self.assertTrue(leverage_buffer(.029, 0.)[config.NO_LIMIT].item())
        self.assertAlmostEqual(leverage_buffer(.029, 0.)[config.MINIMUM_HEADROOM].item(), -.001)

    def test_subsidiary_requirement_cap(self) -> None:
        self.assertEqual(leverage_buffer_requirement(.03, subsidiary=True), .01)
        self.assertEqual(leverage_buffer_requirement(.015, subsidiary=True), .0075)
        self.assertEqual(leverage_buffer_requirement(.02), .01)


class LeverageValidationTests(unittest.TestCase):
    def test_bad_numeric_and_boolean_inputs(self) -> None:
        for column, value in ((config.ADDON, -1.), (config.V, math.nan), (config.END_USER, "False")):
            with self.subTest(column=column), self.assertRaises(ValueError):
                derivative_pfe(derivative().assign(**{column: value}))
        with self.assertRaises(ValueError):
            derivative_replacement_cost(derivative().assign(**{config.CVM_ELIGIBLE: "True"}))

    def test_missing_or_misaligned_months_rejected(self) -> None:
        inputs = toy_inputs()
        for frame in (inputs.derivatives.loc[inputs.derivatives[config.MONTH] != TEST_MONTHS.min()],
                      inputs.derivatives.assign(**{config.MONTH: pd.Timestamp("2026-04-30")})):
            with self.assertRaises(ValueError):
                total_leverage_exposure(replace(inputs, derivatives=frame))

    def test_incomplete_daily_path_rejected(self) -> None:
        inputs = toy_inputs()
        for frame in (inputs.daily_assets.head(3), inputs.daily_assets.sort_values(config.DATE, ascending=False)):
            with self.assertRaises(ValueError):
                total_leverage_exposure(replace(inputs, daily_assets=frame))

    def test_duplicate_netting_set_rejected(self) -> None:
        inputs = toy_inputs()
        with self.assertRaises(ValueError):
            total_leverage_exposure(replace(inputs, derivatives=pd.concat([inputs.derivatives, inputs.derivatives])))

    def test_unsupported_ccf_inputs_rejected(self) -> None:
        for kind, maturity in (("unknown", 1.), (config.TRADE, 2.)):
            with self.assertRaises(ValueError):
                off_balance_sheet_exposure(pd.DataFrame({config.COMMITMENT_TYPE: [kind], config.MATURITY: [maturity], config.NOTIONAL: [1.]}))

    def test_invalid_denominators_and_buffer_rejected(self) -> None:
        for arguments in ((60., 10., 10., 100.), (60., 10., 0., 0.), (math.nan, 100., 0., 100.)):
            with self.assertRaises(ValueError):
                leverage_ratios(*arguments)
        with self.assertRaises(ValueError):
            leverage_buffer(.04, -.01)
        with self.assertRaises(ValueError):
            leverage_buffer_requirement(-.01)

    def test_conflicting_qmna_flags_rejected(self) -> None:
        with self.assertRaises(ValueError):
            repo_counterparty_exposure(repos().assign(**{config.QMNA: [True, False]}))


class LeverageIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = run_plan()

    def test_seeded_data_repeatability_and_base_calibration(self) -> None:
        bank = self.plan.bank
        first, second = synthetic_leverage_inputs(bank), synthetic_leverage_inputs(bank)
        for field in first.__dataclass_fields__:
            pd.testing.assert_frame_equal(getattr(first, field), getattr(second, field))
        self.assertEqual(first.derivatives[config.NETTING_SET].nunique(), 10)
        self.assertEqual(first.commitments[config.MONTH].nunique(), 3)
        self.assertAlmostEqual(first.daily_assets[config.ASSETS].mean(), 250.)
        total = total_leverage_exposure(first)[config.AMOUNT].sum()
        self.assertGreaterEqual((bank.cet1 + bank.at1) / total, .05)
        self.assertLessEqual((bank.cet1 + bank.at1) / total, .07)

    def test_tlac_uses_computed_exposure(self) -> None:
        total = self.plan.tables["leverage_exposure_reconciliation"][config.AMOUNT].sum()
        checks = self.plan.tables["tlac_ltd_hypothetical"].set_index(CHECK)
        self.assertAlmostEqual(checks.loc["tlac_leverage", MINIMUM_BN], .075 * total)
        self.assertAlmostEqual(checks.loc["ltd_leverage", MINIMUM_BN], .025 * total)
        self.assertNotEqual(total, 270.)

    def test_projection_has_nine_quarters_and_three_views(self) -> None:
        path = self.plan.tables["slr_path"]
        self.assertEqual(len(path), 54)
        for _, group in path.groupby([config.SCENARIO, config.VIEW]):
            self.assertEqual(group[config.QUARTER].tolist(), list(range(1, 10)))
            np.testing.assert_allclose(group[config.SLR], group[config.TIER1] / group[config.TLE])
            np.testing.assert_allclose(group[config.LEVERAGE_RATIO], group[config.TIER1] / group[config.LEVERAGE_DENOMINATOR])

    def test_projected_assets_and_mix_independent_reconciliation(self) -> None:
        bank = self.plan.bank
        path = self.plan.tables["slr_path"]
        reference = self.plan.tables["leverage_exposure_reconciliation"][config.AMOUNT].sum()
        deduction = bank.equity - bank.at1 - bank.cet1
        for name in self.plan.scenarios:
            group = path.loc[(path[config.SCENARIO] == name) & (path[config.VIEW] == config.CATEGORY_III)].set_index(config.QUARTER)
            balances = self.plan.tables[f"balances_{name}"].set_index(config.QUARTER)
            allowance = self.plan.tables[f"credit_{name}"].groupby(config.QUARTER)[config.CLOSING_ALLOWANCE].sum()
            opening = bank.assets
            for quarter in range(1, 10):
                loans = sum(balances.loc[quarter, pool.name] for pool in bank.portfolios)
                closing = bank.assets + loans - sum(pool.balance for pool in bank.portfolios) - allowance.loc[quarter] + bank.opening_allowance
                average = (opening + closing) / 2
                self.assertAlmostEqual(group.loc[quarter, config.PROJECTED_ASSETS], closing)
                self.assertAlmostEqual(group.loc[quarter, config.TLE], (reference + deduction) * average / bank.assets - deduction)
                opening = closing

    def test_minimum_summary_and_hurdles(self) -> None:
        path = self.plan.tables["slr_path"]
        for record in self.plan.tables["leverage_minima"].to_dict("records"):
            group = path.loc[(path[config.SCENARIO] == record[config.SCENARIO]) & (path[config.VIEW] == record[config.VIEW])]
            minimum = group.loc[group[config.SLR].idxmin()]
            self.assertEqual(record[config.MINIMUM_QUARTER], minimum[config.QUARTER])
            self.assertEqual(record[config.MINIMUM_RATIO], minimum[config.SLR])
            self.assertAlmostEqual(record[config.BUFFER_HEADROOM], minimum[config.SLR] - .03 - record[config.BUFFER_REQUIREMENT])

    def test_sensitivities_hand_computed(self) -> None:
        inputs = synthetic_leverage_inputs(self.plan.bank)
        total = total_leverage_exposure(inputs)[config.AMOUNT].sum()
        result = leverage_sensitivities(inputs, 23.)
        changes = result.set_index(config.SENSITIVITY)[config.EXPOSURE_CHANGE]
        self.assertAlmostEqual(changes.loc["repo_matched_book_plus_10bn_illustrative"], 10.)
        self.assertAlmostEqual(changes.loc["custodial_exclusion_illustrative"], -6.)
        np.testing.assert_allclose(result[config.SLR_CHANGE_BP], (23. / result[config.TLE] - 23. / total) * 10000)
        self.assertLess(changes.loc["remove_1_4_factor_illustrative"], 0.)

    def test_risk_based_tier1_ratio_unchanged(self) -> None:
        for name in self.plan.scenarios:
            capital = self.plan.tables[f"capital_{name}"]
            np.testing.assert_allclose(capital[RISK_TIER1_RATIO], (capital[config.CLOSING_CET1] + self.plan.bank.at1) / capital[RWA])

    def test_scale_holds_deductions_fixed(self) -> None:
        inputs = toy_inputs()
        inputs.daily_assets[config.DEDUCTIONS] = 5.
        scaled = scale_leverage_inputs(inputs, 2.)
        self.assertEqual(total_leverage_exposure(scaled)[config.AMOUNT].sum(), 2127.)
        self.assertEqual(scaled.daily_assets[config.DEDUCTIONS].mean(), 5.)
