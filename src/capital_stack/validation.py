"""Shared validation for aligned quarterly portfolio balances."""

import numpy as np
import pandas as pd

from .models import Portfolio
from .scenario import Scenario


def validate_balance_paths(portfolios: tuple[Portfolio, ...], scenario: Scenario,
                           balances: pd.DataFrame, quarters: int) -> None:
    """Reject incomplete, nonfinite, negative, or misaligned balance inputs."""
    if isinstance(quarters, bool) or not isinstance(quarters, int) or quarters < 1:
        raise ValueError("projection horizon must be a positive integer")
    names = [pool.name for pool in portfolios]
    if not names or len(set(names)) != len(names):
        raise ValueError("portfolio names must be unique and nonempty")
    if quarters > len(scenario.frame) or quarters > len(balances):
        raise ValueError("projection horizon exceeds scenario or balances")
    if not {"quarter", *names}.issubset(balances.columns) or balances.columns.duplicated().any():
        raise ValueError("balance paths need unique quarter and portfolio columns")
    used = balances.iloc[:quarters]
    if not np.array_equal(used.quarter.to_numpy(), np.arange(1, quarters + 1)):
        raise ValueError("balance paths must use aligned consecutive quarters")
    values = used[names].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values < 0).any():
        raise ValueError("loan balances must be finite and nonnegative")
