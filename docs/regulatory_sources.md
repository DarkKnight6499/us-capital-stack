# Primary-source verification register

Sources were read during construction and rechecked against the linked primary text during the continuation audit. This register identifies the parameter's status separately from the synthetic exposure classification. The Endgame comparison is a historical proposal experiment, with no claim about final implementation of later rulemaking. HTML rule paragraphs and Basel Framework paragraphs were inspected directly; scenario headers were checked against the Federal Reserve domestic table.

| Parameter | Verified section and treatment | Source |
| :- | :- | :- |
| SCB | Starting ratio less minimum projected ratio, dividends in quarters four through seven divided by RWA at the minimum, floor 0.025 | [12 CFR 225.8(f)(2)](https://www.law.cornell.edu/cfr/text/12/225.8#f_2) |
| Stress capital actions | No common dividends, no repurchases; retain instrument obligations | [12 CFR 252.44(c)](https://www.law.cornell.edu/cfr/text/12/252.44#c) |
| CET1 minimum | 0.045 | [12 CFR 217.10(a)(1)(i)](https://www.law.cornell.edu/cfr/text/12/217.10#a) |
| Current credit proxies | Corporate 1.00, qualifying mortgage 0.50, GSE 0.20, cash 0.00; classifications assumed | [12 CFR 217.32(a), (c), (f), (g), (l)](https://www.law.cornell.edu/cfr/text/12/217.32) |
| Historical expanded credit | Public investment-grade corporate 0.65, other corporate 1.00, regulatory retail non-transactor 0.85, transactor 0.55 | [2023 proposal, proposed section 111(h)(1), (g)(1)](https://www.federalregister.gov/documents/2023/09/18/2023-19200/regulatory-capital-rule-large-banking-organizations-and-banking-organizations-with-significant) |
| Historical operational capital | BIC marginal rates 0.12, 0.15, 0.18 at BI bands 1 and 30 USD billion; RWA is 12.5 times capital; ILM minimum one | [2023 proposal, proposed section 150(a)-(e)](https://www.federalregister.gov/documents/2023/09/18/2023-19200/regulatory-capital-rule-large-banking-organizations-and-banking-organizations-with-significant) |
| Historical BI | Interest component cap 0.0225 of earning assets; add dividend, services, and financial components | [2023 proposal, proposed section 150(d)](https://www.federalregister.gov/documents/2023/09/18/2023-19200/regulatory-capital-rule-large-banking-organizations-and-banking-organizations-with-significant) |
| US structure | Lower capital ratios across two stacks; expanded floor uses standardized market risk with expanded other components | [2023 proposal, section III.A and III.A.1](https://www.federalregister.gov/documents/2023/09/18/2023-19200/regulatory-capital-rule-large-banking-organizations-and-banking-organizations-with-significant) |
| Basel output floor | Factor 0.725, fully phased in; base uses revised standardized approaches | [Basel Framework RBC20.4 and RBC20.11](https://www.bis.org/committees/bcbs/basel-framework/standard/rbc?allChapters=true) |
| Method 1 score | Twelve indicators, five categories, weighted share times 10000, substitutability cap 100 bp | [12 CFR 217.404(a)-(b), Table 1](https://www.law.cornell.edu/cfr/text/12/217.404) |
| Method 1 buckets | Cutoffs 130, 230, 330, 430, 530, 630 bp; surcharges 0.01, 0.015, 0.02, 0.025, 0.035, 0.045 with higher buckets | [12 CFR 217.403(b)](https://www.law.cornell.edu/cfr/text/12/217.403#b) |
| US TLAC minimum | Greater of 0.18 times RWA and 0.075 times leverage exposure; eligible debt recognition differs from LTD | [12 CFR 252.63(a)-(b)](https://www.law.cornell.edu/cfr/text/12/252.63) |
| US LTD minimum | Greater of (0.06 plus GSIB surcharge) times RWA and (0.025 plus leverage buffer) times leverage exposure | [12 CFR 252.62(a)](https://www.law.cornell.edu/cfr/text/12/252.62#a) |
| Debt maturity | LTD recognition: full at 730 days or more, half at 365 to 729 days, zero below 365 days | [12 CFR 252.62(b)](https://www.law.cornell.edu/cfr/text/12/252.62#b) |
| Leverage buffer input | Half the Method 1 surcharge for the holding company; caller supplies effective surcharge inputs | [12 CFR 217.11(a)(2)(v)](https://www.law.cornell.edu/cfr/text/12/217.11) |

Mortgage and CRE expanded proxy weights, the requested floor using current US RWA, global GSIB denominators, generic asset classification, and the relative-PD accounting threshold are **stylized/unverified**. ILM equal to one is a deliberate assumption. Market and CVA RWA are placeholders. No current official scenario observations are included in the seeded examples.
