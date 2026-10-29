# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate bounded scalar observations without exposing business values."""

import math
from statistics import fmean

from datakeel.core.dq_models import DqRule
from datakeel.core.errors import ExecutionError
from datakeel.core.metric_models import Scalar


def validate_distribution_values(rule: DqRule, values: tuple[Scalar, ...]) -> None:
    """Reject malformed numeric distributions before collecting any baseline observation."""
    if rule.kind != "distribution_drift" or rule.params.statistic == "null_rate":
        return
    if any(
        value is not None
        and (
            not isinstance(value, int | float)
            or isinstance(value, bool)
            or not math.isfinite(value)
        )
        for value in values
    ):
        msg = "Numeric distribution requires finite numeric or NULL values in every row"
        raise ExecutionError(msg)


def stable_mean(values: tuple[float, ...]) -> float:
    """Scale finite inputs before summation to avoid intermediate floating-point overflow."""
    scale = max((abs(value) for value in values), default=0.0)
    return fmean(value / scale for value in values) * scale if scale else 0.0


def relative_change(actual: float, baseline: float) -> float:
    """Use symmetric absolute relative deviation with a finite zero-baseline result."""
    change = abs(actual / baseline - 1) if baseline else float(actual != 0)
    if not math.isfinite(change):
        msg = "Numeric quality drift exceeds finite representation"
        raise ExecutionError(msg)
    return change


def population_stability(actual: tuple[float, ...], baseline: tuple[float, ...]) -> float:
    """Compute PSI with a fixed epsilon so empty bins remain finite and deterministic."""
    epsilon = 0.0001
    return sum(
        (max(current, epsilon) - max(previous, epsilon))
        * math.log(max(current, epsilon) / max(previous, epsilon))
        for current, previous in zip(actual, baseline, strict=True)
    )
