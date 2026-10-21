"""SLR and exposure reconciliation under 12 CFR 217.10(c) and 217.11(c)(4)."""

from dataclasses import dataclass, replace
import math

import numpy as np
import pandas as pd

from . import leverage_config as config
from .leverage_config import LeverageSettings
from .models import Bank


@dataclass(frozen=True)
class LeverageInputs:
    """Calendar-daily balances and three aligned month-end transaction snapshots."""

    daily_assets: pd.DataFrame
    derivatives: pd.DataFrame
    credit_protection: pd.DataFrame
    repos: pd.DataFrame
    commitments: pd.DataFrame


def _numeric(frame: pd.DataFrame, columns: tuple[str, ...], *, signed: tuple[str, ...] = ()) -> None:
    if not set(columns).issubset(frame.columns):
        raise ValueError(f"missing leverage columns: {sorted(set(columns) - set(frame.columns))}")
    for column in columns:
        values = frame[column].to_numpy(dtype=float)
        if not np.isfinite(values).all() or (column not in signed and (values < 0).any()):
            raise ValueError(f"invalid leverage values in {column}")


def _boolean(frame: pd.DataFrame, columns: tuple[str, ...]) -> None:
    for column in columns:
        if column not in frame or not frame[column].map(lambda value: isinstance(value, (bool, np.bool_))).all():
            raise ValueError(f"{column} must be explicitly boolean")


def _detail(frame: pd.DataFrame, amounts: object, component: str, rule: str) -> pd.DataFrame:
    result = frame.copy()
    result[config.COMPONENT] = component
    result[config.RULE] = rule
    result[config.AMOUNT] = amounts
    return result


def on_balance_sheet_assets(daily: pd.DataFrame) -> pd.DataFrame:
    """Return signed daily means under 12 CFR 217.10(c)(1), (c)(2)(i), SA-CCR only."""
    _numeric(daily, tuple(config.DAILY_COMPONENTS))
    if daily.empty:
        raise ValueError("daily asset path must not be empty")
    return pd.DataFrame([{config.COMPONENT: column, config.RULE: "217.10(c)(2)(i)",
                          config.AMOUNT: sign * float(daily[column].mean())}
                         for column, sign in config.DAILY_COMPONENTS.items()])


def _derivative_factor(frame: pd.DataFrame, settings: LeverageSettings) -> np.ndarray:
    _boolean(frame, (config.END_USER,))
    return np.where(~frame[config.END_USER] & settings.apply_counterparty_factor,
                    config.COUNTERPARTY_FACTOR, 1.)


def derivative_pfe(frame: pd.DataFrame, settings: LeverageSettings = LeverageSettings()) -> pd.DataFrame:
    """Apply 217.10(c)(2)(ii)(B), 217.132(c)(7)(i), with C=0 and input add-on A."""
    _numeric(frame, (config.V, config.ADDON), signed=(config.V,))
    addon = frame[config.ADDON].to_numpy(dtype=float)
    value = frame[config.V].to_numpy(dtype=float)
    exponent = np.zeros_like(addon)
    np.divide(np.minimum(value, 0.), config.PFE_EXPONENT_SCALE * addon,
              out=exponent, where=addon > 0)
    multiplier = config.PFE_FLOOR + (1 - config.PFE_FLOOR) * np.exp(exponent)
    factor = _derivative_factor(frame, settings)
    result = _detail(frame, multiplier * addon * factor, "derivative_pfe", "217.10(c)(2)(ii)(B)")
    result[config.MULTIPLIER] = multiplier
    result[config.FACTOR] = factor
    return result


def derivative_replacement_cost(frame: pd.DataFrame,
                                settings: LeverageSettings = LeverageSettings()) -> pd.DataFrame:
    """Apply 217.10(c)(2)(iii)(B); eligibility asserts conditions (C) through (G)."""
    _numeric(frame, (config.V, config.CVM_RECEIVED, config.CVM_POSTED), signed=(config.V,))
    _boolean(frame, (config.CVM_ELIGIBLE,))
    eligible = frame[config.CVM_ELIGIBLE]
    cost = np.maximum(frame[config.V] - frame[config.CVM_RECEIVED] * eligible
                      + frame[config.CVM_POSTED] * eligible, 0.)
    factor = _derivative_factor(frame, settings)
    result = _detail(frame, cost * factor, "derivative_replacement_cost", "217.10(c)(2)(iii)(B)")
    result[config.FACTOR] = factor
    return result


