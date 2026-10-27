# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Evaluate bounded scalar observations without exposing business values."""

import math
from bisect import bisect_right
from collections import Counter
from statistics import fmean, pstdev

from datakeel.core.dq_models import DqMetrics, DqRule
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


def _numbers(values: tuple[Scalar, ...]) -> tuple[float, ...]:
    return tuple(
        float(value)
        for value in values
        if isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)
    )


def observation(values: tuple[Scalar, ...], edges: tuple[float, ...]) -> DqMetrics:
    """Produce non-sensitive numeric aggregates and fixed-bin histogram frequencies."""
    numbers = _numbers(values)
    histogram = [0.0] * (len(edges) + 1)
    for number in numbers:
        histogram[bisect_right(edges, number)] += 1 / len(numbers)
    return DqMetrics(
        row_count=len(values),
        mean=stable_mean(numbers) if numbers else None,
        stddev=pstdev(numbers) if numbers else None,
        null_rate=sum(value is None for value in values) / len(values) if values else 0,
        histogram=tuple(histogram),
        bin_edges=edges,
    )


def decile_edges(values: tuple[Scalar, ...]) -> tuple[float, ...]:
    """Derive distinct decile cut points so adaptive PSI bins follow the column's scale."""
    numbers = sorted(_numbers(values))
    if not numbers:
        return ()
    return tuple(sorted({numbers[len(numbers) * decile // 10] for decile in range(1, 10)}))


def stable_mean(values: tuple[float, ...]) -> float:
    """Scale finite inputs before summation to avoid intermediate floating-point overflow."""
    scale = max((abs(value) for value in values), default=0.0)
    return fmean(value / scale for value in values) * scale if scale else 0.0


def violating_rows(
    rule: DqRule, values: tuple[Scalar, ...], reference: tuple[Scalar, ...] = ()
) -> tuple[int, ...]:
    """Identify one-based violating row ordinals using explicit NULL semantics."""
    counts: Counter[Scalar] = Counter(values)
    allowed = set(reference or rule.params.values)
    return tuple(
        index for index, value in enumerate(values, 1) if _violates(rule, value, counts, allowed)
    )


def _violates(rule: DqRule, value: Scalar, counts: Counter[Scalar], allowed: set[Scalar]) -> bool:
    if rule.kind == "not_null":
        return value is None
    if value is None:
        return False
    if rule.kind == "unique":
        return counts[value] > 1
    if rule.kind in {"accepted_values", "referential_integrity"}:
        return value not in allowed
    return rule.kind == "range" and _outside_range(rule, value)


def _outside_range(rule: DqRule, value: Scalar) -> bool:
    if not isinstance(value, int | float) or isinstance(value, bool) or not math.isfinite(value):
        return True
    return (rule.params.minimum is not None and value < rule.params.minimum) or (
        rule.params.maximum is not None and value > rule.params.maximum
    )


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
