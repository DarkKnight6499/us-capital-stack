"""Historical 2023 proposal comparison with explicit proxy risk weights."""

from dataclasses import dataclass
import math

import numpy as np
import pandas as pd

from .models import Bank

PROPOSAL_SOURCE = "https://www.federalregister.gov/documents/2023/09/18/2023-19200/regulatory-capital-rule-large-banking-organizations-and-banking-organizations-with-significant"
BASEL_FLOOR_SOURCE = "https://www.bis.org/committees/bcbs/basel-framework/standard/rbc?allChapters=true"
CURRENT_WEIGHTS = {"ci": 1.0, "cre": 1.0, "mortgage": .5, "cards": 1.0, "other_consumer": 1.0}


def _nonnegative(*values: float) -> None:
    if any(not math.isfinite(value) or value < 0 for value in values):
        raise ValueError("amounts must be finite and nonnegative")


@dataclass(frozen=True)
class EndgameSettings:
    """Historical proposal parameters with synthetic portfolio classification."""

    investment_grade_public_share: float = .30
    card_transactor_share: float = .20
    mortgage_proxy_weight: float = .60
    cre_proxy_weight: float = 1.10
    expanded_market_rwa: float = 6.0
    standardized_market_rwa: float = 7.0
    cva_rwa: float = 2.0
    internal_loss_multiplier: float = 1.0
    output_floor_factor: float = .725

    def __post_init__(self) -> None:
        _nonnegative(*vars(self).values())
        if any(x > 1 for x in (self.investment_grade_public_share, self.card_transactor_share, self.output_floor_factor)):
            raise ValueError("shares and floor factor must not exceed one")
        if self.internal_loss_multiplier < 1:
            raise ValueError("2023 proposal ILM floor is one")


def business_indicator(history: pd.DataFrame) -> float:
    """Compute BI from three annual observations using the proposal component structure."""
    columns = ["interest_income", "interest_expense", "earning_assets", "dividend_income",
               "fee_income", "fee_expense", "other_income", "other_expense",
               "trading_revenue", "banking_financial_revenue"]
    if len(history) != 3 or not set(columns).issubset(history.columns):
        raise ValueError("three complete annual financial observations are required")
    values = history[columns].to_numpy(dtype=float)
    if not np.isfinite(values).all() or (history[columns[:8]] < 0).any().any():
        raise ValueError("invalid BI inputs")
    interest = min(float((history.interest_income - history.interest_expense).abs().mean()),
                   .0225 * float(history.earning_assets.mean())) + float(history.dividend_income.mean())
    services = max(float(history.fee_income.mean()), float(history.fee_expense.mean())) + max(float(history.other_income.mean()), float(history.other_expense.mean()))
    financial = float(history.trading_revenue.abs().mean() + history.banking_financial_revenue.abs().mean())
    return interest + services + financial


def business_indicator_component(indicator_bn: float) -> float:
    """Apply verified 2023 proposal marginal BIC rates in USD billions."""
    _nonnegative(indicator_bn)
    return .12 * min(indicator_bn, 1) + .15 * min(max(indicator_bn - 1, 0), 29) + .18 * max(indicator_bn - 30, 0)


def operational_rwa(indicator_bn: float, internal_loss_multiplier: float = 1.0) -> float:
    """Convert BIC times assumed ILM to RWA, using the proposal floor on ILM."""
    _nonnegative(internal_loss_multiplier)
    if internal_loss_multiplier < 1:
        raise ValueError("ILM must be at least one")
    return 12.5 * business_indicator_component(indicator_bn) * internal_loss_multiplier


def output_floor(expanded_rwa: float, standardized_rwa: float, factor: float = .725) -> float:
    """Apply illustrative aggregate floor mechanics to caller-supplied totals."""
    _nonnegative(expanded_rwa, standardized_rwa, factor)
    if factor > 1:
        raise ValueError("floor factor must not exceed one")
    return max(expanded_rwa, factor * standardized_rwa)