def sold_credit_protection(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply 217.10(c)(2)(iv); matched flag asserts reference and maturity eligibility."""
    _numeric(frame, config.PROTECTION_AMOUNT_COLUMNS)
    _boolean(frame, (config.MATCHED_HEDGE,))
    amounts = np.maximum(frame[config.SOLD] - frame[config.PURCHASED] * frame[config.MATCHED_HEDGE]
                         - frame[config.CET1_LOSS], 0.)
    return _detail(frame, amounts, "sold_credit_protection", "217.10(c)(2)(iv)")


def gross_repo_receivables(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply 217.10(c)(2)(v); subtract receivables already included on balance sheet."""
    _numeric(frame, (config.GROSS_RECEIVABLE, config.ON_BALANCE_RECEIVABLE))
    _boolean(frame, (config.NETTING_MET,))
    if (frame[config.ON_BALANCE_RECEIVABLE] > frame[config.GROSS_RECEIVABLE]).any():
        raise ValueError("on-balance repo receivable exceeds gross receivable")
    amounts = (frame[config.GROSS_RECEIVABLE] - frame[config.ON_BALANCE_RECEIVABLE]) * ~frame[config.NETTING_MET]
    return _detail(frame, amounts, "gross_repo_receivables", "217.10(c)(2)(v)")


def repo_counterparty_exposure(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply 217.10(c)(2)(vi): floor by transaction or qualifying agreement."""
    _numeric(frame, (config.E, config.C))
    _boolean(frame, (config.QMNA,))
    keys = [config.COUNTERPARTY, config.REPO_NETTING_SET]
    if not set(keys).issubset(frame.columns) or frame[keys].isna().any().any():
        raise ValueError("repo counterparty and agreement identifiers are required")
    if (frame.groupby(keys)[config.QMNA].nunique() > 1).any():
        raise ValueError("QMNA flags must agree within each agreement")
    result = frame.copy()
    result[config.AMOUNT] = np.maximum(result[config.E] - result[config.C], 0.)
    matched = result.loc[result[config.QMNA]]
    if not matched.empty:
        grouped = matched.groupby(keys, as_index=False)[[config.E, config.C]].sum()
        grouped[config.AMOUNT] = np.maximum(grouped[config.E] - grouped[config.C], 0.)
        result = pd.concat([result.loc[~result[config.QMNA]], grouped], ignore_index=True)
    return _detail(result, result[config.AMOUNT], "repo_counterparty_exposure", "217.10(c)(2)(vi)")


def off_balance_sheet_exposure(frame: pd.DataFrame) -> pd.DataFrame:
    """Apply 217.10(c)(2)(viii), 217.33(b), including the 10 percent CCF floor."""
    _numeric(frame, (config.MATURITY, config.NOTIONAL))
    if config.COMMITMENT_TYPE not in frame:
        raise ValueError("commitment type is required")
    kinds = frame[config.COMMITMENT_TYPE]
    if not kinds.isin([*config.CCF_TABLE, config.COMMITMENT]).all():
        raise ValueError("unsupported off-balance sheet commitment type")
    if ((kinds == config.TRADE) & (frame[config.MATURITY] > config.ONE_YEAR)).any():
        raise ValueError("self-liquidating trade treatment requires maturity of one year or less")
    base = kinds.map(config.CCF_TABLE).astype(float)
    commitment = kinds == config.COMMITMENT
    base.loc[commitment] = np.where(frame.loc[commitment, config.MATURITY] <= config.ONE_YEAR,
                                   config.SHORT_COMMITMENT_CCF, config.LONG_COMMITMENT_CCF)
    ccf = base.clip(lower=config.CCF_FLOOR)
    result = _detail(frame, frame[config.NOTIONAL] * ccf, "off_balance_commitments", "217.10(c)(2)(viii)")
    result[config.BASE_CCF], result[config.CCF] = base, ccf
    return result


def custodial_exclusion(daily: pd.DataFrame, settings: LeverageSettings = LeverageSettings()) -> pd.DataFrame:
    """Apply 217.10(c)(2)(x); eligibility is asserted by the configuration switch."""
    _numeric(daily, (config.CENTRAL_BANK, config.CUSTODIAL_DEPOSITS))
    if daily.empty:
        raise ValueError("daily custodial path must not be empty")
    exclusion = np.minimum(daily[config.CENTRAL_BANK], daily[config.CUSTODIAL_DEPOSITS]).mean()
    return pd.DataFrame([{config.COMPONENT: "custodial_exclusion", config.RULE: "217.10(c)(2)(x)",
                          config.AMOUNT: -float(exclusion) if settings.custodial_banking_organization else 0.}])


def monthly_exposure_components(inputs: LeverageInputs,
                                settings: LeverageSettings = LeverageSettings()) -> pd.DataFrame:
    """Reconcile each of three month ends before averaging, 217.10(c)(1)(ii)."""
    dates = pd.to_datetime(inputs.daily_assets[config.DATE], errors="raise")
    if dates.empty or dates.isna().any() or dates.duplicated().any():
        raise ValueError("daily dates must be nonempty and unique")
    period = dates.min().to_period("Q")
    expected_days = pd.date_range(period.start_time, period.end_time.normalize(), freq="D")
    if not pd.DatetimeIndex(dates).equals(expected_days):
        raise ValueError("daily assets must cover every calendar day of one complete quarter in order")
    months = pd.date_range(period.start_time, period.end_time, freq=pd.offsets.MonthEnd())
    rows = []
    functions = ((inputs.derivatives, derivative_pfe), (inputs.derivatives, derivative_replacement_cost),
                 (inputs.credit_protection, sold_credit_protection), (inputs.repos, gross_repo_receivables),
                 (inputs.repos, repo_counterparty_exposure), (inputs.commitments, off_balance_sheet_exposure))
    for frame, function in functions:
        if config.MONTH not in frame:
            raise ValueError("each exposure table requires three month-end snapshots")
        observed = pd.to_datetime(frame[config.MONTH], errors="raise")
        if observed.isna().any() or set(observed) != set(months):
            raise ValueError("month-end snapshots must align with the daily reporting quarter")
        if function in (derivative_pfe, derivative_replacement_cost):
            if config.NETTING_SET not in frame or frame.duplicated([config.MONTH, config.NETTING_SET]).any():
                raise ValueError("derivative netting sets must be unique at each month end")
        for month in months:
            snapshot = frame.loc[observed == month]
            detail = function(snapshot, settings) if function in (derivative_pfe, derivative_replacement_cost) else function(snapshot)
            rows.append({config.MONTH: month, config.COMPONENT: detail[config.COMPONENT].iat[0],
                         config.RULE: detail[config.RULE].iat[0], config.AMOUNT: float(detail[config.AMOUNT].sum())})
    return pd.DataFrame(rows)


def total_leverage_exposure(inputs: LeverageInputs,
                            settings: LeverageSettings = LeverageSettings()) -> pd.DataFrame:
    """Return additive reconciliation, 217.10(c)(1)-(2); sum amount for total exposure."""
    daily = on_balance_sheet_assets(inputs.daily_assets)
    monthly = monthly_exposure_components(inputs, settings)
    averaged = monthly.groupby([config.COMPONENT, config.RULE], as_index=False, sort=False)[config.AMOUNT].mean()
    result = pd.concat([daily, averaged, custodial_exclusion(inputs.daily_assets, settings)], ignore_index=True)
    if not np.isfinite(result[config.AMOUNT]).all() or result[config.AMOUNT].sum() <= 0:
        raise ValueError("total leverage exposure must be finite and positive")
    return result


def leverage_ratios(tier1: float, average_total_assets: float, tier1_deductions: float,
                    exposure: float) -> pd.DataFrame:
    """Calculate 217.10(b)(4), (c)(1) ratios; tier 1 is already net of deductions."""
    if not all(math.isfinite(value) for value in (tier1, average_total_assets, tier1_deductions, exposure)):
        raise ValueError("leverage ratio inputs must be finite")
    denominator = average_total_assets - tier1_deductions
    if tier1_deductions < 0 or denominator <= 0 or exposure <= 0:
        raise ValueError("leverage denominators must be positive and deductions nonnegative")
    return pd.DataFrame([{config.TIER1: tier1, config.LEVERAGE_DENOMINATOR: denominator,
                          config.TLE: exposure, config.LEVERAGE_RATIO: tier1 / denominator,
                          config.SLR: tier1 / exposure}])


def leverage_buffer_requirement(method1_surcharge: float, *, subsidiary: bool = False) -> float:
    """Apply 217.11(a)(2)(v)(A)-(B) to an explicitly applicable GSIB view."""
    if not math.isfinite(method1_surcharge) or method1_surcharge < 0:
        raise ValueError("Method 1 surcharge must be finite and nonnegative")
    requirement = config.METHOD1_BUFFER_SHARE * method1_surcharge
    return min(config.SUBSIDIARY_BUFFER_CAP, requirement) if subsidiary else requirement


def max_payout_ratio(buffer: float, requirement: float) -> pd.DataFrame:
    """Apply Table 2 to 217.11(c)(4)(iii); NaN means no leverage payout limit."""
    if not all(math.isfinite(value) and value >= 0 for value in (buffer, requirement)):
        raise ValueError("buffer and requirement must be finite and nonnegative")
    fraction = buffer / requirement if requirement else math.nan
    payout = 0.
    no_limit = requirement == 0
    if requirement:
        for boundary, rate in config.PAYOUT_BANDS:
            if fraction > boundary and not math.isclose(fraction, boundary, rel_tol=0., abs_tol=config.BOUNDARY_TOLERANCE):
                payout = math.nan if rate is None else rate
                no_limit = rate is None
                break
    else:
        payout = math.nan
    return pd.DataFrame([{config.BUFFER_FRACTION: fraction, config.PAYOUT: payout, config.NO_LIMIT: no_limit}])


def leverage_buffer(slr: float, requirement: float) -> pd.DataFrame:
    """Apply 217.11(c)(4) and Table 2 to the leverage buffer alone."""
    if not math.isfinite(slr):
        raise ValueError("SLR must be finite")
    buffer = max(slr - config.MINIMUM_SLR, 0.)
    result = max_payout_ratio(buffer, requirement)
    result[config.BUFFER] = buffer
    result[config.BUFFER_REQUIREMENT] = requirement
    result[config.MINIMUM_HEADROOM] = slr - config.MINIMUM_SLR
    result[config.BUFFER_HEADROOM] = slr - config.MINIMUM_SLR - requirement
    return result


def scale_leverage_inputs(inputs: LeverageInputs, factor: float) -> LeverageInputs:
    """Scale the illustrative as-of exposure mix; regulatory deductions stay fixed."""
    if not math.isfinite(factor) or factor <= 0:
        raise ValueError("exposure scale must be finite and positive")
    frames = []
    specs = ((inputs.daily_assets, tuple(column for column in config.DAILY_AMOUNT_COLUMNS if column != config.DEDUCTIONS)),
             (inputs.derivatives, config.DERIVATIVE_AMOUNT_COLUMNS),
             (inputs.credit_protection, config.PROTECTION_AMOUNT_COLUMNS),
             (inputs.repos, config.REPO_AMOUNT_COLUMNS), (inputs.commitments, (config.NOTIONAL,)))
    for frame, columns in specs:
        scaled = frame.copy()
        scaled.loc[:, list(columns)] = scaled.loc[:, list(columns)] * factor
        frames.append(scaled)
    daily, derivatives, protection, repos, commitments = frames
    return LeverageInputs(daily_assets=daily, derivatives=derivatives, credit_protection=protection,
                          repos=repos, commitments=commitments)


def project_leverage(bank: Bank, capital: pd.DataFrame, balances: pd.DataFrame,
                     credit: pd.DataFrame, inputs: LeverageInputs) -> pd.DataFrame:
    """Project illustrative assets and exposures at a fixed mix, 217.10(b)(4), (c)(1)."""
    names = [pool.name for pool in bank.portfolios]
    loans = balances.set_index(config.QUARTER)[names].sum(axis=1)
    allowance = credit.groupby(config.QUARTER)[config.CLOSING_ALLOWANCE].sum()
    closing_assets = bank.assets + loans - sum(pool.balance for pool in bank.portfolios) - (allowance - bank.opening_allowance)
    opening_assets, rows = bank.assets, []
    reference_average = float(inputs.daily_assets[config.ASSETS].mean())
    for record in capital.to_dict("records"):
        quarter = record[config.QUARTER]
        closing = float(closing_assets.loc[quarter])
        average = (opening_assets + closing) / 2
        factor = average / reference_average
        scaled = scale_leverage_inputs(inputs, factor)
        exposure = float(total_leverage_exposure(scaled)[config.AMOUNT].sum())
        ratios = leverage_ratios(record[config.CLOSING_CET1] + bank.at1, average,
                                 float(scaled.daily_assets[config.DEDUCTIONS].mean()), exposure)
        rows.append({config.QUARTER: quarter, config.PROJECTED_ASSETS: closing,
                     config.AVERAGE_ASSETS: average, config.ASSET_SCALE: factor, **ratios.to_dict("records")[0]})
        opening_assets = closing
    return pd.DataFrame(rows)


def leverage_views(path: pd.DataFrame, method1_surcharge: float = config.ILLUSTRATIVE_METHOD1_SURCHARGE) -> pd.DataFrame:
    """Compare Category III, illustrative GSIB BHC, and illustrative subsidiary views."""
    requirements = {config.CATEGORY_III: 0., config.GSIB_BHC: leverage_buffer_requirement(method1_surcharge),
                    config.GSIB_SUBSIDIARY: leverage_buffer_requirement(method1_surcharge, subsidiary=True)}
    rows = []
    for view, requirement in requirements.items():
        for record in path.to_dict("records"):
            rows.append({**record, config.VIEW: view,
                         **leverage_buffer(record[config.SLR], requirement).to_dict("records")[0]})
    return pd.DataFrame(rows)


def summarize_leverage(path: pd.DataFrame) -> pd.DataFrame:
    """Report the minimum SLR and both headrooms in each scenario and view."""
    rows = []
    for (scenario, view), group in path.groupby([config.SCENARIO, config.VIEW], sort=False):
        minimum = group.loc[group[config.SLR].idxmin()]
        rows.append({config.SCENARIO: scenario, config.VIEW: view,
                     config.MINIMUM_RATIO: minimum[config.SLR], config.MINIMUM_QUARTER: minimum[config.QUARTER],
                     config.BUFFER_REQUIREMENT: minimum[config.BUFFER_REQUIREMENT],
                     config.MINIMUM_HEADROOM: minimum[config.MINIMUM_HEADROOM],
                     config.BUFFER_HEADROOM: minimum[config.BUFFER_HEADROOM]})
    return pd.DataFrame(rows)


def leverage_sensitivities(inputs: LeverageInputs, tier1: float) -> pd.DataFrame:
    """Isolate illustrative USD 10bn matched repo growth, alpha removal, and custody."""
    base = float(total_leverage_exposure(inputs)[config.AMOUNT].sum())
    daily = inputs.daily_assets.copy()
    daily[config.ASSETS] += config.ILLUSTRATIVE_REPO_GROWTH_BN
    growth_rows = [{config.MONTH: month, config.COUNTERPARTY: config.ILLUSTRATIVE_REPO_ID,
                    config.REPO_NETTING_SET: config.ILLUSTRATIVE_REPO_ID, config.QMNA: True,
                    config.E: config.ILLUSTRATIVE_REPO_GROWTH_BN, config.C: config.ILLUSTRATIVE_REPO_GROWTH_BN,
                    config.GROSS_RECEIVABLE: config.ILLUSTRATIVE_REPO_GROWTH_BN,
                    config.ON_BALANCE_RECEIVABLE: config.ILLUSTRATIVE_REPO_GROWTH_BN, config.NETTING_MET: True}
                   for month in inputs.repos[config.MONTH].unique()]
    growth = replace(inputs, daily_assets=daily, repos=pd.concat([inputs.repos, pd.DataFrame(growth_rows)], ignore_index=True))
    cases = (("repo_matched_book_plus_10bn_illustrative", growth, LeverageSettings()),
             ("remove_1_4_factor_illustrative", inputs, LeverageSettings(apply_counterparty_factor=False)),
             ("custodial_exclusion_illustrative", inputs, LeverageSettings(custodial_banking_organization=True)))
    rows = []
    for name, case, settings in cases:
        exposure = float(total_leverage_exposure(case, settings)[config.AMOUNT].sum())
        rows.append({config.SENSITIVITY: name, config.TLE: exposure, config.EXPOSURE_CHANGE: exposure - base,
                     config.SLR: tier1 / exposure, config.SLR_CHANGE_BP: (tier1 / exposure - tier1 / base) * 10000})
    return pd.DataFrame(rows)
