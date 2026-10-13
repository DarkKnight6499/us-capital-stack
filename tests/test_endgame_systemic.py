"""Capital framework benchmarks, floor cases, scoring, and debt eligibility tests."""

import math
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from _bootstrap import temporary_directory
from capital_stack.data import reference_scenario, synthetic_bank
from capital_stack.endgame import EndgameSettings, business_indicator, business_indicator_component, compare_endgame, credit_rwa_table, current_standardized_rwa, operational_rwa, output_floor
from capital_stack.planning import synthetic_business_history
from capital_stack.reporting import markdown_table, write_table
from capital_stack.scenario import load_fed_scenario
from capital_stack.systemic import INDICATORS, eligible_debt, method1_score, method1_surcharge, synthetic_systemic_inputs, tlac_ltd_check


class EndgameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bank = synthetic_bank()
        cls.history = synthetic_business_history(cls.bank)

    def test_bic_analytic_bands(self) -> None:
        for indicator, expected in ((0., 0.), (.5, .06), (1., .12), (10., 1.47), (30., 4.47), (40., 6.27)):
            self.assertAlmostEqual(business_indicator_component(indicator), expected)

    def test_bic_continuity_and_marginal_rates(self) -> None:
        for boundary in (1., 30.):
            self.assertLess(abs(business_indicator_component(boundary + 1e-8) - business_indicator_component(boundary - 1e-8)), 1e-8)
        self.assertAlmostEqual(business_indicator_component(20.) - business_indicator_component(19.), .15)

    def test_bi_absolute_values_and_interest_cap(self) -> None:
        history = pd.DataFrame({"interest_income": [20., 0., 20.], "interest_expense": [0., 20., 0.],
                                "earning_assets": [100.] * 3, "dividend_income": [1.] * 3,
                                "fee_income": [2.] * 3, "fee_expense": [3.] * 3,
                                "other_income": [4.] * 3, "other_expense": [2.] * 3,
                                "trading_revenue": [3., -3., 3.], "banking_financial_revenue": [-1.] * 3})
        self.assertAlmostEqual(business_indicator(history), 14.25)

    def test_operational_rwa_analytic(self) -> None:
        self.assertAlmostEqual(operational_rwa(10.), 18.375)
        self.assertAlmostEqual(operational_rwa(10., 2.), 36.75)

    def test_output_floor_binding(self) -> None:
        self.assertAlmostEqual(output_floor(60., 100.), 72.5)

    def test_output_floor_nonbinding(self) -> None:
        self.assertEqual(output_floor(80., 100.), 80.)

    def test_output_floor_equality_and_zero(self) -> None:
        self.assertEqual(output_floor(72.5, 100.), 72.5)
        self.assertEqual(output_floor(0., 0.), 0.)

    def test_output_floor_scaling(self) -> None:
        self.assertAlmostEqual(output_floor(120., 200.), 2 * output_floor(60., 100.))

    def test_current_rwa_additivity(self) -> None:
        frame = credit_rwa_table(self.bank)
        self.assertAlmostEqual(current_standardized_rwa(self.bank), frame.current_credit_rwa.sum() + self.bank.current_market_rwa)
        np.testing.assert_allclose(frame.expanded_credit_rwa - frame.current_credit_rwa, frame.rwa_change)

    def test_conditional_retail_weight_benchmarks(self) -> None:
        transactors = credit_rwa_table(self.bank, EndgameSettings(card_transactor_share=1.)).set_index("exposure")
        revolvers = credit_rwa_table(self.bank, EndgameSettings(card_transactor_share=0.)).set_index("exposure")
        self.assertAlmostEqual(transactors.loc["cards", "expanded_weight"], .55)
        self.assertAlmostEqual(revolvers.loc["cards", "expanded_weight"], .85)

    def test_qualifying_corporate_weight_benchmarks(self) -> None:
        frame = credit_rwa_table(self.bank, EndgameSettings(investment_grade_public_share=1.)).set_index("exposure")
        self.assertAlmostEqual(frame.loc["ci", "expanded_weight"], .65)

    def test_impact_ratio_and_capital_reconciliation(self) -> None:
        frame = compare_endgame(self.bank, self.history, .07)
        np.testing.assert_allclose(frame.cet1_ratio * frame.total_rwa, self.bank.cet1)
        np.testing.assert_allclose(frame.incremental_required_cet1_bn, frame.required_cet1_bn - frame.required_cet1_bn.iloc[0])
        np.testing.assert_allclose(frame.required_cet1_bn + frame.capital_headroom_bn, self.bank.cet1)
        starting_ratio = frame.cet1_ratio.iloc[0]
        np.testing.assert_allclose((self.bank.cet1 + frame.cet1_to_preserve_opening_ratio_bn) / frame.total_rwa, starting_ratio)

    def test_us_dual_stack_keeps_standardized_requirement(self) -> None:
        frame = compare_endgame(self.bank, self.history, .07, EndgameSettings(standardized_market_rwa=500.))
        us = frame[frame.framework == "historical_2023_us_dual_stack_proxy"].iloc[0]
        self.assertGreaterEqual(us.total_rwa, us.proposed_standardized_rwa)
        self.assertGreaterEqual(us.total_rwa, .725 * us.us_market_floor_base)
        self.assertGreaterEqual(us.total_rwa, us.expanded_raw_rwa)

    def test_unverified_weights_labelled(self) -> None:
        frame = credit_rwa_table(self.bank).set_index("exposure")
        for name in ("mortgage", "cre"):
            self.assertIn("stylized/unverified", frame.loc[name, "status"])

    def test_framework_components_reconcile_with_binding_adjustments(self) -> None:
        for settings in (EndgameSettings(), EndgameSettings(standardized_market_rwa=500.)):
            frame = compare_endgame(self.bank, self.history, .07, settings)
            total = frame.credit_rwa + frame.operational_rwa + frame.market_rwa + frame.cva_rwa + frame.floor_adjustment_rwa + frame.dual_stack_adjustment_rwa
            np.testing.assert_allclose(total, frame.total_rwa, atol=1e-10)
            self.assertTrue((frame.floor_adjustment_rwa >= 0).all())
            self.assertTrue((frame.dual_stack_adjustment_rwa >= 0).all())

    def test_invalid_endgame_inputs(self) -> None:
        with self.assertRaises(ValueError):
            business_indicator_component(-1.)
        with self.assertRaises(ValueError):
            operational_rwa(1., .9)
        with self.assertRaises(ValueError):
            output_floor(1., 2., 1.1)
        with self.assertRaises(ValueError):
            business_indicator(self.history.iloc[:2])


