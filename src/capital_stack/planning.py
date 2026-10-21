"""End-to-end orchestration of the synthetic bank capital plan."""

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

from .cecl import CreditSettings, allowances, project_credit
from .data import DEFAULT_SEED, loan_balance_paths, reference_scenario, synthetic_bank, synthetic_scenarios, synthetic_leverage_inputs
from . import leverage_config as leverage_config
from .leverage import (leverage_sensitivities, leverage_views, monthly_exposure_components,
                       project_leverage, summarize_leverage, total_leverage_exposure)
from .endgame import business_indicator, business_indicator_component, compare_endgame, credit_rwa_table, current_standardized_rwa
from .models import Bank
from .ppnr import PPNRSettings, income_statement_run_rate, project_ppnr
from .projection import CapitalSettings, peak_to_trough, project_capital, project_rwa, requirement_table, stress_capital_buffer
from .scenario import LONG_RUN, Scenario
from .systemic import method1_score, method1_surcharge, synthetic_systemic_inputs, tlac_ltd_check


@dataclass
class CapitalPlan:
    """Inputs, projections, and reconciliations from a complete synthetic run."""

    bank: Bank
    scenarios: dict[str, Scenario]
    tables: dict[str, pd.DataFrame]
    scb: dict[str, float | int]


def synthetic_business_history(bank: Bank, seed: int = DEFAULT_SEED) -> pd.DataFrame:
    """Create three synthetic annual financial observations for the BI calculation."""
    rng = np.random.default_rng(seed)
    annual = income_statement_run_rate(bank).set_index("line").annual_bn
    rows = []
    for year in range(1, 4):
        scale = float(rng.uniform(.96, 1.04))
        rows.append({"year": year, "interest_income": annual.interest_income * scale,
                     "interest_expense": annual.interest_expense * scale,
                     "earning_assets": 240. * scale, "dividend_income": .05 * scale,
                     "fee_income": annual.noninterest_income * scale, "fee_expense": .45 * scale,
                     "other_income": .4 * scale, "other_expense": .6 * scale,
                     "trading_revenue": .25 * scale, "banking_financial_revenue": -.1 * scale})
    return pd.DataFrame(rows)


