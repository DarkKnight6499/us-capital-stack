"""Synthetic bank capital planning with explicit accounting and model assumptions."""

from .data import synthetic_bank, synthetic_scenarios
from .models import Bank, Portfolio
from .planning import CapitalPlan, run_plan
from .scenario import Scenario, load_fed_scenario, load_scenario

__all__ = ["Bank", "CapitalPlan", "Portfolio", "Scenario", "load_fed_scenario", "load_scenario", "run_plan", "synthetic_bank", "synthetic_scenarios"]
__version__ = "0.1.0"
