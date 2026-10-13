"""Rate-sensitive interest income, macro-sensitive fees, and expense projections."""

from dataclasses import dataclass
import math

import pandas as pd

from .models import Bank
from .scenario import Scenario
from .validation import validate_balance_paths


@dataclass(frozen=True)
class PPNRSettings:
    """Stylized funding response and expense assumptions."""

    deposit_beta: float = .5
    deposit_repricing_speed: float = .5
    securities_repricing_speed: float = .12
    annual_expense_inflation: float = .02
    initial_rate_3m: float = 4.5
    initial_rate_10y: float = 4.2

    def __post_init__(self) -> None:
        if not all(math.isfinite(x) for x in vars(self).values()):
            raise ValueError("PPNR settings must be finite")
        if any(not 0 <= x <= 1 for x in (self.deposit_beta, self.deposit_repricing_speed, self.securities_repricing_speed)):
            raise ValueError("betas and speeds must lie between zero and one")
        if self.annual_expense_inflation <= -1:
            raise ValueError("expense growth must exceed minus one")


def income_statement_run_rate(bank: Bank, settings: PPNRSettings = PPNRSettings()) -> pd.DataFrame:
    """Return annual opening income at the initial rate anchors."""
    income = sum(p.balance * p.effective_rate for p in bank.portfolios) + bank.securities * bank.securities_yield + bank.cash * settings.initial_rate_3m / 100
    expense = bank.deposits * bank.deposit_rate + bank.borrowings * bank.borrowing_rate
    fees = sum(bank.fee_run_rate)
    return pd.DataFrame({"line": ["interest_income", "interest_expense", "net_interest_income", "noninterest_income", "noninterest_expense", "ppnr"],
                         "annual_bn": [income, expense, income - expense, fees, bank.expense_run_rate, income - expense + fees - bank.expense_run_rate]})


def project_ppnr(bank: Bank, scenario: Scenario, balance_paths: pd.DataFrame, *, quarters: int = 9,
                 settings: PPNRSettings = PPNRSettings()) -> pd.DataFrame:
    """Project quarterly PPNR using average balances and gradual repricing."""
    validate_balance_paths(bank.portfolios, scenario, balance_paths, quarters)
    loan_yields = {p.name: p.effective_rate for p in bank.portfolios}
    previous = {p.name: p.balance for p in bank.portfolios}
    initial_loans = sum(previous.values())
    if initial_loans <= 0:
        raise ValueError("PPNR deposit scaling requires a positive opening loan book")
    deposit_rate, security_yield = bank.deposit_rate, bank.securities_yield
    previous_deposits = bank.deposits
    rows = []
    for index in range(quarters):
        macro = scenario.macro(index)
        short_change = (macro["rate_3m"] - settings.initial_rate_3m) / 100
        long_change = (macro["rate_10y"] - settings.initial_rate_10y) / 100
        deposit_target = max(0.0, bank.deposit_rate + settings.deposit_beta * short_change)
        deposit_rate += settings.deposit_repricing_speed * (deposit_target - deposit_rate)
        security_target = max(0.0, bank.securities_yield + long_change)
        security_yield += settings.securities_repricing_speed * (security_target - security_yield)
        closing = {p.name: float(balance_paths.iloc[index][p.name]) for p in bank.portfolios}
        if any(not math.isfinite(value) or value < 0 for value in closing.values()):
            raise ValueError("loan balances must be finite and nonnegative")
        loan_interest = 0.0
        for pool in bank.portfolios:
            target = max(0.0, pool.effective_rate + pool.short_rate_weight * short_change + (1 - pool.short_rate_weight) * long_change)
            loan_yields[pool.name] += pool.repricing_speed * (target - loan_yields[pool.name])
            loan_interest += (previous[pool.name] + closing[pool.name]) / 2 * loan_yields[pool.name] / 4
        deposits = bank.deposits * sum(closing.values()) / initial_loans
        average_deposits = (previous_deposits + deposits) / 2
        borrowing_rate = max(0.0, bank.borrowing_rate + .8 * short_change)
        interest_income = loan_interest + bank.securities * security_yield / 4 + bank.cash * max(0.0, macro["rate_3m"] / 100) / 4
        interest_expense = (average_deposits * deposit_rate / 4
                            + (bank.borrowings - bank.tier2) * borrowing_rate / 4
                            + bank.tier2 * bank.borrowing_rate / 4)
        nii = interest_income - interest_expense
        earning_assets = sum((previous[name] + closing[name]) / 2 for name in closing) + bank.securities + bank.cash
        fees = bank.fee_run_rate
        transaction_fees = fees[0] / 4 * max(.2, 1 + .02 * (macro["real_gdp_growth"] - 2) - .025 * (macro["unemployment"] - 4.2))
        wealth_fees = fees[1] / 4 * (macro["equity_index"] / 100) ** .65
        origination_fees = fees[2] / 4 * max(.2, 1 + .03 * (macro["real_gdp_growth"] - 2)) * macro["house_prices"] / 100
        noninterest_income = transaction_fees + wealth_fees + origination_fees
        noninterest_expense = bank.expense_run_rate / 4 * (1 + settings.annual_expense_inflation) ** ((index + 1) / 4) * (1 + .016 * max(0, macro["unemployment"] - 4.2))
        rows.append({"quarter": index + 1, "interest_income": interest_income,
                     "interest_expense": interest_expense, "nii": nii, "nim": 4 * nii / earning_assets,
                     "earning_assets": earning_assets, "deposit_balance": deposits, "deposit_rate": deposit_rate,
                     "securities_yield": security_yield, "transaction_fees": transaction_fees,
                     "wealth_fees": wealth_fees, "origination_fees": origination_fees,
                     "noninterest_income": noninterest_income, "noninterest_expense": noninterest_expense,
                     "ppnr": nii + noninterest_income - noninterest_expense})
        previous, previous_deposits = closing, deposits
    return pd.DataFrame(rows)
