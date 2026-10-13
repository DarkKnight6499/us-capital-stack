# Synthetic capital plan

All monetary quantities are USD billions. Ratios use decimals. All data and macro paths are synthetic.

The SCB reference excludes common dividends and buybacks. Planning paths include planned distributions.

## Capital projection

| scenario | assets_bn | opening_allowance_bn | starting_cet1_ratio | total_ppnr_bn | total_provision_bn | total_other_losses_bn | total_credit_losses_bn | credit_losses_to_opening_loans | total_net_income_bn | total_distributions_bn | ending_cet1_bn | minimum_cet1_ratio | minimum_quarter | ending_cet1_ratio | peak_to_trough_decline | closing_allowance_bn |
| :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- |
| baseline | 250.000000 | 2.736472 | 0.118068 | 12.693931 | 2.796590 | 0.000000 | 2.947979 | 0.016846 | 7.423006 | 2.970000 | 25.453006 | 0.120205 | 1 | 0.138860 | 0.000000 | 2.585083 |
| severely_adverse | 250.000000 | 2.736472 | 0.118068 | 8.947427 | 12.934363 | 0.500000 | 10.919001 | 0.062394 | -4.707783 | 2.970000 | 13.322217 | 0.071313 | 9 | 0.071313 | 0.046754 | 4.751834 |


## SCB calculation

| starting_ratio | minimum_ratio | minimum_quarter | rwa_at_minimum | starting_to_minimum_decline | dividend_addon | scb | reference_peak_to_trough_decline |
| :- | :- | :- | :- | :- | :- | :- | :- |
| 0.118068 | 0.083529 | 5 | 189.074802 | 0.034539 | 0.005077 | 0.039617 | 0.034539 |


## Credit accounting comparison

| scenario | quarter | cecl | ifrs9 | difference | stage1_balance | stage2_balance | stage3_balance |
| :- | :- | :- | :- | :- | :- | :- | :- |
| baseline | 0 | 2.715705 | 1.221284 | 1.494421 | 174.475000 | 0.000000 | 0.525000 |
| baseline | 1 | 2.528994 | 1.030149 | 1.498846 | 175.691464 | 0.000000 | 0.000000 |
| baseline | 2 | 2.530907 | 1.030445 | 1.500462 | 176.368256 | 0.000000 | 0.000000 |
| baseline | 3 | 2.532035 | 1.029375 | 1.502660 | 177.079105 | 0.000000 | 0.000000 |
| baseline | 4 | 2.531181 | 1.030982 | 1.500200 | 177.787176 | 0.000000 | 0.000000 |
| baseline | 5 | 2.535500 | 1.030196 | 1.505304 | 178.479463 | 0.000000 | 0.000000 |
| baseline | 6 | 2.545215 | 1.029551 | 1.515663 | 179.168367 | 0.000000 | 0.000000 |
| baseline | 7 | 2.559903 | 1.031002 | 1.528901 | 179.880603 | 0.000000 | 0.000000 |
| baseline | 8 | 2.570060 | 1.025108 | 1.544952 | 180.585545 | 0.000000 | 0.000000 |
| baseline | 9 | 2.585083 | 1.025701 | 1.559381 | 181.325673 | 0.000000 | 0.000000 |
| severely_adverse | 0 | 7.822667 | 3.190376 | 4.632291 | 174.475000 | 0.000000 | 0.525000 |
| severely_adverse | 1 | 8.272023 | 3.949624 | 4.322399 | 174.606250 | 0.000000 | 0.000000 |
| severely_adverse | 2 | 8.620501 | 7.500903 | 1.119598 | 29.771232 | 144.066750 | 0.000000 |
| severely_adverse | 3 | 8.610059 | 8.610059 | 0.000000 | 0.000000 | 173.307777 | 0.000000 |
| severely_adverse | 4 | 8.245447 | 8.245447 | 0.000000 | 0.000000 | 172.935165 | 0.000000 |
| severely_adverse | 5 | 7.635568 | 7.635568 | 0.000000 | 0.000000 | 172.762230 | 0.000000 |
| severely_adverse | 6 | 6.848456 | 6.848456 | 0.000000 | 0.000000 | 172.710401 | 0.000000 |
| severely_adverse | 7 | 6.084015 | 6.084015 | 0.000000 | 0.000000 | 172.796756 | 0.000000 |
| severely_adverse | 8 | 5.385622 | 5.385622 | 0.000000 | 0.000000 | 172.969553 | 0.000000 |
| severely_adverse | 9 | 4.751834 | 4.751834 | 0.000000 | 0.000000 | 173.229007 | 0.000000 |


## Historical proposal comparison

| framework | credit_rwa | operational_rwa | market_rwa | cva_rwa | total_rwa | floor_adjustment_rwa | dual_stack_adjustment_rwa | cet1_ratio | rwa_change | required_cet1_ratio | required_cet1_bn | incremental_required_cet1_bn | cet1_to_preserve_opening_ratio_bn | capital_headroom_bn | expanded_raw_rwa | us_market_floor_base | proposed_standardized_rwa | status |
| :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- | :- |
| current_standardized_proxy | 173.863669 | 0.000000 | 4.000000 | 0.000000 | 177.863669 | 0.000000 | 0.000000 | 0.118068 | 0.000000 | 0.084617 | 15.050250 | 0.000000 | 0.000000 | 5.949750 | 197.102397 | 198.102397 | 180.863669 | Simplified current classification and market placeholder |
| requested_illustrative_output_floor | 171.662779 | 17.439618 | 6.000000 | 2.000000 | 197.102397 | 0.000000 | 0.000000 | 0.106544 | 19.238728 | 0.084617 | 16.678170 | 1.627919 | 2.271477 | 4.321830 | 197.102397 | 198.102397 | 180.863669 | stylized/unverified US application: floor base is current RWA, not revised Basel standardized RWA |
| historical_2023_us_dual_stack_proxy | 171.662779 | 17.439618 | 6.000000 | 2.000000 | 197.102397 | 0.000000 | 0.000000 | 0.106544 | 19.238728 | 0.084617 | 16.678170 | 1.627919 | 2.271477 | 4.321830 | 197.102397 | 198.102397 | 180.863669 | Verified dual-stack structure; proxy credit and market inputs; ILM assumed one |


## Accounting residuals

| scenario | max_cet1_residual_bn | max_allowance_residual_bn | max_loan_balance_residual_bn | max_ifrs_reconciliation_residual_bn |
| :- | :- | :- | :- | :- |
| baseline | 3.219647e-15 | 0.000000e+00 | 7.105427e-15 | 2.220446e-16 |
| severely_adverse | 9.992007e-16 | 1.942890e-16 | 7.105427e-15 | 8.881784e-16 |


Historical proposal only. Mortgage and CRE proxy weights and GSIB denominators are stylized/unverified. Market and CVA inputs are placeholders. TLAC and debt checks are hypothetical and not applicable to this synthetic bank.
