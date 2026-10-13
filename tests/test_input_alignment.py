"""Prevent silent quarter misalignment and missing-data aggregation."""

import unittest

import numpy as np
import pandas as pd

import _bootstrap
from capital_stack.cecl import project_credit
from capital_stack.planning import run_plan
from capital_stack.ppnr import project_ppnr
from capital_stack.projection import project_capital, project_rwa


class InputAlignmentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = run_plan()
        cls.bank = cls.plan.bank
        cls.scenario = cls.plan.scenarios["baseline"]
        cls.balances = cls.plan.tables["balances_baseline"]
        cls.opening = cls.plan.tables["credit_baseline"].query("quarter == 1").set_index("portfolio").opening_allowance.to_dict()

    def assert_balance_rejected(self, balances: pd.DataFrame, quarters: int = 9) -> None:
        functions = (
            lambda: project_credit(self.bank.portfolios, self.scenario, balances, self.opening, quarters=quarters),
            lambda: project_ppnr(self.bank, self.scenario, balances, quarters=quarters),
            lambda: project_rwa(self.bank, self.scenario, balances, quarters=quarters),
        )
        for function in functions:
            with self.subTest(function=function):
                with self.assertRaises(ValueError):
                    function()

    def test_shuffled_balance_quarters_are_rejected(self) -> None:
        self.assert_balance_rejected(self.balances.iloc[::-1].reset_index(drop=True))

    def test_shifted_balance_quarters_are_rejected(self) -> None:
        balances = self.balances.copy()
        balances["quarter"] += 1
        self.assert_balance_rejected(balances)

    def test_missing_pool_column_is_rejected(self) -> None:
        self.assert_balance_rejected(self.balances.drop(columns="ci"))

    def test_negative_balances_are_rejected(self) -> None:
        balances = self.balances.copy()
        balances.loc[0, "ci"] = -1.
        self.assert_balance_rejected(balances)

    def test_nonfinite_balances_are_rejected(self) -> None:
        balances = self.balances.copy()
        balances.loc[0, "ci"] = np.nan
        self.assert_balance_rejected(balances)

    def test_fractional_projection_horizon_is_rejected(self) -> None:
        self.assert_balance_rejected(self.balances, quarters=2.5)

    def test_missing_provision_does_not_disappear_in_sum(self) -> None:
        credit = self.plan.tables["credit_baseline"].copy()
        credit.loc[0, "provision"] = np.nan
        with self.assertRaises(ValueError):
            project_capital(self.bank, self.plan.tables["ppnr_baseline"], credit,
                            self.plan.tables["capital_baseline"][["quarter", "rwa"]])

    def test_invalid_opening_allowance_is_rejected(self) -> None:
        opening = {**self.opening, "ci": np.nan}
        with self.assertRaises(ValueError):
            project_credit(self.bank.portfolios, self.scenario, self.balances, opening)

    def test_capital_rejects_misaligned_rwa_quarters(self) -> None:
        rwa = self.plan.tables["capital_baseline"][["quarter", "rwa"]].iloc[::-1]
        with self.assertRaises(ValueError):
            project_capital(self.bank, self.plan.tables["ppnr_baseline"], self.plan.tables["credit_baseline"], rwa)
