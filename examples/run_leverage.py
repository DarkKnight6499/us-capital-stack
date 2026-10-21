"""Run the illustrative leverage extension and write auditable synthetic results."""

from pathlib import Path
import sys

# Config: paths and output selections for this illustrative example.
PROJECT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT / "src"
OUTPUT = PROJECT / "examples" / "output"
TABLES = ("leverage_exposure_reconciliation", "slr_path", "leverage_minima", "leverage_sensitivities",
          "leverage_month_end_exposures", "leverage_daily_assets_synthetic", "leverage_derivatives_synthetic",
          "leverage_credit_protection_synthetic", "leverage_repos_synthetic", "leverage_commitments_synthetic")
SUMMARY_FILE = "leverage_summary.md"
sys.path.insert(0, str(SOURCE))

from capital_stack import leverage_config as config
from capital_stack.leverage import leverage_ratios
from capital_stack.planning import run_plan
from capital_stack.reporting import markdown_table, write_table


def main() -> None:
    """Write the reconciliation, nine-quarter paths, minima, sensitivities, and inputs."""
    plan = run_plan()
    for name in TABLES:
        write_table(plan.tables[name], OUTPUT, name)
    reconciliation = plan.tables["leverage_exposure_reconciliation"]
    exposure = float(reconciliation[config.AMOUNT].sum())
    daily = plan.tables["leverage_daily_assets_synthetic"]
    ratios = leverage_ratios(plan.bank.cet1 + plan.bank.at1, float(daily[config.ASSETS].mean()),
                             float(daily[config.DEDUCTIONS].mean()), exposure)
    path = plan.tables["slr_path"]
    display = path.loc[path[config.VIEW] == config.CATEGORY_III,
                       [config.SCENARIO, config.QUARTER, config.TLE, config.LEVERAGE_RATIO, config.SLR]]
    sections = ["# Illustrative synthetic leverage results",
                "All monetary amounts are USD billions. Ratios are decimals. No real bank observations are used.",
                "## As-of ratios", markdown_table(ratios),
                "## Exposure reconciliation", markdown_table(reconciliation),
                "## Nine-quarter path", markdown_table(display),
                "## Minimum SLR and headroom", markdown_table(plan.tables["leverage_minima"]),
                "## Isolated sensitivities", markdown_table(plan.tables["leverage_sensitivities"]),
                "## Assumptions and limits",
                "Illustrative Method 1 surcharge is 2.0%; BHC and subsidiary buffer requirements are 1.0%. "
                "Category III has no leverage buffer. All configurations share the same synthetic exposure and capital paths. "
                "The subsidiary view is a requirement comparison, not a separate legal-entity balance sheet.",
                "Projected assets equal starting assets plus gross loan growth less allowance growth; other assets stay fixed. "
                "Average quarterly assets equal the mean of opening and closing assets. "
                "The daily shape and month-end derivative and off-balance exposures scale with that average, "
                "holding the as-of mix fixed. Tier 1 deductions and AT1 stay constant. "
                "Business-day asset shocks carry forward on weekends.",
                "Repo growth adds 10bn of fully collateralized on-balance receivables financed by matched repo liabilities, "
                "with no incremental counterparty exposure. Alpha removal is a counterfactual, not a permitted election. "
                "Custodial eligibility is assumed only in that sensitivity.",
                "Aggregated SA-CCR add-ons are inputs. Credit-protection hedge eligibility is simplified to an asserted flag "
                "and allocated amount, net of required hedge-value adjustments. Clearing and agency exceptions are omitted. "
                "NaN payout means no leverage limit; other capital-buffer and retained-income restrictions can still bind.",
                "Rules: [12 CFR 217.10(b)(4), (c)(1)-(2)](https://www.law.cornell.edu/cfr/text/12/217.10), "
                "[217.11(a)(2)(v), (c)(4), Table 2](https://www.law.cornell.edu/cfr/text/12/217.11)."]
    (OUTPUT / SUMMARY_FILE).write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(markdown_table(ratios), end="")
    print(markdown_table(plan.tables["leverage_minima"]), end="")
    print(markdown_table(plan.tables["leverage_sensitivities"]), end="")


if __name__ == "__main__":
    main()
