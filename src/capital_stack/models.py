"""Validated model inputs. Monetary quantities are USD billions."""

from dataclasses import dataclass
import math

import pandas as pd


@dataclass(frozen=True)
class Portfolio:
    """A homogeneous performing loan pool with synthetic credit parameters."""

    name: str
    balance: float
    annual_pd: float
    lgd: float
    maturity_quarters: int
    annual_prepayment: float
    effective_rate: float
    unemployment_beta: float
    house_beta: float
    spread_beta: float
    collateral: str | None = None
    collateral_beta: float = 0.0
    repricing_speed: float = 0.5
    short_rate_weight: float = 0.8
    origination_pd: float | None = None
    default_fraction: float = 0.0

    def __post_init__(self) -> None:
        numeric = [self.balance, self.annual_pd, self.lgd, self.annual_prepayment,
                   self.effective_rate, self.unemployment_beta, self.house_beta,
                   self.spread_beta, self.collateral_beta, self.repricing_speed,
                   self.short_rate_weight, self.default_fraction]
        if not all(math.isfinite(value) for value in numeric):
            raise ValueError("portfolio values must be finite")
        if not self.name or self.balance < 0 or not 0 < self.annual_pd < 1:
            raise ValueError("invalid portfolio balance or PD")
        if isinstance(self.maturity_quarters, bool) or not isinstance(self.maturity_quarters, int) or self.maturity_quarters < 1:
            raise ValueError("maturity must be a positive integer")
        if not 0 <= self.lgd <= 1 or not 0 <= self.annual_prepayment <= 1:
            raise ValueError("invalid LGD or prepayment")
        if self.effective_rate <= -1:
            raise ValueError("effective rate must exceed minus one")
        if any(value < 0 for value in [self.unemployment_beta, self.house_beta, self.spread_beta, self.collateral_beta]):
            raise ValueError("stress coefficients must be nonnegative")
        if not 0 <= self.repricing_speed <= 1 or not 0 <= self.short_rate_weight <= 1 or not 0 <= self.default_fraction <= 1:
            raise ValueError("invalid fraction")
        if self.collateral not in (None, "house_prices", "cre_prices"):
            raise ValueError("unknown collateral index")
        if self.origination_pd is not None and not 0 < self.origination_pd < 1:
            raise ValueError("origination PD must be strictly interior")


@dataclass(frozen=True)
class Bank:
    """Synthetic opening balance sheet and regulatory capital, net of deductions."""

    portfolios: tuple[Portfolio, ...]
    securities: float
    cash: float
    other_assets: float
    deposits: float
    borrowings: float
    equity: float
    cet1: float
    at1: float
    tier2: float
    opening_allowance: float
    deposit_rate: float
    borrowing_rate: float
    securities_yield: float
    fee_run_rate: tuple[float, float, float]
    expense_run_rate: float
    current_market_rwa: float = 4.0

    def __post_init__(self) -> None:
        if not self.portfolios or len({p.name for p in self.portfolios}) != len(self.portfolios):
            raise ValueError("portfolio names must be unique and nonempty")
        values = [self.securities, self.cash, self.other_assets, self.deposits,
                  self.borrowings, self.equity, self.cet1, self.at1, self.tier2,
                  self.opening_allowance, self.deposit_rate, self.borrowing_rate,
                  self.securities_yield, self.expense_run_rate, self.current_market_rwa,
                  *self.fee_run_rate]
        if not all(math.isfinite(value) and value >= 0 for value in values):
            raise ValueError("bank amounts must be finite and nonnegative")
        if len(self.fee_run_rate) != 3:
            raise ValueError("three fee lines are required")
        if self.cet1 + self.at1 > self.equity or self.tier2 > self.borrowings:
            raise ValueError("capital instruments must reconcile with funding")
        if abs(self.assets - self.deposits - self.borrowings - self.equity) > 1e-8:
            raise ValueError("opening balance sheet does not reconcile")

    @property
    def assets(self) -> float:
        """Return assets net of the opening allowance."""
        return self.cash + self.securities + self.other_assets + sum(p.balance for p in self.portfolios) - self.opening_allowance

    def balance_sheet(self) -> pd.DataFrame:
        """Return a signed opening balance sheet."""
        rows = [("assets", "cash", self.cash), ("assets", "securities", self.securities)]
        rows += [("assets", p.name, p.balance) for p in self.portfolios]
        rows += [("assets", "other_assets", self.other_assets),
                 ("assets", "allowance_contra_asset", -self.opening_allowance),
                 ("funding", "deposits", self.deposits), ("funding", "borrowings", self.borrowings),
                 ("funding", "equity_including_at1", self.equity)]
        return pd.DataFrame(rows, columns=["side", "category", "amount_bn"])