def credit_rwa_table(bank: Bank, settings: EndgameSettings = EndgameSettings()) -> pd.DataFrame:
    """Compare pool-level weights with all assumptions attached to each row."""
    expanded = {"ci": .65 * settings.investment_grade_public_share + 1 - settings.investment_grade_public_share,
                "cre": settings.cre_proxy_weight, "mortgage": settings.mortgage_proxy_weight,
                "cards": .55 * settings.card_transactor_share + .85 * (1 - settings.card_transactor_share),
                "other_consumer": .85}
    notes = {"ci": "Verified conditional 2023 weights; synthetic public investment-grade share",
             "cre": "stylized/unverified aggregate CRE proxy, not an LTV rule table",
             "mortgage": "stylized/unverified aggregate mortgage proxy, not an LTV rule table",
             "cards": "Verified conditional 2023 weights; synthetic regulatory-retail and transactor classification",
             "other_consumer": "Verified conditional 2023 weight; assumed qualifying regulatory retail"}
    rows = []
    for pool in bank.portfolios:
        if pool.name not in CURRENT_WEIGHTS:
            raise ValueError(f"no risk weight for portfolio {pool.name}")
        rows.append((pool.name, pool.balance, CURRENT_WEIGHTS[pool.name], expanded[pool.name], notes[pool.name]))
    rows += [("securities", bank.securities, .20, .20, "Assumed GSE exposure, no securitization or trading overlap"),
             ("cash", bank.cash, 0.0, 0.0, "Assumed central-bank balances"),
             ("other_assets", bank.other_assets, 1.0, 1.0, "stylized/unverified generic asset classification")]
    frame = pd.DataFrame(rows, columns=["exposure", "balance_bn", "current_weight", "expanded_weight", "status"])
    frame["current_credit_rwa"] = frame.balance_bn * frame.current_weight
    frame["expanded_credit_rwa"] = frame.balance_bn * frame.expanded_weight
    frame["rwa_change"] = frame.expanded_credit_rwa - frame.current_credit_rwa
    return frame


def current_standardized_rwa(bank: Bank) -> float:
    """Return simplified opening standardized RWA, including a market placeholder."""
    return float(credit_rwa_table(bank).current_credit_rwa.sum()) + bank.current_market_rwa


def compare_endgame(bank: Bank, history: pd.DataFrame, required_cet1_ratio: float,
                    settings: EndgameSettings = EndgameSettings()) -> pd.DataFrame:
    """Compare current, illustrative floor, and historical US dual-stack totals."""
    _nonnegative(required_cet1_ratio)
    if required_cet1_ratio > 1:
        raise ValueError("required CET1 ratio must not exceed one")
    table = credit_rwa_table(bank, settings)
    credit_current = float(table.current_credit_rwa.sum())
    credit_expanded = float(table.expanded_credit_rwa.sum())
    op_rwa = operational_rwa(business_indicator(history), settings.internal_loss_multiplier)
    expanded_raw = credit_expanded + op_rwa + settings.expanded_market_rwa + settings.cva_rwa
    expanded_standardized_market = credit_expanded + op_rwa + settings.standardized_market_rwa + settings.cva_rwa
    proposed_standardized = credit_current + settings.standardized_market_rwa
    us_expanded = output_floor(expanded_raw, expanded_standardized_market, settings.output_floor_factor)
    current = credit_current + bank.current_market_rwa
    illustrative = output_floor(expanded_raw, current, settings.output_floor_factor)
    frameworks = [
        ("current_standardized_proxy", current, credit_current, 0., bank.current_market_rwa, 0., "Simplified current classification and market placeholder"),
        ("requested_illustrative_output_floor", illustrative, credit_expanded, op_rwa, settings.expanded_market_rwa, settings.cva_rwa,
         "stylized/unverified US application: floor base is current RWA, not revised Basel standardized RWA"),
        ("historical_2023_us_dual_stack_proxy", max(us_expanded, proposed_standardized), credit_expanded, op_rwa, settings.expanded_market_rwa, settings.cva_rwa,
         "Verified dual-stack structure; proxy credit and market inputs; ILM assumed one"),
    ]
    rows = []
    for label, rwa, credit, operational, market, cva, status in frameworks:
        raw_components = credit + operational + market + cva
        floor_adjustment = 0.0 if label == "current_standardized_proxy" else (us_expanded if label == "historical_2023_us_dual_stack_proxy" else illustrative) - raw_components
        dual_adjustment = rwa - us_expanded if label == "historical_2023_us_dual_stack_proxy" else 0.0
        rows.append({"framework": label, "credit_rwa": credit, "operational_rwa": operational,
                     "market_rwa": market, "cva_rwa": cva, "total_rwa": rwa,
                     "floor_adjustment_rwa": floor_adjustment,
                     "dual_stack_adjustment_rwa": dual_adjustment,
                     "cet1_ratio": bank.cet1 / rwa, "rwa_change": rwa - current,
                     "required_cet1_ratio": required_cet1_ratio,
                     "required_cet1_bn": required_cet1_ratio * rwa,
                     "incremental_required_cet1_bn": required_cet1_ratio * (rwa - current),
                     "cet1_to_preserve_opening_ratio_bn": bank.cet1 / current * (rwa - current),
                     "capital_headroom_bn": bank.cet1 - required_cet1_ratio * rwa,
                     "expanded_raw_rwa": expanded_raw, "us_market_floor_base": expanded_standardized_market,
                     "proposed_standardized_rwa": proposed_standardized, "status": status})
    return pd.DataFrame(rows)