class SystemicTests(unittest.TestCase):
    def test_method1_size_benchmark(self) -> None:
        amounts = dict.fromkeys(INDICATORS, 0.)
        denominators = dict.fromkeys(INDICATORS, 100.)
        amounts["total_exposures"] = 10.
        score, table = method1_score(amounts, denominators)
        self.assertAlmostEqual(score, 200.)
        self.assertEqual(len(table.category.unique()), 5)
        self.assertEqual(len(table), 12)

    def test_substitutability_cap(self) -> None:
        amounts = {name: 100. if category == "substitutability" else 0.
                   for name, (category, _) in INDICATORS.items()}
        score, table = method1_score(amounts, dict.fromkeys(INDICATORS, 100.))
        self.assertAlmostEqual(score, 100.)
        self.assertGreater(table.uncapped_score_bp.sum(), table.score_bp.sum())

    def test_score_invariant_under_unit_conversion(self) -> None:
        amounts, denominators = synthetic_systemic_inputs()
        original, _ = method1_score(amounts, denominators)
        converted, _ = method1_score({key: value * 1000 for key, value in amounts.items()},
                                    {key: value * 1000 for key, value in denominators.items()})
        self.assertAlmostEqual(original, converted)

    def test_bucket_thresholds(self) -> None:
        for score, expected in ((129.9, 0.), (130., .01), (230., .015), (330., .02), (430., .025),
                                (530., .035), (630., .045), (730., .055), (830., .065)):
            self.assertAlmostEqual(method1_surcharge(score), expected)

    def test_debt_maturity_boundaries(self) -> None:
        debt = pd.DataFrame({"principal_bn": [2.] * 4, "days_to_maturity": [364, 365, 729, 730], "eligible": [True] * 4})
        result = eligible_debt(debt)
        self.assertEqual(result["ltd_eligible_bn"], 4.)
        self.assertEqual(result["tlac_eligible_debt_bn"], 6.)

    def test_ineligible_debt_excluded(self) -> None:
        debt = pd.DataFrame({"principal_bn": [100.], "days_to_maturity": [1000], "eligible": [False]})
        self.assertEqual(eligible_debt(debt)["tlac_eligible_debt_bn"], 0.)

    def test_tlac_ltd_rule_benchmarks(self) -> None:
        debt = pd.DataFrame({"principal_bn": [20.], "days_to_maturity": [1000], "eligible": [True]})
        frame = tlac_ltd_check(10., 2., debt, 100., 200., .02, .015, applicable=True).set_index("check")
        self.assertEqual(frame.loc["tlac_risk", "minimum_bn"], 18.)
        self.assertEqual(frame.loc["tlac_leverage", "minimum_bn"], 15.)
        self.assertAlmostEqual(frame.loc["ltd_risk", "minimum_bn"], 8.)
        self.assertAlmostEqual(frame.loc["ltd_leverage", "minimum_bn"], 6.5)
        self.assertTrue(frame.meets_hypothetical_minimum.all())

    def test_tier2_does_not_enter_tlac_numerator(self) -> None:
        debt = pd.DataFrame({"principal_bn": [0.], "days_to_maturity": [1000], "eligible": [True]})
        frame = tlac_ltd_check(10., 2., debt, 100., 200., 0., 0.)
        self.assertEqual(frame.iloc[0].eligible_amount_bn, 12.)
        self.assertFalse(frame.iloc[0].meets_hypothetical_minimum)
        self.assertFalse(frame.applicable.any())

    def test_invalid_systemic_inputs(self) -> None:
        amounts, denominators = synthetic_systemic_inputs()
        denominators["total_exposures"] = 0.
        with self.assertRaises(ValueError):
            method1_score(amounts, denominators)
        with self.assertRaises(ValueError):
            method1_surcharge(math.nan)
        debt = pd.DataFrame({"principal_bn": [1.], "days_to_maturity": [500], "eligible": ["False"]})
        with self.assertRaises(ValueError):
            eligible_debt(debt)


