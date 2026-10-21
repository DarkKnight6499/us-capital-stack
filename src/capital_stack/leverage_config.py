"""Leverage configuration, schemas, and explicitly illustrative synthetic inputs."""

from dataclasses import dataclass

# Config: rule constants, column names, and illustrative example parameters.
MINIMUM_SLR = .03
MINIMUM_LEVERAGE = .04
COUNTERPARTY_FACTOR = 1.4
PFE_FLOOR = .05
PFE_EXPONENT_SCALE = 1.9
CCF_FLOOR = .10
SUBSIDIARY_BUFFER_CAP = .01
METHOD1_BUFFER_SHARE = .5
PAYOUT_BANDS = ((1., None), (.75, .60), (.50, .40), (.25, .20))
BOUNDARY_TOLERANCE = 1e-12
DATE = "date"
MONTH = "month_end"
ASSETS = "on_balance_assets"
SALES = "securities_sales_treatment"
DEDUCTIONS = "tier1_deductions"
RECEIVED_SECURITIES = "securities_received_unrehypothecated"
DERIVATIVE_ASSETS = "derivative_fair_value_assets"
CENTRAL_BANK = "qualifying_central_bank_deposits"
CUSTODIAL_DEPOSITS = "linked_fiduciary_custodial_deposits"
NETTING_SET = "netting_set_id"
COUNTERPARTY_TYPE = "counterparty_type"
END_USER = "is_commercial_end_user"
V = "fair_value_V"
ADDON = "aggregated_addon_A"
CVM_RECEIVED = "cvm_received"
CVM_POSTED = "cvm_posted"
CVM_ELIGIBLE = "cvm_eligible"
MULTIPLIER = "pfe_multiplier"
FACTOR = "counterparty_factor"
REFERENCE = "reference_id"
SOLD = "sold_effective_notional"
PURCHASED = "purchased_effective_notional"
MATCHED_HEDGE = "matched_hedge"
CET1_LOSS = "fair_value_loss_in_cet1"
COUNTERPARTY = "counterparty"
QMNA = "qmna"
REPO_NETTING_SET = "repo_netting_set_id"
E = "E_i"
C = "C_i"
GROSS_RECEIVABLE = "gross_receivable"
ON_BALANCE_RECEIVABLE = "on_balance_receivable"
NETTING_MET = "netting_criteria_met"
COMMITMENT_TYPE = "type"
MATURITY = "original_maturity_years"
NOTIONAL = "notional"
CCF = "ccf"
BASE_CCF = "base_ccf"
COMPONENT = "component"
RULE = "rule_paragraph"
AMOUNT = "amount"
QUARTER = "quarter"
SCENARIO = "scenario"
VIEW = "configuration"
TIER1 = "tier1_capital"
TLE = "total_leverage_exposure"
LEVERAGE_DENOMINATOR = "leverage_denominator"
LEVERAGE_RATIO = "tier1_leverage_ratio"
SLR = "slr"
BUFFER = "leverage_buffer"
BUFFER_REQUIREMENT = "buffer_requirement"
BUFFER_FRACTION = "buffer_to_requirement"
PAYOUT = "max_payout_ratio"
NO_LIMIT = "no_leverage_payout_limit"
MINIMUM_HEADROOM = "headroom_to_3pct"
BUFFER_HEADROOM = "headroom_to_3pct_plus_buffer"
MINIMUM_RATIO = "minimum_slr"
MINIMUM_QUARTER = "minimum_slr_quarter"
AVERAGE_ASSETS = "average_total_assets"
PROJECTED_ASSETS = "projected_total_assets"
ASSET_SCALE = "exposure_scale"
CLOSING_CET1 = "closing_cet1"
CLOSING_ALLOWANCE = "closing_allowance"
SENSITIVITY = "sensitivity"
SLR_CHANGE_BP = "slr_change_bp"
EXPOSURE_CHANGE = "exposure_change_bn"
UNCANCELABLE = "unconditionally_cancelable"
COMMITMENT = "commitment"
TRADE = "self_liquidating_trade"
TRANSACTION = "transaction_contingent"
PERFORMANCE_BOND = "performance_bond"
PERFORMANCE_LC = "performance_standby_lc"
GUARANTEE = "guarantee"
FINANCIAL_LC = "financial_standby_lc"
CCF_TABLE = {UNCANCELABLE: 0., TRADE: .20, TRANSACTION: .50,
             PERFORMANCE_BOND: .50, PERFORMANCE_LC: .50,
             GUARANTEE: 1., FINANCIAL_LC: 1.}
