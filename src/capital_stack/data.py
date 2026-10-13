"""Seeded synthetic data. These paths are not published Fed scenario values."""

from dataclasses import replace

import numpy as np
import pandas as pd

from .models import Bank, Portfolio
from .scenario import LONG_RUN, MACRO_COLUMNS, Scenario

DEFAULT_SEED = 20230727


def reference_scenario(quarters: int = 13) -> Scenario:
    """Return a constant long-run reference macro state."""
    if quarters < 1:
        raise ValueError("quarters must be positive")
    return Scenario("reference_synthetic", pd.DataFrame({"quarter": np.arange(1, quarters + 1),
                                                       **{key: np.full(quarters, value) for key, value in LONG_RUN.items()}}))


def synthetic_scenarios(seed: int = DEFAULT_SEED) -> dict[str, Scenario]:
    """Create baseline and severely adverse synthetic paths, each thirteen quarters."""
    rng = np.random.default_rng(seed)
    quarters = np.arange(1, 14)
    baseline = pd.DataFrame({"quarter": quarters,
                            "unemployment": 4.2 + rng.normal(0, 0.035, 13),
                            "real_gdp_growth": 2.0 + rng.normal(0, 0.12, 13),
                            "house_prices": 100 * (1.005 ** quarters),
                            "cre_prices": 100 * (1.003 ** quarters),
                            "equity_index": 100 * (1.012 ** quarters),
                            "rate_3m": np.linspace(4.5, 3.0, 13),
                            "rate_10y": np.linspace(4.2, 4.0, 13),
                            "bbb_spread": 1.5 + rng.normal(0, 0.025, 13),
                            "vix": 18 + rng.normal(0, 0.4, 13)})
    adverse_values = [
        [5.5, 7.0, 8.5, 9.5, 10, 10, 9.8, 9.5, 9.2, 8.8, 8.4, 8, 7.5],
        [-6, -8, -5, -3, -1, 0, 1, 1.5, 2, 2.5, 3, 3, 3],
        [94, 87, 80, 75, 72, 70, 70, 71, 72, 74, 76, 78, 80],
        [90, 80, 70, 63, 58, 55, 55, 56, 58, 60, 63, 66, 70],
        [75, 60, 50, 48, 50, 53, 57, 61, 65, 69, 73, 77, 81],
        [2, 0.5, 0.1, 0.1, 0.1, 0.2, 0.3, 0.5, 0.7, 1, 1.2, 1.5, 1.8],
        [3, 2.3, 2, 1.8, 1.8, 1.9, 2, 2.2, 2.4, 2.6, 2.8, 3, 3.2],
        [3, 4.5, 5.5, 6, 6, 5.7, 5.3, 4.8, 4.3, 3.8, 3.3, 2.8, 2.5],
        [40, 55, 65, 60, 55, 50, 45, 40, 36, 32, 29, 26, 24],
    ]
    adverse = pd.DataFrame({"quarter": quarters, **dict(zip(MACRO_COLUMNS, adverse_values))})
    return {"baseline": Scenario("baseline", baseline), "severely_adverse": Scenario("severely_adverse", adverse)}


def synthetic_bank(seed: int = DEFAULT_SEED) -> Bank:
    """Create a synthetic bank with net assets of USD 250 billion."""
    from .cecl import allowances

    rng = np.random.default_rng(seed)
    weights = np.array([55., 40., 50., 15., 15.]) * rng.uniform(0.98, 1.02, 5)
    balances = weights / weights.sum() * 175
    pools = (
        Portfolio("ci", balances[0], .012, .42, 20, .06, .065, .16, .32, .12, repricing_speed=.2),
        Portfolio("cre", balances[1], .018, .28, 28, .04, .062, .20, .56, .12, "cre_prices", .50, .15, .6),
        Portfolio("mortgage", balances[2], .006, .18, 80, .10, .052, .18, .96, .06, "house_prices", .60, .04, .15),
        Portfolio("cards", balances[3], .035, .88, 12, .03, .19, .17, .08, .04, repricing_speed=.6),
        Portfolio("other_consumer", balances[4], .022, .65, 20, .08, .085, .19, .24, .05, repricing_speed=.1),
    )
    pools = tuple(replace(p, default_fraction=.003) for p in pools)
    opening_acl = sum(float(allowances(p, reference_scenario(), observed_macro=LONG_RUN)["cecl"]) for p in pools)
    return Bank(pools, securities=55, cash=10, other_assets=10 + opening_acl,
                deposits=196, borrowings=30, equity=24, cet1=21, at1=2, tier2=3,
                opening_allowance=opening_acl, deposit_rate=.018, borrowing_rate=.043,
                securities_yield=.037, fee_run_rate=(1.5, .9, .6), expense_run_rate=8.0)


def loan_balance_paths(bank: Bank, scenario: Scenario) -> pd.DataFrame:
    """Return shared end-quarter balances under stylized macro-driven book growth."""
    current = {pool.name: pool.balance for pool in bank.portfolios}
    rows = []
    for index in range(len(scenario.frame)):
        macro = scenario.macro(index)
        growth = np.clip(.004 + .0007 * (macro["real_gdp_growth"] - 2)
                         - .0005 * (macro["unemployment"] - 4.2), -.025, .015)
        current = {name: balance * (1 + float(growth)) for name, balance in current.items()}
        rows.append({"quarter": index + 1, **current})
    return pd.DataFrame(rows)
