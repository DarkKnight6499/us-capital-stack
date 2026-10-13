# us-capital-stack

A Python library for US bank capital planning on reproducible synthetic data. It links macro scenarios, lifetime credit losses, pre-provision net revenue (PPNR), capital distributions, and risk-weighted assets (RWA). It also compares simplified current standardized capital with a historical Basel III Endgame proposal and computes systemic-risk and hypothetical debt-coverage checks.

The seeded bank has USD 250 billion of net assets. Baseline and severely adverse paths contain 13 quarters; the capital projection covers 9 quarters. These are **synthetic, stylized paths shaped like supervisory scenarios, NOT published Federal Reserve numbers**. No network access or external data is needed at runtime.

## Run

Run from the project root with Python, NumPy, and pandas available. The examples and tests import the source tree directly, so installation is optional.

```text
python -m unittest discover -s tests -v
python examples/run_capital_plan.py
python examples/run_sensitivity.py
```

For use as an installed library:

```text
python -m pip install -e .
```

```python
from capital_stack import run_plan

plan = run_plan()
print(plan.tables["capital_results_display"])
print(plan.tables["requirements"])
```

The examples write CSV and Markdown tables under [examples/output](examples/output/). Start with [capital_plan_summary.md](examples/output/capital_plan_summary.md). Both examples use seed `20230727` through `numpy.random.default_rng`. CSV files retain more precision than the display tables. The CI workflow is configured to run the same suite and examples across its Python version matrix.

## Methodology

The opening balance sheet contains securities, C&I, CRE, residential mortgage, cards, other consumer loans, cash, and other assets. Deposits, borrowings, and equity reconcile with net assets. CET1, AT1, Tier 2, regulatory deductions, and the opening contra-asset allowance are explicit. The opening allowance is USD 2.736472 billion; gross exposures and starting standardized RWA appear in generated tables.

Credit losses use conditional PD, collateral-sensitive LGD, and amortizing EAD with prepayments. A logit intercept reproduces each synthetic target annual PD at the long-run reference state. Macro sensitivities act on unemployment, house prices, and BBB spreads. Marginal default probabilities include survival, and losses are discounted at the effective interest rate. The reasonable-and-supportable forecast spans 8 quarters, followed by 4 quarters of linear reversion, subject to available observations.

CECL measures lifetime losses. The simplified IFRS 9 comparison measures twelve-month default losses for stage 1, lifetime losses for stage 2, and a separate loss on the defaulted stage 3 stock. The relative annual-PD threshold is 2 times origination PD. This threshold is **stylized/unverified as an accounting rule**. Stage 1 includes the full modeled loss from defaults in its shorter default window, not only payments missed within that window.

Credit projection resolves defaults into recoveries and charge-offs, then replenishes loans to scenario-driven balances. Quarterly provision equals closing allowance minus opening allowance plus net charge-offs. Surviving and new loans are regrouped into a representative pool each quarter. The shared balance paths feed PPNR and RWA. This is a replenished-pool approximation, not a vintage-level loan simulation.

PPNR equals NII plus macro-sensitive transaction, wealth, and origination fees minus expenses. NII uses average balances, gradual short-rate and long-rate repricing, and deposit beta 0.50. NIM reconciles to NII and average earning assets. Adverse other losses are a one-time USD 0.5 billion combined trading and counterparty scalar. Taxes are 25% of positive pre-tax income, with no loss-quarter tax benefit by default. Closing CET1 equals opening CET1 plus net income minus common dividends, buybacks, and preferred dividends.

