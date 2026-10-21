# Methodology and model boundaries

This library demonstrates a reproducible capital planning workflow on synthetic data. It does not implement a supervisory model, an accounting standard in full, or a regulatory filing calculator. Monetary values are USD billions. Credit probabilities, yields, capital ratios, and risk weights use decimal units. Scenario rates, unemployment, spreads, and annualized real GDP growth use percentage units. Price indices use a common reference level of 100.

## Synthetic inputs and opening accounting

`synthetic_bank` uses `numpy.random.default_rng` with seed 20230727. Five loan balances receive bounded random perturbations and are normalized to a combined gross balance of 175. Net assets are 250. The opening contra-asset allowance is computed from the reference-state credit engine. Other gross assets are the residual required to make net assets equal deposits plus borrowings plus equity. This is a construction constraint, not a hidden capital adjustment.

Common equity before regulatory deductions is equity less AT1. Opening CET1 is net of an explicit regulatory deduction. Tier 2 instruments are included in borrowings. AT1 is included in equity, so neither capital component is added again to the balance sheet. See the generated `balance_sheet`, `starting_capital`, `portfolio_parameters`, and `income_run_rate` tables for complete inputs.

Both macro paths contain thirteen quarters. The projection uses the first nine. Baseline perturbations are seeded. The adverse path deliberately combines a deep recession, falling property and equity prices, widening credit spreads, and lower rates. These are stylized paths shaped like supervisory scenarios. They are NOT the published Federal Reserve values, forecasts, or fitted historical observations.

## Scenario loading

`load_scenario` accepts the canonical columns in `scenario.py`, an optional source-to-canonical column map, optional conversion from decimal rates, and optional index rebasing. Quarter identifiers must begin at one and remain contiguous. Nonfinite inputs and nonpositive price indices are rejected.