class AdapterReportingTests(unittest.TestCase):
    def test_fed_domestic_adapter(self) -> None:
        frame = pd.DataFrame({"Date": ["Q1 2025", "Q2 2025"], "Real GDP growth": [2., 1.],
                              "Unemployment rate": [4.2, 5.], "House Price Index": [300., 270.],
                              "Commercial Real Estate Price Index": [200., 180.],
                              "Dow Jones Total Stock Market Index": [50000., 40000.],
                              "3-month Treasury rate": [3., 2.], "10-year Treasury yield": [4., 3.],
                              "BBB corporate yield": [5.5, 6.], "Market Volatility Index": [18., 40.]})
        with temporary_directory() as folder:
            path = Path(folder) / "fed_layout_synthetic.csv"
            frame.to_csv(path, index=False)
            loaded = load_fed_scenario(path, "fed", {"house_prices": 300., "cre_prices": 200., "equity_index": 50000.})
        self.assertEqual(loaded.frame.quarter.tolist(), [1, 2])
        self.assertEqual(loaded.frame.bbb_spread.tolist(), [1.5, 3.])
        self.assertEqual(loaded.frame.house_prices.tolist(), [100., 90.])
        self.assertFalse(loaded.synthetic)

    def test_write_tables_preserves_data(self) -> None:
        frame = pd.DataFrame({"name": ["synthetic"], "value": [1.25]})
        with temporary_directory() as folder:
            write_table(frame, Path(folder), "table")
            loaded = pd.read_csv(Path(folder) / "table.csv")
            pd.testing.assert_frame_equal(frame, loaded)
            self.assertIn("1.250000", (Path(folder) / "table.md").read_text(encoding="utf-8"))

    def test_markdown_escapes_pipes(self) -> None:
        self.assertIn("left/right", markdown_table(pd.DataFrame({"text": ["left|right"]})))