SHORT_COMMITMENT_CCF = .20
LONG_COMMITMENT_CCF = .50
ONE_YEAR = 1.
DAILY_AMOUNT_COLUMNS = (ASSETS, SALES, DEDUCTIONS, RECEIVED_SECURITIES,
                        DERIVATIVE_ASSETS, CENTRAL_BANK, CUSTODIAL_DEPOSITS)
DERIVATIVE_AMOUNT_COLUMNS = (V, ADDON, CVM_RECEIVED, CVM_POSTED)
PROTECTION_AMOUNT_COLUMNS = (SOLD, PURCHASED, CET1_LOSS)
REPO_AMOUNT_COLUMNS = (E, C, GROSS_RECEIVABLE, ON_BALANCE_RECEIVABLE)
DAILY_COMPONENTS = {ASSETS: 1., SALES: 1., DEDUCTIONS: -1.,
                    RECEIVED_SECURITIES: -1., DERIVATIVE_ASSETS: -1.}
CATEGORY_III = "category_iii_illustrative"
GSIB_BHC = "gsib_bhc_illustrative"
GSIB_SUBSIDIARY = "gsib_subsidiary_illustrative"
ILLUSTRATIVE_METHOD1_SURCHARGE = .02
ILLUSTRATIVE_REPO_GROWTH_BN = 10.
ILLUSTRATIVE_AS_OF = "2026-09-30"
ILLUSTRATIVE_ASSET_NOISE = .002
ILLUSTRATIVE_MONTH_SCALES = (.98, 1., 1.02)
ILLUSTRATIVE_NETTING_SETS = 10
ILLUSTRATIVE_END_USER_INTERVAL = 4
ILLUSTRATIVE_INELIGIBLE_CVM_INTERVAL = 3
ILLUSTRATIVE_FINANCIAL_COUNTERPARTY = "financial"
ILLUSTRATIVE_COMMERCIAL_COUNTERPARTY = "commercial_end_user"
ILLUSTRATIVE_V_RANGE = (-1., 2.)
ILLUSTRATIVE_ADDON_RANGE = (3., 5.)
ILLUSTRATIVE_CVM_RANGE = (0., .5)
ILLUSTRATIVE_DERIVATIVE_ASSETS = 8.
ILLUSTRATIVE_SALES = 1.5
ILLUSTRATIVE_RECEIVED_SECURITIES = .5
ILLUSTRATIVE_CENTRAL_BANK_DEPOSITS = 8.
ILLUSTRATIVE_CUSTODIAL_DEPOSITS = 6.
ILLUSTRATIVE_PROTECTION = (("reference_a", 20., 8., True, .5),
                           ("reference_b", 12., 4., False, .2),
                           ("reference_c", 8., 3., True, .3))
ILLUSTRATIVE_REPOS = (("dealer_a", "agreement_a", True, 35., 34., 35., 30., True),
                      ("dealer_a", "agreement_a", True, 25., 25.5, 25., 20., True),
                      ("dealer_b", "agreement_b", False, 20., 19., 20., 15., False),
                      ("dealer_c", "agreement_c", False, 12., 13., 12., 10., True))
ILLUSTRATIVE_COMMITMENTS = ((UNCANCELABLE, .5, 80.), (COMMITMENT, .5, 30.),
                            (TRADE, .5, 8.), (COMMITMENT, 3., 42.),
                            (PERFORMANCE_BOND, 2., 7.), (PERFORMANCE_LC, 2., 4.),
                            (GUARANTEE, 2., 9.), (FINANCIAL_LC, 2., 8.))
ILLUSTRATIVE_REPO_ID = "illustrative_matched_growth"


@dataclass(frozen=True)
class LeverageSettings:
    """The custodial eligibility switch is illustrative and defaults to false."""

    apply_counterparty_factor: bool = True
    custodial_banking_organization: bool = False

    def __post_init__(self) -> None:
        if not all(isinstance(value, bool) for value in
                   (self.apply_counterparty_factor, self.custodial_banking_organization)):
            raise ValueError("leverage switches must be boolean")