def run_plan(seed: int = DEFAULT_SEED, credit_settings: CreditSettings = CreditSettings(),
             *, scenario_paths: dict[str, Scenario] | None = None) -> CapitalPlan:
    """Run the seeded bank under supplied or synthetic scenarios with a separate SCB reference."""
    bank = synthetic_bank(seed)
    scenarios = synthetic_scenarios(seed) if scenario_paths is None else dict(scenario_paths)
    if set(scenarios) != {"baseline", "severely_adverse"} or any(len(path.frame) < 9 for path in scenarios.values()):
        raise ValueError("baseline and severely_adverse paths must each cover at least nine quarters")
    opening = {pool.name: float(allowances(pool, reference_scenario(), observed_macro=LONG_RUN)["cecl"])
               for pool in bank.portfolios}
    projections, tables, summary, comparison = {}, {}, [], []
    settings_by_scenario = {"baseline": CapitalSettings(), "severely_adverse": CapitalSettings(shock_loss_bn=.5)}
    supervisory_reference = None
    starting_ratio = bank.cet1 / current_standardized_rwa(bank)
    for name, scenario in scenarios.items():
        balances = loan_balance_paths(bank, scenario)
        credit = project_credit(bank.portfolios, scenario, balances, opening, settings=credit_settings)
        revenue = project_ppnr(bank, scenario, balances)
        risk_assets = project_rwa(bank, scenario, balances)
        capital = project_capital(bank, revenue, credit, risk_assets, settings_by_scenario[name])
        projections[name] = capital
        tables[f"balances_{name}"] = balances
        tables[f"credit_{name}"] = credit
        tables[f"ppnr_{name}"] = revenue
        tables[f"capital_{name}"] = capital
        tables[f"credit_totals_{name}"] = credit.groupby("quarter")[["opening_allowance", "closing_allowance", "net_chargeoffs", "provision"]].sum().reset_index()
        for pool in bank.portfolios:
            row = allowances(pool, scenario, observed_macro=scenario.macro(0), settings=credit_settings)
            comparison.append({"scenario": name, "quarter": 0, "portfolio": pool.name,
                               "measurement": "scenario_forecast_remeasurement", **row})
        for row in credit.to_dict("records"):
            comparison.append({"scenario": name, "quarter": row["quarter"], "portfolio": row["portfolio"],
                               "measurement": "projected_quarter_end",
                               **{key.removeprefix("ending_"): value for key, value in row.items() if key.startswith("ending_")}})
        minimum_index = int(capital.cet1_ratio.to_numpy().argmin())
        summary.append({"scenario": name, "assets_bn": bank.assets, "opening_allowance_bn": bank.opening_allowance,
                        "starting_cet1_ratio": starting_ratio, "total_ppnr_bn": float(capital.ppnr.sum()),
                        "total_provision_bn": float(capital.provision.sum()), "total_other_losses_bn": float(capital.other_losses.sum()),
                        "total_credit_losses_bn": float(credit.net_chargeoffs.sum()),
                        "credit_losses_to_opening_loans": float(credit.net_chargeoffs.sum()) / sum(p.balance for p in bank.portfolios),
                        "total_net_income_bn": float(capital.net_income.sum()), "total_distributions_bn": float(capital.distributions.sum()),
                        "ending_cet1_bn": float(capital.closing_cet1.iloc[-1]),
                        "minimum_cet1_ratio": float(capital.cet1_ratio.min()), "minimum_quarter": minimum_index + 1,
                        "ending_cet1_ratio": float(capital.cet1_ratio.iloc[-1]),
                        "peak_to_trough_decline": peak_to_trough([starting_ratio, *capital.cet1_ratio]),
                        "closing_allowance_bn": float(credit[credit.quarter == 9].closing_allowance.sum())})
        if name == "severely_adverse":
            supervisory_reference = project_capital(bank, revenue, credit, risk_assets, settings_by_scenario[name], supervisory_actions=True)
    if supervisory_reference is None:
        raise RuntimeError("adverse reference projection missing")
    scb = stress_capital_buffer(starting_ratio, supervisory_reference.cet1_ratio,
                               supervisory_reference.rwa, settings_by_scenario["baseline"].common_dividends)
    tables["scb_reference_capital"] = supervisory_reference
    scb["reference_peak_to_trough_decline"] = peak_to_trough([starting_ratio, *supervisory_reference.cet1_ratio])
    tables["scb_calculation"] = pd.DataFrame([scb])
    tables["capital_summary"] = pd.DataFrame(summary)
    tables["requirements"] = requirement_table(projections, float(scb["scb"]))
    tables["cecl_ifrs9_reconciliation"] = pd.DataFrame(comparison)
    totals = tables["cecl_ifrs9_reconciliation"].groupby(["scenario", "quarter"])[["cecl", "ifrs9", "difference", "stage1_balance", "stage2_balance", "stage3_balance"]].sum().reset_index()
    tables["cecl_ifrs9_totals"] = totals
    tables["balance_sheet"] = bank.balance_sheet()
    tables["portfolio_parameters"] = pd.DataFrame([asdict(pool) for pool in bank.portfolios])
    tables["income_run_rate"] = income_statement_run_rate(bank)
    tables["starting_capital"] = pd.DataFrame({"component": ["cet1", "at1", "tier2", "common_equity_regulatory_deduction"],
                                               "amount_bn": [bank.cet1, bank.at1, bank.tier2, bank.equity - bank.at1 - bank.cet1]})
    tables["model_settings"] = pd.DataFrame({
        "parameter": ["seed", "projection_quarters", "baseline_scenario_quarters", "adverse_scenario_quarters",
                      "forecast_quarters", "reversion_quarters", "relative_pd_threshold", "deposit_beta",
                      "tax_rate_assumed", "adverse_shock_bn", "scb_floor", "minimum_cet1_ratio",
                      "illustrative_output_floor_factor", "ilm_assumed", "historical_proposal_year"],
        "value": [seed, len(projections["baseline"]), len(scenarios["baseline"].frame), len(scenarios["severely_adverse"].frame),
                  credit_settings.forecast_quarters, credit_settings.reversion_quarters, credit_settings.relative_pd_threshold,
                  PPNRSettings().deposit_beta, settings_by_scenario["baseline"].tax_rate,
                  settings_by_scenario["severely_adverse"].shock_loss_bn, .025, .045, .725, 1., 2023]})
    history = synthetic_business_history(bank, seed)
    tables["business_history"] = history
    indicator = business_indicator(history)
    tables["operational_risk"] = pd.DataFrame([{"business_indicator_bn": indicator,
                                                "bic_bn": business_indicator_component(indicator),
                                                "ilm_assumed": 1.0, "operational_rwa_bn": 12.5 * business_indicator_component(indicator)}])
    tables["endgame_credit"] = credit_rwa_table(bank)
    tables["endgame_impact"] = compare_endgame(bank, history, .045 + float(scb["scb"]))
    amounts, denominators = synthetic_systemic_inputs(bank.assets)
    score, indicators = method1_score(amounts, denominators)
    surcharge = method1_surcharge(score)
    tables["gsib_indicators_stylized"] = indicators
    tables["gsib_categories_stylized"] = indicators.groupby("category")[["uncapped_score_bp", "score_bp"]].sum().reset_index()
    tables["gsib_summary"] = pd.DataFrame([{"score_bp": score, "method1_surcharge": surcharge,
                                            "status": "stylized/unverified denominators; Method 2 omitted; no GSIB designation"}])
    debt = pd.DataFrame({"principal_bn": [12., 5., 3., 10.], "days_to_maturity": [1500, 500, 200, 1800],
                         "eligible": [True, True, True, False]})
    tables["debt_schedule_synthetic"] = debt
    leverage_inputs = synthetic_leverage_inputs(bank, seed)
    reconciliation = total_leverage_exposure(leverage_inputs)
    tables["leverage_exposure_reconciliation"] = reconciliation
    tables["leverage_month_end_exposures"] = monthly_exposure_components(leverage_inputs)
    tables["leverage_daily_assets_synthetic"] = leverage_inputs.daily_assets
    tables["leverage_derivatives_synthetic"] = leverage_inputs.derivatives
    tables["leverage_credit_protection_synthetic"] = leverage_inputs.credit_protection
    tables["leverage_repos_synthetic"] = leverage_inputs.repos
    tables["leverage_commitments_synthetic"] = leverage_inputs.commitments
    leverage_paths = []
    for name, capital in projections.items():
        path = project_leverage(bank, capital, tables[f"balances_{name}"], tables[f"credit_{name}"], leverage_inputs)
        path[leverage_config.SCENARIO] = name
        leverage_paths.append(leverage_views(path))
    tables["slr_path"] = pd.concat(leverage_paths, ignore_index=True)
    tables["leverage_minima"] = summarize_leverage(tables["slr_path"])
    tables["leverage_sensitivities"] = leverage_sensitivities(leverage_inputs, bank.cet1 + bank.at1)
    tables["tlac_ltd_hypothetical"] = tlac_ltd_check(bank.cet1, bank.at1, debt,
                                                    current_standardized_rwa(bank), float(reconciliation[leverage_config.AMOUNT].sum()),
                                                    surcharge, surcharge, applicable=False)
    residuals = []
    for name, capital in projections.items():
        credit = tables[f"credit_{name}"]
        residuals.append({"scenario": name,
                          "max_cet1_residual_bn": float((capital.closing_cet1 - capital.opening_cet1 - capital.net_income + capital.distributions).abs().max()),
                          "max_allowance_residual_bn": float((credit.closing_allowance - credit.opening_allowance - credit.provision + credit.net_chargeoffs).abs().max()),
                          "max_loan_balance_residual_bn": float((credit.opening_balance - credit.default_principal - credit.scheduled_principal - credit.prepayment + credit.originations - credit.extra_runoff - credit.closing_balance).abs().max()),
                          "max_ifrs_reconciliation_residual_bn": float((totals[totals.scenario == name].cecl - totals[totals.scenario == name].ifrs9 - totals[totals.scenario == name].difference).abs().max())})
    tables["validation_residuals"] = pd.DataFrame(residuals)
    display = tables["capital_summary"][["scenario", "total_ppnr_bn", "total_provision_bn", "ending_cet1_bn",
                                         "minimum_cet1_ratio", "ending_cet1_ratio"]].copy()
    display["minimum_cet1_percent"] = display.pop("minimum_cet1_ratio") * 100
    display["ending_cet1_percent"] = display.pop("ending_cet1_ratio") * 100
    tables["capital_results_display"] = display
    tables["scb_results_display"] = pd.DataFrame([{"starting_cet1_percent": starting_ratio * 100,
                                                   "reference_minimum_cet1_percent": scb["minimum_ratio"] * 100,
                                                   "dividend_addon_percent": scb["dividend_addon"] * 100,
                                                   "scb_percent": scb["scb"] * 100,
                                                   "planning_hurdle_percent": (.045 + scb["scb"]) * 100}])
    display = tables["endgame_impact"][["framework", "total_rwa", "cet1_ratio", "incremental_required_cet1_bn"]].copy()
    display["cet1_percent"] = display.pop("cet1_ratio") * 100
    tables["endgame_results_display"] = display
    return CapitalPlan(bank, scenarios, tables, scb)
