"""Quarterly CET1 accounting, scenario RWA, and rule-structured SCB calculation."""

from dataclasses import dataclass
import math
from collections.abc import Sequence

import numpy as np
import pandas as pd

from .endgame import CURRENT_WEIGHTS, current_standardized_rwa
from .models import Bank
from .scenario import Scenario
from .validation import validate_balance_paths

SCB_SOURCE = "https://www.law.cornell.edu/cfr/text/12/225.8#f_2"
MINIMUM_CET1 = .045


@dataclass(frozen=True)
class CapitalSettings:
    """Stylized planning actions and taxes, not a distribution-approval engine."""

    common_dividends: tuple[float, ...] = (.24,) * 9
    buybacks: tuple[float, ...] = (.06,) * 9
    preferred_dividend: float = .03
    tax_rate: float = .25
    recognize_tax_benefit: bool = False
    shock_loss_bn: float = 0.0
    shock_quarter: int = 1

    def __post_init__(self) -> None:
        if len(self.common_dividends) != len(self.buybacks) or not self.common_dividends:
            raise ValueError("distribution paths must have matching positive lengths")
        amounts = (*self.common_dividends, *self.buybacks, self.preferred_dividend, self.shock_loss_bn)
        if not all(math.isfinite(x) and x >= 0 for x in amounts):
            raise ValueError("distributions and shock loss must be nonnegative")
        if not math.isfinite(self.tax_rate) or not 0 <= self.tax_rate <= 1:
            raise ValueError("tax rate must lie between zero and one")
        if not isinstance(self.shock_quarter, int) or not 1 <= self.shock_quarter <= len(self.common_dividends):
            raise ValueError("shock quarter outside distribution horizon")


def cet1_roll_forward(opening: float, net_income: float, distributions: float) -> float:
    """Apply the CET1 accounting identity with no hidden capital injections."""
    if not all(math.isfinite(x) for x in (opening, net_income, distributions)) or distributions < 0:
        raise ValueError("invalid capital roll-forward inputs")
    return opening + net_income - distributions


def project_rwa(bank: Bank, scenario: Scenario, balance_paths: pd.DataFrame, quarters: int = 9) -> pd.DataFrame:
    """Apply explicit stylized migration overlays to standardized portfolio weights."""
    validate_balance_paths(bank.portfolios, scenario, balance_paths, quarters)
    opening_credit = sum(p.balance * CURRENT_WEIGHTS[p.name] for p in bank.portfolios)
    fixed_rwa = current_standardized_rwa(bank) - opening_credit
    rows = []
    for index in range(quarters):
        macro = scenario.macro(index)
        migration = .012 * max(0, macro["unemployment"] - 4.2) + .006 * max(0, macro["bbb_spread"] - 1.5)
        loans = sum(float(balance_paths.iloc[index][p.name]) * CURRENT_WEIGHTS[p.name]
                    * (1 + migration * (.5 if p.name == "mortgage" else 1)) for p in bank.portfolios)
        rwa = fixed_rwa + loans
        if not math.isfinite(rwa) or rwa <= 0:
            raise ValueError("RWA must be finite and positive")
        rows.append({"quarter": index + 1, "rwa": rwa, "migration_overlay": migration})
    return pd.DataFrame(rows)


