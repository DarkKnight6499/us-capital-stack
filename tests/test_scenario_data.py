"""Input invariants, reproducibility, and scenario I/O tests."""

from dataclasses import replace
from pathlib import Path
import unittest

import numpy as np
import pandas as pd

from _bootstrap import temporary_directory
from capital_stack.data import reference_scenario, synthetic_bank, synthetic_scenarios
from capital_stack.scenario import LONG_RUN, Scenario, forecast_macro, load_scenario


class ScenarioDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.bank = synthetic_bank()
        cls.scenarios = synthetic_scenarios()

    def test_balance_sheet_identity(self) -> None:
        frame = self.bank.balance_sheet()
        self.assertAlmostEqual(frame[frame.side == "assets"].amount_bn.sum(), frame[frame.side == "funding"].amount_bn.sum())
        self.assertAlmostEqual(self.bank.assets, 250.)

    def test_capital_instruments_reconcile(self) -> None:
        self.assertGreaterEqual(self.bank.equity - self.bank.at1, self.bank.cet1)
        self.assertLessEqual(self.bank.tier2, self.bank.borrowings)

    def test_bank_is_seeded(self) -> None:
        self.assertEqual(self.bank, synthetic_bank())
        self.assertNotEqual(self.bank.portfolios[0].balance, synthetic_bank(7).portfolios[0].balance)

    def test_paths_are_seeded_and_synthetic(self) -> None:
        other = synthetic_scenarios()
        for name, scenario in self.scenarios.items():
            pd.testing.assert_frame_equal(scenario.frame, other[name].frame)
            self.assertTrue(scenario.synthetic)
            self.assertEqual(len(scenario.frame), 13)

    def test_adverse_has_severity(self) -> None:
        base, stress = self.scenarios["baseline"].frame, self.scenarios["severely_adverse"].frame
        self.assertTrue((stress.unemployment > base.unemployment).all())
        self.assertTrue((stress.house_prices < base.house_prices).all())

    def test_scenario_loader_round_trip(self) -> None:
        with temporary_directory() as folder:
            path = Path(folder) / "scenario.csv"
            self.scenarios["baseline"].to_csv(path)
            loaded = load_scenario(path, "baseline", synthetic=True)
            pd.testing.assert_frame_equal(loaded.frame, self.scenarios["baseline"].frame, atol=1e-9, rtol=1e-9)

    def test_mapped_loader_percent_conversion_and_rebase(self) -> None:
        frame = reference_scenario(2).frame.copy().rename(columns={"unemployment": "Jobless", "quarter": "Period"})
        frame["Period"] = ["2025Q1", "2025Q2"]
        for key in ("Jobless", "real_gdp_growth", "rate_3m", "rate_10y", "bbb_spread"):
            frame[key] /= 100
        frame["house_prices"] = [300., 270.]
        with temporary_directory() as folder:
            path = Path(folder) / "mapped.csv"
            frame.to_csv(path, index=False)
            loaded = load_scenario(path, "mapped", column_map={"Jobless": "unemployment", "Period": "date"}, rates_in_decimals=True, rebase_indices=True)
        self.assertEqual(loaded.frame.quarter.tolist(), [1, 2])
        self.assertEqual(loaded.frame.house_prices.tolist(), [100., 90.])
        self.assertAlmostEqual(loaded.frame.unemployment.iloc[0], 4.2)

    def test_loader_rejects_date_gaps(self) -> None:
        frame = reference_scenario(2).frame.drop(columns="quarter")
        frame["date"] = ["2025Q1", "2025Q3"]
        with temporary_directory() as folder:
            path = Path(folder) / "gap.csv"
            frame.to_csv(path, index=False)
            with self.assertRaises(ValueError):
                load_scenario(path, "gap")

    def test_scenario_rejects_nonfinite(self) -> None:
        frame = reference_scenario().frame.copy()
        frame.loc[0, "vix"] = np.nan
        with self.assertRaises(ValueError):
            Scenario("bad", frame)

    def test_scenario_rejects_nonpositive_prices(self) -> None:
        frame = reference_scenario().frame.copy()
        frame.loc[0, "house_prices"] = 0.
        with self.assertRaises(ValueError):
            Scenario("bad", frame)

    def test_scenario_rejects_quarter_gaps(self) -> None:
        frame = reference_scenario().frame.copy()
        frame.loc[1, "quarter"] = 9
        with self.assertRaises(ValueError):
            Scenario("bad", frame)

    def test_scenario_copies_input(self) -> None:
        frame = reference_scenario().frame.copy()
        scenario = Scenario("copied", frame)
        frame.loc[0, "unemployment"] = 99.
        self.assertAlmostEqual(scenario.macro(0)["unemployment"], 4.2)

    def test_reversion_endpoint_and_midpoint(self) -> None:
        scenario = self.scenarios["severely_adverse"]
        endpoint = scenario.macro(7)["unemployment"]
        self.assertEqual(forecast_macro(scenario, 0, 8)["unemployment"], endpoint)
        self.assertAlmostEqual(forecast_macro(scenario, 0, 10)["unemployment"], (endpoint + 4.2) / 2)
        self.assertEqual(forecast_macro(scenario, 0, 12), LONG_RUN)

    def test_reversion_uses_available_endpoint(self) -> None:
        scenario = self.scenarios["severely_adverse"]
        self.assertEqual(forecast_macro(scenario, 13, 1), LONG_RUN)
        self.assertEqual(forecast_macro(scenario, 12, 1), scenario.macro(12))
        self.assertEqual(forecast_macro(scenario, 12, 5), LONG_RUN)

    def test_zero_forecast_uses_long_run(self) -> None:
        self.assertEqual(forecast_macro(self.scenarios["severely_adverse"], 0, 1, forecast_quarters=0), LONG_RUN)

    def test_invalid_bank_and_portfolio_inputs(self) -> None:
        with self.assertRaises(ValueError):
            replace(self.bank, deposits=self.bank.deposits + 1)
        with self.assertRaises(ValueError):
            replace(self.bank.portfolios[0], maturity_quarters=0)
        with self.assertRaises(ValueError):
            replace(self.bank.portfolios[0], lgd=1.1)
