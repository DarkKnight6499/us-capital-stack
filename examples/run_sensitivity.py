"""Run unemployment sensitivity and a fully amortizing credit benchmark."""

from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from capital_stack.cecl import allowances, loss_term_structure
from capital_stack.data import reference_scenario, synthetic_bank
from capital_stack.reporting import markdown_table, write_table
from capital_stack.scenario import LONG_RUN, Scenario


def main() -> None:
    """Write sensitivity tables using the same seeded bank as the capital plan."""
    bank = synthetic_bank()
    rows = []
    for unemployment in np.arange(4.2, 10.21, 1.0):
        frame = reference_scenario().frame.copy()
        frame["unemployment"] = unemployment
        scenario = Scenario("unemployment_synthetic", frame)
        macro = {**LONG_RUN, "unemployment": float(unemployment)}
        row = {"unemployment_percent": unemployment, "cecl_bn": 0., "ifrs9_bn": 0.}
        for pool in bank.portfolios:
            result = allowances(pool, scenario, observed_macro=macro)
            row["cecl_bn"] += float(result["cecl"])
            row["ifrs9_bn"] += float(result["ifrs9"])
        rows.append(row)
    sensitivity = pd.DataFrame(rows)
    output = PROJECT / "examples" / "output"
    write_table(sensitivity, output, "unemployment_sensitivity")
    benchmark = replace(bank.portfolios[0], balance=1., annual_pd=.04, lgd=.5,
                        maturity_quarters=4, annual_prepayment=0., effective_rate=0., default_fraction=0.)
    term_structure = loss_term_structure(benchmark, reference_scenario())
    hazard = 1 - .96 ** .25
    analytic = sum(.5 * (1 - (step - 1) / 4) * (1 - hazard) ** (step - 1) * hazard for step in range(1, 5))
    numeric = float(term_structure.expected_loss.sum())
    write_table(term_structure, output, "analytic_credit_term_structure")
    write_table(pd.DataFrame([{"analytic_ecl_bn": analytic, "engine_ecl_bn": numeric,
                               "absolute_error_bn": abs(analytic - numeric)}]), output, "analytic_credit_benchmark")
    print(markdown_table(sensitivity), end="")
    print(f"Analytic benchmark ECL: {analytic:.12f}; engine: {numeric:.12f}; absolute error: {abs(analytic - numeric):.3e}")


if __name__ == "__main__":
    main()