def project_capital(bank: Bank, ppnr: pd.DataFrame, credit: pd.DataFrame, rwa: pd.DataFrame,
                    settings: CapitalSettings = CapitalSettings(), *, supervisory_actions: bool = False) -> pd.DataFrame:
    """Project CET1 using planned actions or a no-common-distribution SCB reference."""
    quarters = len(ppnr)
    if quarters < 1 or len(rwa) != quarters or len(settings.common_dividends) < quarters:
        raise ValueError("capital input horizons must match")
    expected = np.arange(1, quarters + 1)
    if not np.array_equal(ppnr.quarter, expected) or not np.array_equal(rwa.quarter, expected):
        raise ValueError("capital inputs must use consecutive aligned quarters")
    if credit.duplicated(["quarter", "portfolio"]).any():
        raise ValueError("duplicate credit projection rows")
    names = {p.name for p in bank.portfolios}
    if set(credit.quarter) != set(expected) or any(set(group.portfolio) != names for _, group in credit.groupby("quarter")):
        raise ValueError("credit inputs must cover every portfolio in every quarter")
    if not np.isfinite(credit.provision.to_numpy(dtype=float)).all():
        raise ValueError("individual portfolio provisions must be finite")
    provisions = credit.groupby("quarter").provision.sum()
    if not np.isfinite(ppnr.ppnr).all() or not np.isfinite(provisions).all() or not np.isfinite(rwa.rwa).all() or (rwa.rwa <= 0).any():
        raise ValueError("capital input values must be finite and RWA positive")
    opening, rows = bank.cet1, []
    for index in range(quarters):
        quarter = index + 1
        revenue = float(ppnr.iloc[index].ppnr)
        provision_bn = float(provisions.loc[quarter])
        shock = settings.shock_loss_bn if quarter == settings.shock_quarter else 0.0
        pretax = revenue - provision_bn - shock
        tax = settings.tax_rate * (pretax if settings.recognize_tax_benefit else max(pretax, 0.0))
        income = pretax - tax
        common_dividends = 0.0 if supervisory_actions else settings.common_dividends[index]
        buybacks = 0.0 if supervisory_actions else settings.buybacks[index]
        distributions = common_dividends + buybacks + settings.preferred_dividend
        closing = cet1_roll_forward(opening, income, distributions)
        risk_assets = float(rwa.iloc[index].rwa)
        rows.append({"quarter": quarter, "opening_cet1": opening, "ppnr": revenue,
                     "provision": provision_bn, "other_losses": shock, "pretax_income": pretax,
                     "taxes": tax, "net_income": income, "common_dividends": common_dividends,
                     "buybacks": buybacks, "preferred_dividends": settings.preferred_dividend,
                     "distributions": distributions, "closing_cet1": closing, "rwa": risk_assets,
                     "cet1_ratio": closing / risk_assets, "tier1_ratio": (closing + bank.at1) / risk_assets,
                     "total_capital_ratio": (closing + bank.at1 + bank.tier2) / risk_assets})
        opening = closing
    return pd.DataFrame(rows)


def peak_to_trough(ratios: Sequence[float]) -> float:
    """Return the maximum chronological drawdown of a ratio path."""
    values = np.asarray(ratios, dtype=float)
    if values.ndim != 1 or values.size == 0 or not np.isfinite(values).all():
        raise ValueError("ratio path must be nonempty and finite")
    return float(np.max(np.maximum.accumulate(values) - values))


def stress_capital_buffer(starting_ratio: float, projected_ratios: Sequence[float],
                          projected_rwa: Sequence[float], planned_common_dividends: Sequence[float]) -> dict[str, float | int]:
    """Apply 12 CFR 225.8(f)(2): starting ratio, minimum ratio, Q4-Q7 dividends."""
    ratios = np.asarray(projected_ratios, dtype=float)
    rwa = np.asarray(projected_rwa, dtype=float)
    dividends = np.asarray(planned_common_dividends, dtype=float)
    if ratios.ndim != 1 or len(ratios) < 7 or ratios.shape != rwa.shape or ratios.shape != dividends.shape:
        raise ValueError("SCB inputs must have matching paths covering at least seven quarters")
    if not math.isfinite(starting_ratio) or starting_ratio < 0 or not np.isfinite(ratios).all() or not np.isfinite(rwa).all() or not np.isfinite(dividends).all():
        raise ValueError("SCB inputs must be finite")
    if (rwa <= 0).any() or (dividends < 0).any():
        raise ValueError("SCB requires positive RWA and nonnegative dividends")
    index = int(np.argmin(ratios))
    decline = starting_ratio - float(ratios[index])
    dividend_addon = float(dividends[3:7].sum() / rwa[index])
    return {"starting_ratio": starting_ratio, "minimum_ratio": float(ratios[index]),
            "minimum_quarter": index + 1, "rwa_at_minimum": float(rwa[index]),
            "starting_to_minimum_decline": decline, "dividend_addon": dividend_addon,
            "scb": max(.025, decline + dividend_addon)}


def requirement_table(projections: dict[str, pd.DataFrame], scb: float, gsib_surcharge: float = 0.0,
                       countercyclical_buffer: float = 0.0) -> pd.DataFrame:
    """Compare projected CET1 with an assumed next-cycle CET1 planning hurdle."""
    if not all(math.isfinite(x) and x >= 0 for x in (scb, gsib_surcharge, countercyclical_buffer)):
        raise ValueError("buffer inputs must be finite and nonnegative")
    requirement = MINIMUM_CET1 + scb + gsib_surcharge + countercyclical_buffer
    rows = []
    for name, frame in projections.items():
        for row in frame.itertuples():
            rows.append({"scenario": name, "quarter": row.quarter,
                         "cet1_ratio": row.cet1_ratio, "minimum_cet1_ratio": MINIMUM_CET1,
                         "scb": scb, "gsib_surcharge": gsib_surcharge, "countercyclical_buffer": countercyclical_buffer,
                         "planning_hurdle": requirement, "headroom_ratio": row.cet1_ratio - requirement,
                         "capital_headroom_bn": row.closing_cet1 - requirement * row.rwa,
                         "meets_planning_hurdle": row.cet1_ratio >= requirement})
    return pd.DataFrame(rows)
