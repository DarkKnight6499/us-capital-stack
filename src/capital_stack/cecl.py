"""Discounted PD, LGD, EAD losses and a simplified IFRS 9 comparison."""

from dataclasses import dataclass, replace
from functools import lru_cache
import math

import pandas as pd

from .models import Portfolio
from .numerics import annual_to_quarterly, bisect_root, logistic, logit
from .scenario import LONG_RUN, Scenario, forecast_macro
from .validation import validate_balance_paths


@dataclass(frozen=True)
class CreditSettings:
    """Stylized forecast, reversion, and significant-risk-increase settings."""

    forecast_quarters: int = 8
    reversion_quarters: int = 4
    relative_pd_threshold: float = 2.0

    def __post_init__(self) -> None:
        if any(isinstance(x, bool) or not isinstance(x, int) or x < 0
               for x in (self.forecast_quarters, self.reversion_quarters)):
            raise ValueError("forecast and reversion must be nonnegative integers")
        if not math.isfinite(self.relative_pd_threshold) or self.relative_pd_threshold <= 1:
            raise ValueError("relative PD threshold must exceed one")


@lru_cache(maxsize=128)
def calibrated_intercept(target_pd: float) -> float:
    """Calibrate the reference-state annual probability to its synthetic TTC target."""
    center = logit(target_pd)
    if target_pd <= .5:
        objective = lambda value: logistic(value) / target_pd - 1
    else:
        objective = lambda value: logistic(-value) / (1 - target_pd) - 1
    return bisect_root(objective, center - 4, center + 4)


def conditioned_pd(portfolio: Portfolio, macro: dict[str, float]) -> float:
    """Return annual conditional PD with documented macro sensitivities."""
    house_stress = math.log(LONG_RUN["house_prices"] / macro["house_prices"])
    score = (calibrated_intercept(portfolio.annual_pd)
             + portfolio.unemployment_beta * (macro["unemployment"] - LONG_RUN["unemployment"])
             + portfolio.house_beta * house_stress
             + portfolio.spread_beta * (macro["bbb_spread"] - LONG_RUN["bbb_spread"]))
    return logistic(score)


def conditioned_lgd(portfolio: Portfolio, macro: dict[str, float]) -> float:
    """Link secured-pool LGD to the collateral index, bounded by zero and one."""
    if portfolio.collateral is None:
        return portfolio.lgd
    price_ratio = macro[portfolio.collateral] / LONG_RUN[portfolio.collateral]
    return min(1.0, max(0.0, portfolio.lgd + portfolio.collateral_beta * (1 - price_ratio)))


def ead_schedule(balance: float, maturity_quarters: int, annual_prepayment: float,
                 effective_rate: float = 0.0) -> pd.DataFrame:
    """Return exposure before each payment for a surviving amortizing account."""
    if not math.isfinite(balance) or balance < 0 or isinstance(maturity_quarters, bool) or not isinstance(maturity_quarters, int) or maturity_quarters < 1:
        raise ValueError("invalid balance or maturity")
    if not math.isfinite(annual_prepayment) or not 0 <= annual_prepayment <= 1 or not math.isfinite(effective_rate) or effective_rate <= -1:
        raise ValueError("invalid prepayment or rate")
    log_quarter_rate = math.log1p(effective_rate) / 4
    rate = math.expm1(log_quarter_rate)
    payment = balance / maturity_quarters if rate == 0 else balance * rate / -math.expm1(-maturity_quarters * log_quarter_rate)
    prepayment = annual_to_quarterly(annual_prepayment)
    remaining, prepay_survival = balance, 1.0
    rows = []
    for quarter in range(1, maturity_quarters + 1):
        opening = remaining * prepay_survival
        principal = min(remaining, max(0.0, payment - remaining * rate))
        scheduled = principal * prepay_survival
        remaining = max(0.0, remaining - principal)
        if quarter == maturity_quarters:
            scheduled += remaining * prepay_survival
            remaining = 0.0
        prepaid = remaining * prepay_survival * prepayment
        prepay_survival *= 1 - prepayment
        rows.append((quarter, opening, scheduled, prepaid, remaining * prepay_survival))
    return pd.DataFrame(rows, columns=["step", "ead", "scheduled_principal", "prepayment", "closing_ead"])


def loss_term_structure(portfolio: Portfolio, scenario: Scenario, *, offset: int = 0,
                        horizon: int | None = None, settings: CreditSettings = CreditSettings()) -> pd.DataFrame:
    """Integrate marginal default probabilities over deterministic surviving EAD."""
    if offset < 0 or offset > len(scenario.frame):
        raise ValueError("invalid observation offset")
    if horizon is not None and (not isinstance(horizon, int) or horizon < 1):
        raise ValueError("loss horizon must be positive")
    steps = min(portfolio.maturity_quarters, horizon if horizon is not None else portfolio.maturity_quarters)
    schedule = ead_schedule(portfolio.balance, portfolio.maturity_quarters,
                            portfolio.annual_prepayment, portfolio.effective_rate)
    survival, rows = 1.0, []
    for index in range(steps):
        step = index + 1
        macro = forecast_macro(scenario, offset, step, settings.forecast_quarters, settings.reversion_quarters)
        annual_pd = conditioned_pd(portfolio, macro)
        hazard = annual_to_quarterly(annual_pd)
        lgd = conditioned_lgd(portfolio, macro)
        ead = float(schedule.iloc[index].ead)
        marginal = survival * hazard
        discount = (1 + portfolio.effective_rate) ** (-step / 4)
        loss = marginal * ead * lgd * discount
        rows.append((step, annual_pd, hazard, survival, marginal, ead, lgd, discount, loss))
        survival *= 1 - hazard
    return pd.DataFrame(rows, columns=["step", "annual_pd", "quarterly_pd", "survival",
                                      "marginal_pd", "ead", "lgd", "discount", "expected_loss"])