`load_fed_scenario` maps common domestic Fed column labels, accepts labels such as `Q1 2025` and `2025Q1`, and calculates BBB spread as BBB corporate yield minus the ten-year Treasury yield. It requires all three pre-scenario price bases: house prices, CRE prices, and equities. This preserves a decline that has already occurred in the first projected quarter. Rebasing a stressed path to its own first observation would erase that initial decline. The header and unit convention was checked against [the Federal Reserve domestic scenario table](https://www.federalreserve.gov/publications/2025-stress-test-scenarios.htm), table 3.A. A synthetic fixture tests this layout. The actual downloadable CSV could not be ingested by the web tool because its content type was unsupported; an exact real-file integration test is not claimed.

The library never downloads data at runtime. For a new Fed vintage, inspect headers and use `column_map` where necessary. Ignore additional domestic variables only after confirming the required model drivers remain present. International scenario files and trading shock workbooks are outside the adapter's scope.

## Lifetime credit loss

Annual conditional PD follows a logit model:

`logit(PD) = intercept + beta_u * (unemployment - 4.2) + beta_h * log(100 / house_prices) + beta_s * (BBB_spread - 1.5)`.

The intercept is calibrated with a bracketed bisection solver to reproduce each synthetic target annual PD at the reference state. Calibration rescales the probability residual by the smaller tail probability, preserving accuracy for extreme interior PDs. Quarterly hazards and annuity payments use `log1p` and `expm1` to avoid cancellation near zero. This is reference-state calibration, not an empirical estimate of the average PD over a business cycle. The sensitivities and targets below are model assumptions, not regulatory parameters or estimated bank coefficients.

| Portfolio | Target annual PD | Base LGD | Unemployment coefficient | House coefficient | Spread coefficient | Collateral coefficient |
| :- | :- | :- | :- | :- | :- | :- |
| C&I | 0.012000 | 0.420000 | 0.160000 | 0.320000 | 0.120000 | 0.000000 |
| CRE | 0.018000 | 0.280000 | 0.200000 | 0.560000 | 0.120000 | 0.500000 |
| Mortgage | 0.006000 | 0.180000 | 0.180000 | 0.960000 | 0.060000 | 0.600000 |
| Cards | 0.035000 | 0.880000 | 0.170000 | 0.080000 | 0.040000 | 0.000000 |
| Other consumer | 0.022000 | 0.650000 | 0.190000 | 0.240000 | 0.050000 | 0.000000 |

Unemployment and spread coefficients act per percentage point. House-price sensitivity acts on a log relative index. Secured LGD is `clip(base_LGD + collateral_beta * (1 - collateral_index / 100), 0, 1)`. CRE uses the CRE price index for LGD; mortgage uses the house price index. The PD house coefficient remains a common property-cycle driver for both.

The conditional quarterly hazard is `qPD = 1 - (1 - annual_PD)^(1/4)`. Survival at the start of a future quarter is the product of earlier nondefault probabilities. Marginal default probability is survival times that quarter's hazard. This prevents repeated defaults on the same lifetime exposure.

EAD is the outstanding principal before each quarter's payment. Scheduled principal follows a level-payment annuity using the quarterly effective rate. A zero-rate loan uses equal principal payments. Prepayments apply to remaining principal after scheduled payments. They do not reduce exposure before the first default interval. Conditional EAD already incorporates prepayments; the survival term incorporates defaults only. Principal repayments, prepayments, and ending principal reconcile exactly.

Each lifetime contribution is `marginal_PD * EAD * LGD * (1 + effective_annual_rate)^(-quarter/4)`. Expected recoveries are represented through LGD rather than modeled as separate delayed cash flows. The engine uses this discounted cash-shortfall approximation for the CECL comparison and IFRS comparison. It is not a claim that every allowable CECL method discounts losses this way.

The reasonable-and-supportable window is eight quarters from each measurement date, limited by available scenario observations. Macro levels then revert linearly to the reference state over four quarters. Beyond reversion, the reference state remains constant. If no forecast observations remain, the engine immediately uses the reference state. This explicitly avoids repeating the final adverse observation for a long mortgage lifetime. These horizon choices and level reversion are stylized assumptions.

## Allowances, provisions, and replenishment

The starting allowance is the same reference-state allowance in both capital projections. An adverse forecast is recognized through provision rather than silently changing opening equity. Each quarterly allowance is measured after that quarter's realized defaults and principal activity, using future observations from the next quarter.

Quarter zero in the accounting-comparison table is a scenario forecast remeasurement at the opening book size, not the actual ledger's starting allowance. The capital ledger always starts from the separately reported reference allowance. Quarters one onward are projected quarter-end measurements.

Initially defaulted exposures are a synthetic fraction of each pool. They enter both opening CECL and IFRS allowances as a next-quarter discounted LGD loss. They are resolved in the first projected quarter. Subsequent defaulted principal is immediately resolved into recovery and net charge-off, so no defaulted stock is carried forward or repeatedly written off.

The model uses a replenished pool approximation. Existing survivors amortize and prepay; originations replenish the book to its macro-driven target balance. Additional runoff is reported if the target is below surviving principal. Net loan growth is `clip(0.004 + 0.0007 * (GDP_growth - 2) - 0.0005 * (unemployment - 4.2), -0.025, 0.015)` per quarter. New and surviving exposures are regrouped into a representative pool with the same remaining maturity and credit parameters at each measurement date. This simplifies vintage aging and underwriting changes. It must not be interpreted as a loan-level closed-book model.

Allowance and principal accounting are explicit:

`closing_allowance = opening_allowance + provision - net_chargeoffs`.

`closing_principal = opening_principal - default_principal - scheduled_principal - prepayments + originations - extra_runoff`.

`default_principal = recoveries + net_chargeoffs`.

Allowance releases can create negative provisions. No provision floor is imposed. Per-pool provision adds to the aggregate used in the capital projection. Recoveries are not credited to income again because net charge-offs already recognize them.

## Simplified IFRS comparison

Performing pools enter stage 2 when current annual conditional PD is at least twice original annual PD. Otherwise they enter stage 1. Stage 1 includes losses from defaults in the next four quarters, or remaining contractual life if shorter. Stage 2 includes lifetime losses. Existing defaulted balances enter a separate stage 3 exposure and loss column. CECL includes lifetime performing loss plus the same defaulted-exposure loss. Therefore the reconciliation difference is entirely the shortened stage 1 default horizon; stage 2 and stage 3 match by construction.

This comparison omits the past-due backstops, qualitative significant-risk-increase criteria, cure periods, probability-weighted scenario mixtures, purchased credit-impaired assets, and defaulted-loan interest recognition of a complete IFRS model. The relative-PD threshold is stylized/unverified as an accounting rule. It is a configurable modeling choice.

## PPNR

Loan balances are shared with the credit engine. Interest income uses average opening and closing balances. Portfolio yields move gradually toward their starting yield plus a weighted change in short and long Treasury rates. Repricing speed is the fraction of the remaining yield gap closed each quarter. It is a stylized repricing model, not a contractual cash flow ladder.

Deposits scale with the aggregate loan balance. Deposit rates have a beta of 0.50 to the short-rate change and close half the target gap each quarter. Securities close 0.12 of their long-rate yield gap each quarter. Ordinary borrowing costs have a short-rate sensitivity of 0.8. Tier 2 borrowing costs remain at the starting stated rate. Cash earns the nonnegative short rate. Product rates are floored at zero. Starting short and long rate anchors are 4.5 and 4.2 percent.

Transaction fees depend on GDP and unemployment, wealth fees on the equity index, and origination fees on GDP and house prices. Expenses grow with annual inflation of 0.02 and increase with unemployment above the reference state. Transaction fees use GDP and unemployment coefficients of 0.02 and 0.025 per percentage point. Wealth fees use an equity-index exponent of 0.65. Origination fees use a GDP coefficient of 0.03 and the house-price index. Expenses increase by 0.016 per percentage point of unemployment above 4.2. Loan repricing speeds for C&I, CRE, mortgage, cards, and other consumer are 0.20, 0.15, 0.04, 0.60, and 0.10 per quarter, respectively. Exact coefficients are visible in `ppnr.py` and generated portfolio inputs. PPNR is NII plus noninterest income less noninterest expense. Annualized NIM is four times quarterly NII divided by average earning assets.

The deposit projection is a revenue assumption. The toolkit does not project a complete quarterly GAAP balance sheet or balance funding through a liquidity model. NPL interest suspension, hedges, security valuation changes, and nonlinear deposit migration are omitted.

## Capital accounting and SCB

Pre-tax income equals PPNR less provisions less other losses. The adverse scenario has a one-time combined trading and counterparty loss of 0.5 in the first quarter. This is a scalar assumption without position-level market or counterparty models. Taxes are 0.25 of positive pre-tax income. Loss quarters receive no tax benefit by default. A separate option enables tax benefits, without claiming deferred tax asset realizability.

Quarterly planned common dividends are 0.24, buybacks are 0.06, and preferred dividends are 0.03. Closing CET1 equals opening CET1 plus net income less these distributions. AT1 and Tier 2 remain constant. The toolkit reports CET1, tier 1, and total capital ratios; only CET1 is compared against the planning hurdle. Negative income and capital are retained in outputs.

Projected RWA starts from exposure-class weights. Loan balances evolve with the shared book projection. A stylized migration overlay is `0.012 * max(unemployment - 4.2, 0) + 0.006 * max(BBB_spread - 1.5, 0)`. Mortgage receives half this overlay. This is not an automatic feature of the current standardized rule. Gross exposure weights, allowance RWA adjustments, and default classifications are simplified proxies.

For SCB, the library constructs a separate stressed reference path with no common dividends or buybacks, while retaining preferred dividends and stated Tier 2 interest. This follows the capital-action structure in [12 CFR 252.44(c)](https://www.law.cornell.edu/cfr/text/12/252.44#c). The economics remain this project's internal synthetic models, so the result is an SCB estimate, not a Federal Reserve determination.

The calculation is `max(0.025, starting_CET1_ratio - minimum_projected_CET1_ratio + sum(planned_common_dividends_Q4_to_Q7) / RWA_at_minimum_ratio)`. The starting ratio is used, not the highest ratio reached later. Chronological peak-to-trough decline is reported separately. Both dividend timing and the denominator were verified against [12 CFR 225.8(f)(2)](https://www.law.cornell.edu/cfr/text/12/225.8#f_2).

The planning hurdle uses the CET1 minimum plus estimated SCB and caller-supplied GSIB and countercyclical buffers. The example assumes no GSIB or countercyclical buffer. This is a next-cycle planning comparison, not an effective-date determination or permission to execute distributions. The CET1 minimum was checked in [12 CFR 217.10(a)(1)](https://www.law.cornell.edu/cfr/text/12/217.10#a). The leverage extension reports separate leverage requirements and payout ratios. Automatic distribution changes, risk-based buffer interactions with tier 1 and total capital, and capital deduction changes are omitted.

## Historical Endgame comparison

The comparison freezes the July 2023 proposal, published as 88 FR 64028, rather than claiming to represent later proposals or current final implementation. The official text is linked from [the Federal Reserve announcement](https://www.federalreserve.gov/newsevents/pressreleases/bcreg20230727a.htm). The compact [source register](regulatory_sources.md) records verified sections and proxy treatment.

Current exposure classifications are assumed, not inferred from loans. Securities are treated as GSE exposures; mortgage receives a qualifying first-lien proxy. C&I public investment-grade and card transactor shares are synthetic. **Mortgage and CRE expanded weights are stylized/unverified aggregate proxies.** The library does not reproduce the residential or commercial LTV tables. Generic other assets, small opening default stocks, and gross-to-net RWA adjustments are also simplified. Source-based weights do not make these synthetic classifications verified.

Operational BI is computed from three synthetic annual financial observations. Other operating expense in BI means the specified financial-services component, not all personnel and administrative expenses. ILM is assumed to equal one. This is not a claim that the proposal fixed ILM at one for every bank. Loss-history estimation is omitted.

Market and CVA RWA are explicit placeholders and do not overlap the banking-book securities exposure. The requested illustrative aggregate floor uses current total RWA as its base, which is stylized/unverified as a US application. The generic Basel floor function is also available for callers supplying the appropriate revised standardized totals. The historical US proxy separately applies the market-model floor within expanded RWA, then retains the larger standardized or expanded capital stack. A before/after table reports both constructions, required capital at the same CET1 planning hurdle, and capital needed to preserve the starting CET1 ratio. Floor and dual-stack adjustments are reported separately so components reconcile even when either constraint binds.

## Method 1 and hypothetical TLAC

The GSIB calculator uses the twelve US indicators in five categories. It applies published table weights literally, including rounded interconnectedness, substitutability, and complexity weights. The substitutability cap is allocated proportionally across its indicator rows for reconciliation. Scores remain unrounded for bucket selection. Indicator amounts and global denominators in the example are synthetic and **stylized/unverified**. Method 2, assessment discretion, currency conversion, reporting-specific rounding, and GSIB designation are omitted.

The synthetic bank is not treated as a GSIB. TLAC and long-term debt checks therefore carry `applicable=False` and evaluate hypothetical minimum coverage only. Debt instruments are already assumed eligible; the code does not establish legal eligibility. It applies maturity recognition, uses CET1 and AT1 plus recognized debt for TLAC, and excludes a separate Tier 2 capital amount. TLAC distribution buffers and retained-income payout restrictions are not modeled. See the source register for the retrieved US minimum formulas and the updated leverage-buffer input.

## Calibration and generated outcomes

The synthetic bank holds 175 of gross loans, 55 of securities, 10 of cash, and residual other assets. Deposits are 196, borrowings are 30, and equity is 24. CET1 is 21, AT1 is 2, Tier 2 is 3, and the common-equity regulatory deduction is 1. The reference-state opening allowance is 2.736472. Every portfolio has an opening default fraction of 0.003. Annual fees are 1.5 for transactions, 0.9 for wealth, and 0.6 for originations; annual expenses are 8.0.

The credit sensitivities, collateral sensitivities, rate repricing, funding beta, fee sensitivities, expenses, other-loss scalar, and distribution mix are calibrated together. The macro paths and all loss, allowance, PPNR, capital, SCB, and RWA formulas are unchanged. This is a target-range calibration of synthetic inputs, not an empirical fit to a real bank or supervisory estimates.

The regenerated nine-quarter run starts at 11.806796% CET1. Baseline ends at 13.885977%. The adverse planned-distribution path reaches a minimum of 7.131349%, with a 4.675447 percentage point chronological decline. The reference path before discretionary common distributions reaches 8.352854%, with a 3.453942 point decline. Estimated SCB is 3.961678% and the planning hurdle is 8.461678%.

Adverse cumulative net charge-offs are 10.919001, or 6.239429% of the opening gross loan book. Adverse provisions are 12.934363; they include the increase in allowance. Baseline and adverse cumulative PPNR are 12.693931 and 8.947427, respectively. PPNR is positive and lower under stress in every quarter. The historical Endgame proxy increases starting RWA by 10.816559%; the seeded aggregate output floor is nonbinding. Explicit tests retain both binding and nonbinding floor inputs. All 160 unittest tests pass, including the original calibration tests and leverage benchmarks.

## Validation and reproducibility

The unittest suite covers analytic loss benchmarks, calibrated PDs, probability conservation, principal conservation, allowance and CET1 roll-forwards, provision additivity, monotone stress responses, stage reconciliation, deposit beta effects, SCB dividend timing and floor, both output floor cases, BI bands, GSIB cap and buckets, debt maturity boundaries, scenario round trips, and invalid inputs. Shared balance validation rejects shuffled quarters, missing portfolios, negative balances, and nonfinite inputs before any projection. Individual provisions are checked before aggregation so missing values cannot silently disappear in a sum. The analytic benchmark in `run_sensitivity.py` derives a fully amortizing loss outside the engine. Generated residual tables report actual floating-point errors in scientific notation.

No SciPy, pytest, plotting package, network service, or external dataset is used at runtime. Bisection and logistic calculations use the standard library. Outputs are deterministic for the documented seed. The workflow should not be mistaken for validation against actual bank losses or supervisory test results.


## Supplementary leverage ratio and exposure

The leverage extension implements the supplied 2026-10-19 rule specification. Paragraphs were checked through Cornell's CFR HTML on 2026-10-21; the eCFR page was inaccessible to the web reader. See [the source register](regulatory_sources.md). Monetary units remain USD billions and ratios remain decimals. The existing `tier1_ratio` remains Tier 1/RWA. `tier1_leverage_ratio` is Tier 1 divided by average consolidated assets less deductions, under 217.10(b)(4); `slr` is Tier 1/TLE under 217.10(c)(1). Minimum leverage and SLR are 4% and 3% under 217.10(a)(1)(iv)-(v).

`TLE = mean_daily(assets + sales-treatment securities - received unrehypothecated securities - derivative fair-value assets - Tier1 deductions) + mean_three_month_ends(PFE + RC + credit protection + gross repo adjustment + repo counterparty exposure + credit-equivalent commitments) - custodial exclusion`.

The daily carrying-value adjustments implement 217.10(c)(2)(i). Deductions occur once; the capital numerator is already net of deductions. Synthetic inputs expand business-day shocks to every calendar day using carry-forward, with initial backfill if the quarter starts on a weekend. The total calculator requires a complete, ordered calendar quarter and aligned snapshots for all three calendar month ends. Absent activities use explicit zero-amount snapshot rows.

PFE under 217.10(c)(2)(ii)(B) uses `alpha * multiplier * A`, where `multiplier = min(1, 0.05 + 0.95 * exp(V / (1.9 * A)))`, C=0, and alpha is 1.4 except for commercial end-users. A=0 gives zero PFE. Nonnegative V fixes the multiplier at one before exponentiation, avoiding overflow. A is the supplied aggregated add-on under 217.132(c)(7), not a recalculation of supervisory hedging sets. RC under 217.10(c)(2)(iii)(B) is `alpha * max(V - CVMr + CVMp, 0)`; ineligible cash-margin amounts do not enter either term. The eligibility flag asserts conditions (C)-(G).

Sold protection under 217.10(c)(2)(iv) is effective notional less eligible allocated purchased protection and recognized CET1 fair-value losses, floored at zero. The matched flag asserts compatible reference and remaining maturity at least as long. Purchased amounts must already reflect applicable hedge-value adjustments and must not be allocated repeatedly. This simplified input does not establish legal eligibility.

Gross repo exposure under 217.10(c)(2)(v) adds gross receivables less amounts already in daily assets when the same-counterparty netting criteria fail. Under (vi), transactions without QMNA are floored individually; qualifying transactions are summed and floored per counterparty and agreement identifier. Separate agreements cannot offset each other. Off-balance credit equivalents under (viii) apply 217.33(b) CCFs with a 10% floor: cancelable 10%; commitments of at most one year and short self-liquidating trade contingents 20%; longer commitments, performance bonds and performance standby LCs 50%; guarantees and financial standby LCs 100%. Longer trade contingents are rejected rather than assigned the short-trade CCF. The custodial switch under (x), off by default, subtracts the daily lesser of qualifying central-bank deposits and linked fiduciary/custodial deposits.

The leverage buffer is `max(SLR - 0.03, 0)` under 217.11(c)(4). Requirements under 217.11(a)(2)(v) are half the latest Method 1 surcharge for the GSIB BHC and the lesser of 0.01 or half the parent's surcharge for a state member bank subsidiary. Table 2 to 217.11(c)(4)(iii) maps relative buffers above 100%, above 75%, above 50%, above 25%, and at most 25% to no leverage limit, 60%, 40%, 20%, and 0%. Boundary comparisons tolerate only floating-point noise. A zero applicable requirement gives no leverage-buffer payout restriction; minimum SLR headroom remains visible. A no-limit payout is NaN with an explicit boolean. This is a leverage-only measure, not an overall distribution approval. The subsidiary requirement view does not implement the full Table 3 capital-buffer interaction in 217.11(f).

**Illustrative projection assumptions:** Closing assets are starting net assets plus cumulative gross loan balance change less allowance change. All other assets stay fixed. Quarterly average assets equal the mean of opening and closing assets. The daily shape, derivatives, sold protection, repos, and commitments retain their as-of mix and scale by average assets relative to opening daily average assets. AT1 and deductions stay fixed. This is a balance-sheet proxy, not a funding forecast. The same nine-quarter capital path feeds Category III, GSIB BHC, and subsidiary requirement views. The illustrative 2% Method 1 surcharge is separate from the existing synthetic Method 1 score, which implies zero surcharge. Existing distributions and capital results are unchanged. Computed as-of TLE replaces the scalar in hypothetical TLAC/LTD checks.

Sensitivity cases hold Tier 1 constant. A 10bn matched repo book adds 10bn on-balance receivables financed by repo liabilities, with E=C, no extra counterparty exposure, and no second gross add-back. Alpha removal affects both PFE and RC and is a counterfactual. Custodial exclusion assumes eligibility only in that case. Aggregated add-ons, simplified protection offsets, synthetic data, clearing exceptions, agency indemnities, and shared margin agreements limit regulatory completeness. See the generated reconciliation, path, minima, sensitivities, and raw synthetic inputs in `examples/output/`.

Hand-computed tests cover TLE 1066 and SLR 60/1066; negative-V multiplier 0.611238638206 and PFE 8.557340934886; repo exposure 5 without QMNA and zero with QMNA; daily mean 110 and monthly mean 12; exact payout bands; subsidiary caps; all supported CCF types; deductions; custody; and TLAC integration. The README leverage tables are taken from actual generated CSV files, not estimated outcomes.