SCB uses the starting CET1 ratio less the lowest stressed ratio, plus planned common dividends in quarters four through seven divided by RWA at that minimum. Its floor is 2.5%. Chronological peak-to-trough decline is a separate statistic. The SCB reference path excludes common dividends and buybacks while retaining instrument obligations. The formula and capital-action structure were checked against [12 CFR 225.8(f)(2)](https://www.law.cornell.edu/cfr/text/12/225.8#f_2) and [12 CFR 252.44(c)](https://www.law.cornell.edu/cfr/text/12/252.44#c). This produces an internal estimate, not a supervisory determination.

The Endgame experiment freezes the 2023 proposal. Conditional corporate and retail weights and the Business Indicator Component are sourced from the primary proposal. **Mortgage and CRE aggregate weights are stylized/unverified proxies**. Operational RWA uses the Business Indicator from synthetic annual histories. ILM is assumed 1; the proposal used a loss-history multiplier with a floor, so this assumption does not reproduce its full loss-history treatment. See [the Federal Reserve announcement and linked proposal](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20230727a.htm) and [the verified source register](docs/regulatory_sources.md).

The requested illustrative floor is `max(expanded RWA, floor factor * current standardized RWA)`, with factor 72.5%. Using current US RWA as that floor base is **stylized/unverified**. The fully phased-in [Basel Framework RBC20.4 and RBC20.11](https://www.bis.org/committees/bcbs/basel-framework/standard/rbc?allChapters=true) uses revised standardized totals. A separate historical US proxy applies the proposal's floor using standardized market risk inside the expanded stack and then retains the larger capital stack. Both constructions have explicit floor and dual-stack reconciliation adjustments.

The GSIB Method 1 calculator includes the systemic categories, underlying indicator weights, global denominators, substitutability cap, and surcharge buckets. Denominators are **stylized/unverified**, and the synthetic bank is not assigned GSIB status. TLAC and long-term debt checks use the retrieved US GSIB minimum structure and maturity recognition, with eligibility asserted by input and applicability set false in the example. Method 2, debt legal eligibility, and TLAC distribution buffers are omitted. [12 CFR 217.404](https://www.law.cornell.edu/cfr/text/12/217.404), [217.403(b)](https://www.law.cornell.edu/cfr/text/12/217.403#b), [252.62](https://www.law.cornell.edu/cfr/text/12/252.62), and [252.63](https://www.law.cornell.edu/cfr/text/12/252.63) support these mechanics.

Detailed equations, coefficients, units, timing, and exclusions are in [docs/methodology.md](docs/methodology.md).

## Validation and actual results

The final run passed **123 unittest tests**, and both examples completed successfully. Tests cover independent analytic ECL benchmarks, probability and principal conservation, allowance and CET1 accounting, provision additivity, monotone stress responses, IFRS staging, deposit beta, SCB timing and floor, binding and nonbinding output floors, operational-risk bands, GSIB buckets, debt maturity boundaries, CSV round trips, and invalid or misaligned inputs. Missing portfolio provisions are rejected before aggregation. Calibration tests additionally enforce the capital, credit-loss, PPNR, and Endgame ranges below without changing the accounting or regulatory formulas.

All results below come from the generated CSV files, with monetary amounts in USD billions.

### Capital projection

| Scenario | PPNR, USD bn | Provisions, USD bn | Ending CET1, USD bn | Minimum CET1, % | Ending CET1, % |
| :- | :- | :- | :- | :- | :- |
| baseline | 12.693931 | 2.796590 | 25.453006 | 12.020549 | 13.885977 |
| severely_adverse | 8.947427 | 12.934363 | 13.322217 | 7.131349 | 7.131349 |

Starting CET1 is 11.806796%. The adverse planned-distribution path loses 4.675447 percentage points from peak to trough. The SCB reference, before discretionary common distributions and without management remediation, loses 3.453942 percentage points and reaches its minimum of 8.352854% in quarter 5. Its dividend add-on is 0.507736%, and estimated SCB is **3.961678%**. Adding the verified CET1 minimum produces a next-cycle planning hurdle of **8.461678%**. [12 CFR 217.10(a)(1)(i)](https://www.law.cornell.edu/cfr/text/12/217.10#a) supplies that minimum.

Cumulative adverse credit losses are **USD 10.919001 billion**, or **6.239429% of the USD 175 billion opening gross loan book over nine quarters**. These are net charge-offs, not provisions; provisions also reflect the change in allowance. Baseline net charge-offs total USD 2.947979 billion, or 1.684559% of opening loans. Adverse quarterly PPNR remains positive, ranging from USD 0.734397 billion to USD 1.351190 billion, and is lower than baseline in every projected quarter.

| Scenario | Minimum headroom, percentage points | Minimum capital headroom, USD bn | Quarters below hurdle |
| :- | :- | :- | :- |
| baseline | 3.558872 | 6.354083 | 0 |
| severely_adverse | -1.330329 | -2.485215 | 8 |

Baseline remains above the estimated planning hurdle throughout the horizon. The adverse planned-distribution path falls below that hurdle, but remains above the minimum CET1 ratio. No management remediation or capital injection is assumed. These are deliberately calibrated synthetic outcomes, not evidence of adequacy for an actual institution or a fit to supervisory bank results.

### CECL and IFRS 9 reconciliation

| Scenario | Measurement quarter | CECL, USD bn | IFRS 9, USD bn | Difference, USD bn |
| :- | :- | :- | :- | :- |
| baseline | 0 | 2.715705 | 1.221284 | 1.494421 |
| baseline | 9 | 2.585083 | 1.025701 | 1.559381 |
| severely_adverse | 0 | 7.822667 | 3.190376 | 4.632291 |
| severely_adverse | 9 | 4.751834 | 4.751834 | 0.000000 |

Measurement quarter zero is a scenario-forecast remeasurement on the opening book, not the ledger's starting allowance. Capital starts from the common reference allowance. Projected quarter-end allowances feed provisions. The CECL versus IFRS difference comes from stage 1's shorter default horizon; stage 2 and stage 3 use the same loss model. All adverse performing pools reach stage 2 by quarter three in this calibration.

### Historical proposal impact

| Framework | RWA, USD bn | Incremental required CET1, USD bn | CET1, % |
| :- | :- | :- | :- |
| Current standardized proxy | 177.863669 | 0.000000 | 11.806796 |
| Illustrative aggregate floor | 197.102397 | 1.627919 | 10.654361 |
| Historical US proposal proxy | 197.102397 | 1.627919 | 10.654361 |

The Endgame RWA increase is **10.816559%**. The illustrative floor does not bind for the seeded inputs. Explicit tests also show a binding floor: expanded RWA 60 and standardized RWA 100 produce 72.5; expanded RWA 80 and standardized RWA 100 produce a nonbinding result of 80. The historical proxy yields the same total in the seeded case, but its construction differs. Operational BI is USD 9.501130 billion, BIC is USD 1.395169 billion, and operational RWA is USD 17.439618 billion. Incremental required CET1 holds the planning hurdle constant; it is not the capital needed to preserve the opening CET1 ratio. That separate amount is reported in [endgame_impact.csv](examples/output/endgame_impact.csv).

### Analytic and sensitivity checks

The fully amortizing credit benchmark gives analytic ECL 0.012563782484, engine ECL 0.012563782484, and absolute error 6.765e-17 USD billion. Increasing only unemployment from 4.2% to 10.2% increases total CECL from USD 2.736472 billion to USD 5.901556 billion.

| scenario | max_cet1_residual_bn | max_allowance_residual_bn | max_loan_balance_residual_bn | max_ifrs_reconciliation_residual_bn |
| :- | :- | :- | :- | :- |
| baseline | 3.219647e-15 | 0.000000e+00 | 7.105427e-15 | 2.220446e-16 |
| severely_adverse | 9.992007e-16 | 1.942890e-16 | 7.105427e-15 | 8.881784e-16 |

The synthetic Method 1 score is 17.009016 basis points and its Method 1 surcharge is 0%. This is neither a verified global assessment nor a GSIB designation. [Hypothetical TLAC and debt checks](examples/output/tlac_ltd_hypothetical.csv) report risk and leverage coverage separately.

## Bring a scenario CSV

`load_scenario` accepts the columns below, with optional source-column mapping, rate conversion, and index rebasing:

```text
quarter, unemployment, real_gdp_growth, house_prices, cre_prices,
equity_index, rate_3m, rate_10y, bbb_spread, vix
```

Quarter identifiers must be contiguous and begin at the first projected quarter. Unemployment, annualized GDP growth, rates, and spreads use percentage units; PDs and financial-model rates use decimals. Prices are relative to the model's long-run reference level. `scenario.py` defines the exact reference state. Canonical round trips are tested.

```python
from capital_stack import load_scenario, run_plan

paths = {
    "baseline": load_scenario("data/baseline.csv", "baseline"),
    "severely_adverse": load_scenario("data/adverse.csv", "severely_adverse"),
}
plan = run_plan(scenario_paths=paths)
```

For domestic Federal Reserve files, `load_fed_scenario` maps common published headers, derives BBB spread from corporate yield less Treasury yield, and validates consecutive date labels. Supply the pre-scenario bases for `house_prices`, `cre_prices`, and `equity_index` in its `price_bases` dictionary. This preserves an initial price decline. Inspect each vintage and use `column_map` for differing headers. [The Federal Reserve domestic scenario table](https://www.federalreserve.gov/publications/2025-stress-test-scenarios.htm) was used to check header and unit conventions. The downloadable CSV was blocked by the web reader's content-type handling; exact real-file integration remains unverified. No actual Fed observations are distributed with this project.

## Layout

| Location | Purpose |
| :- | :- |
| `src/capital_stack/data.py`, `models.py`, `scenario.py` | Synthetic inputs, validated data types, and CSV loading |
| `cecl.py`, `numerics.py` | Lifetime losses, IFRS comparison, hazards, amortization, and bisection |
| `ppnr.py`, `projection.py` | Revenue, provisions, capital actions, RWA, and SCB |
| `endgame.py`, `systemic.py` | Historical framework comparison, Method 1, TLAC, and debt minima |
| `planning.py`, `reporting.py`, `validation.py` | End-to-end orchestration, tables, and alignment validation |
| `tests/` | Standard-library unittest suite |
| `examples/` | Runnable capital-plan and sensitivity examples |
| `docs/` | Model methodology and regulatory verification register |
| `.github/workflows/ci.yml` | Test and example workflow |

## Limitations

All bank data, macro paths, credit coefficients, and portfolio classifications are synthetic. Target PDs are reference-state calibrations, not empirical through-the-cycle estimates. CECL and IFRS outputs approximate discounted credit shortfalls and do not implement either accounting standard in full. Forecast horizons, macro reversion, relative-PD staging, vintage regrouping, and immediate default resolution are modeling assumptions.

The capital projection omits a full quarterly funding balance sheet, liquidity, security valuation and AOCI, evolving regulatory deductions, tax-asset realizability, management remediation, and distribution approvals. RWA migration is a stylized overlay. Endgame results use historical proposal mechanics and omit LTV tables, allowance RWA adjustments, loss-history ILM estimation, and position-level market and CVA calculations. Mortgage and CRE weights, global denominators, generic asset classification, and the illustrative US floor application remain **stylized/unverified**. Market risk and CVA are placeholder inputs.

Only the displayed CET1 planning hurdle is checked for capital adequacy. Method 2, legal GSIB designation, full leverage and total-capital requirements, TLAC payout buffers, and legal debt eligibility are outside scope. Regulatory citations establish the named mechanics only; outputs are not regulatory filings, accounting opinions, or current final Endgame implementation estimates.

## License

MIT, see [LICENSE](LICENSE).