def ifrs_stage(current_pd: float, original_pd: float, defaulted: bool = False,
               relative_threshold: float = 2.0) -> int:
    """Assign a stylized stage using a relative annual-PD threshold."""
    if not all(math.isfinite(x) for x in (current_pd, original_pd, relative_threshold)):
        raise ValueError("nonfinite staging input")
    if not 0 <= current_pd <= 1 or not 0 < original_pd < 1 or relative_threshold <= 1:
        raise ValueError("invalid staging PD or threshold")
    if defaulted:
        return 3
    return 2 if current_pd / original_pd >= relative_threshold else 1


def allowances(portfolio: Portfolio, scenario: Scenario, *, offset: int = 0,
               observed_macro: dict[str, float] | None = None,
               settings: CreditSettings = CreditSettings()) -> dict[str, float | int]:
    """Return CECL, IFRS 9, and stage exposure reconciliation for the same book."""
    macro = observed_macro or (scenario.macro(offset) if offset < len(scenario.frame) else LONG_RUN.copy())
    stage = ifrs_stage(conditioned_pd(portfolio, macro), portfolio.origination_pd or portfolio.annual_pd,
                       relative_threshold=settings.relative_pd_threshold)
    performing = replace(portfolio, balance=portfolio.balance * (1 - portfolio.default_fraction), default_fraction=0.0)
    lifetime = float(loss_term_structure(performing, scenario, offset=offset, settings=settings).expected_loss.sum())
    twelve_month = float(loss_term_structure(performing, scenario, offset=offset, horizon=4, settings=settings).expected_loss.sum())
    default_ecl = (portfolio.balance * portfolio.default_fraction * conditioned_lgd(portfolio, macro)
                   * (1 + portfolio.effective_rate) ** (-0.25))
    ifrs_performing = lifetime if stage == 2 else twelve_month
    return {"cecl": lifetime + default_ecl, "ifrs9": ifrs_performing + default_ecl,
            "difference": lifetime - ifrs_performing, "performing_stage": stage,
            "stage1_balance": performing.balance if stage == 1 else 0.0,
            "stage2_balance": performing.balance if stage == 2 else 0.0,
            "stage3_balance": portfolio.balance * portfolio.default_fraction,
            "stage3_ecl": default_ecl, "twelve_month_ecl": twelve_month,
            "lifetime_performing_ecl": lifetime}


def provision(opening_allowance: float, closing_allowance: float, net_chargeoffs: float) -> float:
    """Reconcile provision to allowance movement plus net charge-offs."""
    if not all(math.isfinite(x) and x >= 0 for x in (opening_allowance, closing_allowance, net_chargeoffs)):
        raise ValueError("allowances and net charge-offs must be finite and nonnegative")
    return closing_allowance - opening_allowance + net_chargeoffs


def project_credit(portfolios: tuple[Portfolio, ...], scenario: Scenario, balance_paths: pd.DataFrame,
                   opening_allowances: dict[str, float], *, quarters: int = 9,
                   settings: CreditSettings = CreditSettings()) -> pd.DataFrame:
    """Project a replenished loan book with explicit allowance roll-forwards."""
    validate_balance_paths(portfolios, scenario, balance_paths, quarters)
    if set(opening_allowances) != {p.name for p in portfolios}:
        raise ValueError("opening allowance map must match portfolios")
    if not all(math.isfinite(value) and value >= 0 for value in opening_allowances.values()):
        raise ValueError("opening allowances must be finite and nonnegative")
    rows = []
    for pool in portfolios:
        opening_balance, opening_acl = pool.balance, opening_allowances[pool.name]
        for index in range(quarters):
            macro = scenario.macro(index)
            default_fraction = pool.default_fraction if index == 0 else 0.0
            hazard = annual_to_quarterly(conditioned_pd(pool, macro))
            default_principal = opening_balance * (default_fraction + (1 - default_fraction) * hazard)
            lgd = conditioned_lgd(pool, macro)
            chargeoffs = default_principal * lgd
            recoveries = default_principal - chargeoffs
            one_step = ead_schedule(opening_balance * (1 - default_fraction) * (1 - hazard),
                                    pool.maturity_quarters, pool.annual_prepayment, pool.effective_rate).iloc[0]
            target = float(balance_paths.iloc[index][pool.name])
            if not math.isfinite(target) or target < 0:
                raise ValueError("loan balances must be finite and nonnegative")
            originations = max(0.0, target - float(one_step.closing_ead))
            extra_runoff = max(0.0, float(one_step.closing_ead) - target)
            ending_pool = replace(pool, balance=target, default_fraction=0.0)
            ending = allowances(ending_pool, scenario, offset=index + 1, observed_macro=macro, settings=settings)
            closing_acl = float(ending["cecl"])
            quarterly_provision = provision(opening_acl, closing_acl, chargeoffs)
            rows.append({"quarter": index + 1, "portfolio": pool.name,
                         "opening_balance": opening_balance, "closing_balance": target,
                         "default_principal": default_principal, "recoveries": recoveries,
                         "scheduled_principal": float(one_step.scheduled_principal),
                         "prepayment": float(one_step.prepayment), "originations": originations,
                         "extra_runoff": extra_runoff, "opening_allowance": opening_acl,
                         "closing_allowance": closing_acl, "net_chargeoffs": chargeoffs,
                         "provision": quarterly_provision, **{f"ending_{key}": value for key, value in ending.items()}})
            opening_balance, opening_acl = target, closing_acl
    return pd.DataFrame(rows).sort_values(["quarter", "portfolio"]).reset_index(drop=True)
