"""Run the complete synthetic capital plan from any working directory."""

from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT / "src"))

from capital_stack.planning import run_plan
from capital_stack.reporting import markdown_table, write_table


def main() -> None:
    """Write reproducible CSV and Markdown tables under examples/output."""
    plan = run_plan()
    output = PROJECT / "examples" / "output"
    for name, frame in plan.tables.items():
        write_table(frame, output, name)
    for name, scenario in plan.scenarios.items():
        scenario.to_csv(output / f"scenario_{name}_synthetic.csv")
    sections = ["# Synthetic capital plan", "All monetary quantities are USD billions. Ratios use decimals. All data and macro paths are synthetic.",
                "The SCB reference excludes common dividends and buybacks. Planning paths include planned distributions.",
                "## Capital projection", markdown_table(plan.tables["capital_summary"]),
                "## SCB calculation", markdown_table(plan.tables["scb_calculation"]),
                "## Credit accounting comparison", markdown_table(plan.tables["cecl_ifrs9_totals"]),
                "## Historical proposal comparison", markdown_table(plan.tables["endgame_impact"]),
                "## Illustrative leverage minima", markdown_table(plan.tables["leverage_minima"]),
                "## Accounting residuals", markdown_table(plan.tables["validation_residuals"], scientific=True),
                "Historical proposal only. Mortgage and CRE proxy weights and GSIB denominators are stylized/unverified. Market and CVA inputs are placeholders. TLAC and debt checks are hypothetical and not applicable to this synthetic bank."]
    (output / "capital_plan_summary.md").write_text("\n\n".join(sections) + "\n", encoding="utf-8")
    print(markdown_table(plan.tables["capital_summary"]), end="")
    print(markdown_table(plan.tables["scb_calculation"]), end="")
    print(markdown_table(plan.tables["endgame_impact"][["framework", "total_rwa", "cet1_ratio", "incremental_required_cet1_bn"]]), end="")


if __name__ == "__main__":
    main()
