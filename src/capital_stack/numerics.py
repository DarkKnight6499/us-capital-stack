"""Small, dependency-free probability and root-solving utilities."""

import math
from collections.abc import Callable


def logistic(value: float) -> float:
    """Evaluate a logistic probability without overflow."""
    if value >= 0:
        exp_value = math.exp(-value)
        return 1.0 - exp_value / (1.0 + exp_value)
    exp_value = math.exp(value)
    return exp_value / (1.0 + exp_value)


def logit(probability: float) -> float:
    """Invert a strictly interior probability."""
    if not 0 < probability < 1:
        raise ValueError("probability must be strictly between zero and one")
    return math.log(probability) - math.log1p(-probability)


def bisect_root(function: Callable[[float], float], lower: float, upper: float,
                tolerance: float = 1e-12, max_iterations: int = 200) -> float:
    """Find a root of a continuous bracketed function."""
    if not (math.isfinite(lower) and math.isfinite(upper) and lower < upper):
        raise ValueError("invalid root bracket")
    if not math.isfinite(tolerance) or tolerance <= 0 or isinstance(max_iterations, bool) or not isinstance(max_iterations, int) or max_iterations < 1:
        raise ValueError("invalid solver settings")
    low_value, high_value = function(lower), function(upper)
    if not math.isfinite(low_value) or not math.isfinite(high_value):
        raise ValueError("nonfinite function value")
    if low_value == 0:
        return lower
    if high_value == 0:
        return upper
    if (low_value > 0) == (high_value > 0):
        raise ValueError("root is not bracketed")
    for _ in range(max_iterations):
        middle = (lower + upper) / 2
        value = function(middle)
        if not math.isfinite(value):
            raise ValueError("nonfinite function value")
        if abs(value) <= tolerance or (upper - lower) / 2 <= tolerance:
            return middle
        if (value > 0) == (low_value > 0):
            lower, low_value = middle, value
        else:
            upper = middle
    raise RuntimeError("root solver did not converge")


def annual_to_quarterly(probability: float) -> float:
    """Convert an annual conditional PD to a constant quarterly hazard."""
    if not math.isfinite(probability) or not 0 <= probability <= 1:
        raise ValueError("PD must lie between zero and one")
    return 1.0 if probability == 1 else -math.expm1(math.log1p(-probability) / 4)
