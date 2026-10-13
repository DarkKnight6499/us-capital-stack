"""Scenario validation, canonical CSV I/O, and explicit Fed CSV mapping."""

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import re

import numpy as np
import pandas as pd

MACRO_COLUMNS = ("unemployment", "real_gdp_growth", "house_prices", "cre_prices",
                 "equity_index", "rate_3m", "rate_10y", "bbb_spread", "vix")
LONG_RUN = dict(zip(MACRO_COLUMNS, (4.2, 2.0, 100.0, 100.0, 100.0, 3.0, 4.0, 1.5, 18.0)))


@dataclass(frozen=True)
class Scenario:
    """Quarterly macro path. Rates and growth use percent units, not decimals."""

    name: str
    frame: pd.DataFrame
    synthetic: bool = True

    def __post_init__(self) -> None:
        required = ["quarter", *MACRO_COLUMNS]
        if not self.name or self.frame.empty or not set(required).issubset(self.frame.columns):
            raise ValueError("scenario needs a name, quarters, and all macro columns")
        clean = self.frame[required].copy().reset_index(drop=True)
        for column in required:
            clean[column] = pd.to_numeric(clean[column], errors="raise")
        if not np.isfinite(clean.to_numpy(dtype=float)).all():
            raise ValueError("scenario values must be finite")
        if not np.array_equal(clean.quarter.to_numpy(), np.arange(1, len(clean) + 1)):
            raise ValueError("quarters must be contiguous and begin at one")
        if not clean.unemployment.between(0, 100).all():
            raise ValueError("invalid unemployment percent")
        if (clean[["house_prices", "cre_prices", "equity_index"]] <= 0).any().any():
            raise ValueError("price indices must be positive")
        if (clean[["bbb_spread", "vix"]] < 0).any().any():
            raise ValueError("spread and VIX must be nonnegative")
        clean["quarter"] = clean.quarter.astype(int)
        object.__setattr__(self, "frame", clean)

    def macro(self, index: int) -> dict[str, float]:
        """Return a macro row using a zero-based offset."""
        if not 0 <= index < len(self.frame):
            raise IndexError("macro offset outside scenario")
        return {key: float(self.frame.iloc[index][key]) for key in MACRO_COLUMNS}

    def to_csv(self, path: str | Path) -> None:
        """Write a canonical numeric scenario file."""
        self.frame.to_csv(path, index=False, float_format="%.12g")


def load_scenario(path: str | Path, name: str, *, column_map: Mapping[str, str] | None = None,
                  rates_in_decimals: bool = False, rebase_indices: bool = False,
                  synthetic: bool = False) -> Scenario:
    """Load a canonical file or map actual Fed headers to canonical column names."""
    frame = pd.read_csv(path)
    if column_map:
        if len(set(column_map.values())) != len(column_map):
            raise ValueError("column map must have unique destination names")
        frame = frame.rename(columns=dict(column_map))
    if frame.columns.duplicated().any():
        raise ValueError("duplicate mapped columns")
    if "quarter" not in frame and "date" in frame:
        labels = frame["date"].astype(str).str.strip().str.replace(":", "", regex=False).str.replace(" ", "", regex=False)
        labels = labels.map(lambda value: re.sub(r"^Q([1-4])(\d{4})$", r"\2Q\1", value))
        periods = pd.PeriodIndex(labels, freq="Q")
        if not np.array_equal(periods.asi8, periods.asi8[0] + np.arange(len(periods))):
            raise ValueError("Fed dates must be consecutive increasing quarters")
        frame["quarter"] = np.arange(1, len(frame) + 1)
    if rates_in_decimals:
        for key in ("unemployment", "real_gdp_growth", "rate_3m", "rate_10y", "bbb_spread"):
            frame[key] = pd.to_numeric(frame[key]) * 100
    if rebase_indices:
        for key in ("house_prices", "cre_prices", "equity_index"):
            values = pd.to_numeric(frame[key])
            if values.empty or values.iloc[0] <= 0:
                raise ValueError("cannot rebase empty or nonpositive index")
            frame[key] = values / values.iloc[0] * 100
    return Scenario(name, frame, synthetic)


FED_HEADERS = {
    "date": "date", "real gdp growth": "real_gdp_growth", "unemployment rate": "unemployment",
    "house price index": "house_prices", "commercial real estate price index": "cre_prices",
    "dow jones total stock market index": "equity_index", "3-month treasury rate": "rate_3m",
    "10-year treasury yield": "rate_10y", "bbb corporate yield": "bbb_yield",
    "market volatility index": "vix", "market volatility index (vix)": "vix",
}


def load_fed_scenario(path: str | Path, name: str, price_bases: Mapping[str, float],
                      *, column_map: Mapping[str, str] | None = None) -> Scenario:
    """Load a domestic Fed-style CSV, derive BBB spread, and use pre-scenario price bases."""
    frame = pd.read_csv(path, thousands=",")
    automatic = {column: FED_HEADERS.get(" ".join(str(column).strip().lower().split()), column)
                 for column in frame.columns}
    if column_map:
        automatic.update(column_map)
    frame = frame.rename(columns=automatic)
    if frame.columns.duplicated().any():
        raise ValueError("duplicate Fed columns after mapping")
    if "bbb_spread" not in frame and "bbb_yield" in frame and "rate_10y" in frame:
        frame["bbb_spread"] = pd.to_numeric(frame.bbb_yield) - pd.to_numeric(frame.rate_10y)
    required_bases = {"house_prices", "cre_prices", "equity_index"}
    if set(price_bases) != required_bases or any(not np.isfinite(value) or value <= 0 for value in price_bases.values()):
        raise ValueError("all three pre-scenario index bases must be positive")
    for key in required_bases:
        frame[key] = pd.to_numeric(frame[key]) / price_bases[key] * 100
    if "quarter" not in frame:
        if "date" not in frame or frame.empty:
            raise ValueError("Fed CSV needs date labels")
        labels = frame.date.astype(str).str.strip().str.replace(":", "", regex=False).str.replace(" ", "", regex=False)
        labels = labels.map(lambda value: re.sub(r"^Q([1-4])(\d{4})$", r"\2Q\1", value))
        periods = pd.PeriodIndex(labels, freq="Q")
        if not np.array_equal(periods.asi8, periods.asi8[0] + np.arange(len(periods))):
            raise ValueError("Fed dates must be consecutive increasing quarters")
        frame["quarter"] = np.arange(1, len(frame) + 1)
    return Scenario(name, frame, synthetic=False)


def forecast_macro(scenario: Scenario, offset: int, step: int, forecast_quarters: int = 8,
                   reversion_quarters: int = 4) -> dict[str, float]:
    """Use available forecasts, then linearly revert levels to the long run."""
    if offset < 0 or offset > len(scenario.frame) or step < 1 or forecast_quarters < 0 or reversion_quarters < 0:
        raise ValueError("invalid forecast horizon")
    available = min(forecast_quarters, len(scenario.frame) - offset)
    if step <= available:
        return scenario.macro(offset + step - 1)
    if available == 0 or reversion_quarters == 0:
        return LONG_RUN.copy()
    endpoint = scenario.macro(offset + available - 1)
    weight = max(0.0, 1 - (step - available) / reversion_quarters)
    return {key: LONG_RUN[key] + weight * (endpoint[key] - LONG_RUN[key]) for key in MACRO_COLUMNS}
