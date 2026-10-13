"""US Method 1 scoring and illustrative GSIB TLAC and eligible debt checks."""

import math

import numpy as np
import pandas as pd

INDICATORS = {
    "total_exposures": ("size", .20),
    "intra_financial_assets": ("interconnectedness", .0667),
    "intra_financial_liabilities": ("interconnectedness", .0667),
    "securities_outstanding": ("interconnectedness", .0667),
    "payments": ("substitutability", .0667),
    "assets_under_custody": ("substitutability", .0667),
    "underwriting": ("substitutability", .0667),
    "otc_derivatives": ("complexity", .0667),
    "trading_and_afs": ("complexity", .0667),
    "level3_assets": ("complexity", .0667),
    "cross_jurisdiction_claims": ("cross_jurisdiction", .10),
    "cross_jurisdiction_liabilities": ("cross_jurisdiction", .10),
}


def method1_score(amounts: dict[str, float], denominators: dict[str, float]) -> tuple[float, pd.DataFrame]:
    """Score twelve indicators in five categories, including the substitutability cap."""
    if set(amounts) != set(INDICATORS) or set(denominators) != set(INDICATORS):
        raise ValueError("all twelve Method 1 indicators and denominators are required")
    rows = []
    for name, (category, weight) in INDICATORS.items():
        amount, denominator = amounts[name], denominators[name]
        if not math.isfinite(amount) or amount < 0 or not math.isfinite(denominator) or denominator <= 0:
            raise ValueError("indicator amounts must be nonnegative and denominators positive")
        rows.append({"indicator": name, "category": category, "amount_bn": amount,
                     "denominator_bn": denominator, "weight": weight,
                     "uncapped_score_bp": 10000 * weight * amount / denominator})
    table = pd.DataFrame(rows)
    table["score_bp"] = table.uncapped_score_bp
    mask = table.category == "substitutability"
    total = float(table.loc[mask, "uncapped_score_bp"].sum())
    if total > 100:
        table.loc[mask, "score_bp"] *= 100 / total
    return float(table.score_bp.sum()), table


def method1_surcharge(score_bp: float) -> float:
    """Map the unrounded score to Method 1 buckets in 12 CFR 217.403(b)."""
    if not math.isfinite(score_bp) or score_bp < 0:
        raise ValueError("score must be finite and nonnegative")
    for threshold, surcharge in ((130, 0.), (230, .01), (330, .015), (430, .02), (530, .025), (630, .035)):
        if score_bp < threshold:
            return surcharge
    return .045 + .01 * math.floor((score_bp - 630) / 100)


def synthetic_systemic_inputs(assets_bn: float = 250.0) -> tuple[dict[str, float], dict[str, float]]:
    """Return stylized/unverified global denominators, never actual GSIB assessment data."""
    if not math.isfinite(assets_bn) or assets_bn <= 0:
        raise ValueError("assets must be positive")
    amounts = dict(zip(INDICATORS, (assets_bn * 1.08, 12., 15., 28., 2200., 150., 35., 900., 40., 2., 18., 20.)))
    denominators = dict(zip(INDICATORS, (100000., 12000., 11000., 22000., 3000000., 160000., 8000., 700000., 13000., 1800., 27000., 24000.)))
    return amounts, denominators


def eligible_debt(debt: pd.DataFrame) -> dict[str, float]:
    """Apply maturity recognition to instruments already asserted to be eligible."""
    if not {"principal_bn", "days_to_maturity", "eligible"}.issubset(debt.columns):
        raise ValueError("debt schedule lacks required columns")
    principal = debt.principal_bn.to_numpy(dtype=float)
    days = debt.days_to_maturity.to_numpy(dtype=float)
    if not np.isfinite(principal).all() or not np.isfinite(days).all() or (principal < 0).any() or (days < 0).any():
        raise ValueError("invalid debt principal or maturity")
    if not debt.eligible.map(lambda value: isinstance(value, (bool, np.bool_))).all():
        raise ValueError("eligibility must be explicitly boolean")
    eligible_principal = principal * debt.eligible.to_numpy(dtype=bool)
    ltd = float(np.sum(eligible_principal * np.where(days >= 730, 1., np.where(days >= 365, .5, 0.))))
    tlac = float(np.sum(eligible_principal * (days >= 365)))
    return {"ltd_eligible_bn": ltd, "tlac_eligible_debt_bn": tlac}


def tlac_ltd_check(cet1: float, at1: float, debt: pd.DataFrame, rwa: float, leverage_exposure: float,
                   gsib_surcharge: float, method1_surcharge_ratio: float,
                   *, applicable: bool = False) -> pd.DataFrame:
    """Check US GSIB minima, with applicability explicit and buffers excluded."""
    values = (cet1, at1, rwa, leverage_exposure, gsib_surcharge, method1_surcharge_ratio)
    if not all(math.isfinite(x) and x >= 0 for x in values) or rwa <= 0 or leverage_exposure <= 0:
        raise ValueError("invalid TLAC or leverage inputs")
    recognized = eligible_debt(debt)
    leverage_buffer = .5 * method1_surcharge_ratio
    rows = [("tlac_risk", cet1 + at1 + recognized["tlac_eligible_debt_bn"], .18 * rwa),
            ("tlac_leverage", cet1 + at1 + recognized["tlac_eligible_debt_bn"], .075 * leverage_exposure),
            ("ltd_risk", recognized["ltd_eligible_bn"], (.06 + gsib_surcharge) * rwa),
            ("ltd_leverage", recognized["ltd_eligible_bn"], (.025 + leverage_buffer) * leverage_exposure)]
    frame = pd.DataFrame(rows, columns=["check", "eligible_amount_bn", "minimum_bn"])
    frame["headroom_bn"] = frame.eligible_amount_bn - frame.minimum_bn
    frame["meets_hypothetical_minimum"] = frame.headroom_bn >= 0
    frame["applicable"] = applicable
    frame["scope"] = "US GSIB minimum only; eligibility asserted; distribution buffers excluded"
    return frame
