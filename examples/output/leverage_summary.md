# Illustrative synthetic leverage results

All monetary amounts are USD billions. Ratios are decimals. No real bank observations are used.

## As-of ratios

| tier1_capital | leverage_denominator | total_leverage_exposure | tier1_leverage_ratio | slr |
| :- | :- | :- | :- | :- |
| 23 | 249.000000 | 392.804632 | 0.092369 | 0.058553 |


## Exposure reconciliation

| component | rule_paragraph | amount |
| :- | :- | :- |
| on_balance_assets | 217.10(c)(2)(i) | 250.000000 |
| securities_sales_treatment | 217.10(c)(2)(i) | 1.500000 |
| tier1_deductions | 217.10(c)(2)(i) | -1.000000 |
| securities_received_unrehypothecated | 217.10(c)(2)(i) | -0.500000 |
| derivative_fair_value_assets | 217.10(c)(2)(i) | -8.000000 |
| derivative_pfe | 217.10(c)(2)(ii)(B) | 44.799077 |
| derivative_replacement_cost | 217.10(c)(2)(iii)(B) | 12.405555 |
| sold_credit_protection | 217.10(c)(2)(iv) | 28.000000 |
| gross_repo_receivables | 217.10(c)(2)(v) | 5.000000 |
| repo_counterparty_exposure | 217.10(c)(2)(vi) | 1.500000 |
| off_balance_commitments | 217.10(c)(2)(viii) | 59.100000 |
| custodial_exclusion | 217.10(c)(2)(x) | 0.000000 |


## Nine-quarter path

| scenario | quarter | total_leverage_exposure | tier1_leverage_ratio | slr |
| :- | :- | :- | :- | :- |
| baseline | 1 | 393.512647 | 0.094054 | 0.059621 |
| baseline | 2 | 394.752203 | 0.095607 | 0.060606 |
| baseline | 3 | 395.842727 | 0.097252 | 0.061649 |
| baseline | 4 | 396.960065 | 0.098928 | 0.062712 |
| baseline | 5 | 398.060271 | 0.100624 | 0.063787 |
| baseline | 6 | 399.137056 | 0.102339 | 0.064875 |
| baseline | 7 | 400.221387 | 0.104084 | 0.065981 |
| baseline | 8 | 401.318001 | 0.105836 | 0.067092 |
| baseline | 9 | 402.436320 | 0.107611 | 0.068217 |
| severely_adverse | 1 | 388.134660 | 0.070413 | 0.044634 |
| severely_adverse | 2 | 382.585128 | 0.070877 | 0.044927 |
| severely_adverse | 3 | 381.296198 | 0.070172 | 0.044481 |
| severely_adverse | 4 | 380.880527 | 0.068954 | 0.043708 |
| severely_adverse | 5 | 381.218367 | 0.067426 | 0.042740 |
| severely_adverse | 6 | 382.141624 | 0.066109 | 0.041905 |
| severely_adverse | 7 | 383.390835 | 0.064808 | 0.041080 |
| severely_adverse | 8 | 384.747087 | 0.063622 | 0.040329 |
| severely_adverse | 9 | 386.136770 | 0.062599 | 0.039681 |


## Minimum SLR and headroom

| scenario | configuration | minimum_slr | minimum_slr_quarter | buffer_requirement | headroom_to_3pct | headroom_to_3pct_plus_buffer |
| :- | :- | :- | :- | :- | :- | :- |
| baseline | category_iii_illustrative | 0.059621 | 1 | 0.000000 | 0.029621 | 0.029621 |
| baseline | gsib_bhc_illustrative | 0.059621 | 1 | 0.010000 | 0.029621 | 0.019621 |
| baseline | gsib_subsidiary_illustrative | 0.059621 | 1 | 0.010000 | 0.029621 | 0.019621 |
| severely_adverse | category_iii_illustrative | 0.039681 | 9 | 0.000000 | 0.009681 | 0.009681 |
| severely_adverse | gsib_bhc_illustrative | 0.039681 | 9 | 0.010000 | 0.009681 | -0.000319 |
| severely_adverse | gsib_subsidiary_illustrative | 0.039681 | 9 | 0.010000 | 0.009681 | -0.000319 |


## Isolated sensitivities

| sensitivity | total_leverage_exposure | exposure_change_bn | slr | slr_change_bp |
| :- | :- | :- | :- | :- |
| repo_matched_book_plus_10bn_illustrative | 402.804632 | 10.000000 | 0.057100 | -14.536397 |
| remove_1_4_factor_illustrative | 380.382753 | -12.421879 | 0.060465 | 19.121312 |
| custodial_exclusion_illustrative | 386.804632 | -6.000000 | 0.059462 | 9.082613 |


## Assumptions and limits

Illustrative Method 1 surcharge is 2.0%; BHC and subsidiary buffer requirements are 1.0%. Category III has no leverage buffer. All configurations share the same synthetic exposure and capital paths. The subsidiary view is a requirement comparison, not a separate legal-entity balance sheet.

Projected assets equal starting assets plus gross loan growth less allowance growth; other assets stay fixed. Average quarterly assets equal the mean of opening and closing assets. The daily shape and month-end derivative and off-balance exposures scale with that average, holding the as-of mix fixed. Tier 1 deductions and AT1 stay constant. Business-day asset shocks carry forward on weekends.

Repo growth adds 10bn of fully collateralized on-balance receivables financed by matched repo liabilities, with no incremental counterparty exposure. Alpha removal is a counterfactual, not a permitted election. Custodial eligibility is assumed only in that sensitivity.

Aggregated SA-CCR add-ons are inputs. Credit-protection hedge eligibility is simplified to an asserted flag and allocated amount, net of required hedge-value adjustments. Clearing and agency exceptions are omitted. NaN payout means no leverage limit; other capital-buffer and retained-income restrictions can still bind.

Rules: [12 CFR 217.10(b)(4), (c)(1)-(2)](https://www.law.cornell.edu/cfr/text/12/217.10), [217.11(a)(2)(v), (c)(4), Table 2](https://www.law.cornell.edu/cfr/text/12/217.11).
