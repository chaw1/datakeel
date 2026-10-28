# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Independent statistical signal rules with explicit source-coordinate evidence."""

from itertools import pairwise
from math import sqrt
from statistics import median

from datakeel.core.models import Record
from datakeel.operators.timeseries.common import TimePoint
from datakeel.operators.timeseries.models import AnomalyParams, ColumnRange, SeriesIssue

MIN_ROBUST_POINTS = 3


class SignalPoint(TimePoint):
    """Attach one finite numeric observation to its original timestamp and row."""

    value: float


def _issue(
    rule: str,
    column: str,
    group: list[SignalPoint],
    threshold: float,
    observed: float,
    detail: str,
) -> SeriesIssue:
    return SeriesIssue(
        rule=rule,
        column=column,
        device=group[0].device,
        rows=tuple(point.row for point in group),
        start_ms=group[0].milliseconds,
        end_ms=group[-1].milliseconds,
        threshold=threshold,
        window=len(group),
        observed=observed,
        detail=detail,
        recommendation="Inspect the original sensor readings and verify calibration before repair",
    )


def stuck_issues(group: list[SignalPoint], column: str, minimum: int) -> list[SeriesIssue]:
    """Locate maximal runs of exactly equal values without tolerance-based guessing."""
    issues: list[SeriesIssue] = []
    start = 0
    for end in range(1, len(group) + 1):
        if end < len(group) and group[end].value == group[start].value:
            continue
        run = group[start:end]
        if len(run) >= minimum:
            issues.append(
                _issue(
                    "stuck_value",
                    column,
                    run,
                    float(minimum),
                    float(len(run)),
                    "Consecutive readings are exactly unchanged",
                )
            )
        start = end
    return issues


def range_issues(group: list[SignalPoint], column: str, bounds: ColumnRange) -> list[SeriesIssue]:
    """Check the caller's inclusive physical bounds without inferring a range."""
    issues: list[SeriesIssue] = []
    for point in group:
        threshold = None
        if bounds.minimum is not None and point.value < bounds.minimum:
            threshold = bounds.minimum
        if bounds.maximum is not None and point.value > bounds.maximum:
            threshold = bounds.maximum
        if threshold is not None:
            issues.append(
                _issue(
                    "out_of_range",
                    column,
                    [point],
                    threshold,
                    point.value,
                    "Reading exceeds a declared physical bound",
                )
            )
    return issues


def jump_issues(group: list[SignalPoint], column: str, threshold: float) -> list[SeriesIssue]:
    """Check consecutive absolute differences against an explicit engineering threshold."""
    return [
        _issue(
            "jump",
            column,
            [before, after],
            threshold,
            abs(after.value - before.value),
            "Consecutive readings exceed the declared absolute jump threshold",
        )
        for before, after in pairwise(group)
        if abs(after.value - before.value) > threshold
    ]


class _Baseline(Record):
    """Keep robust reference scales independent from identified stuck intervals."""

    global_mad: float
    noise_mad: float


def _baseline(
    group: list[SignalPoint], excluded: frozenset[int], *, noise_floor: bool
) -> _Baseline:
    values = [point.value for point in group if point.row not in excluded]
    center = median(values)
    differences = [
        after.value - before.value
        for before, after in pairwise(group)
        if before.row not in excluded and after.row not in excluded
    ]
    difference_center = median(differences) if differences else 0.0
    noise = (
        median(abs(value - difference_center) for value in differences) / sqrt(2)
        if differences and noise_floor
        else 0.0
    )
    return _Baseline(global_mad=median(abs(value - center) for value in values), noise_mad=noise)


def _scale(local_mad: float, baseline: _Baseline, center: float) -> tuple[float, str]:
    scale = max(local_mad, baseline.noise_mad)
    if scale:
        return scale, "max(local_mad, noise_mad)"
    if baseline.global_mad:
        return baseline.global_mad, "global_mad fallback"
    return max(abs(center) * 0.01, 1e-9), "one-percent baseline fallback"


def robust_issues(
    group: list[SignalPoint],
    column: str,
    params: AnomalyParams,
    excluded: frozenset[int] = frozenset(),
) -> list[SeriesIssue]:
    """Apply Hampel windows using independent adjacent-difference noise evidence.

    Stuck intervals are excluded from targets and references. The noise-MAD
    floor is MAD(delta - median(delta)) / sqrt(2), using only adjacent eligible
    pairs, so a linear slope does not inflate it. Each reference needs at least
    three eligible readings. A zero final scale retains the prior fallback.
    """
    if sum(point.row not in excluded for point in group) < MIN_ROBUST_POINTS:
        return []
    baseline = _baseline(group, excluded, noise_floor=params.noise_floor)
    issues: list[SeriesIssue] = []
    radius = params.window // 2
    for index, point in enumerate(group):
        if point.row in excluded:
            continue
        window = group[max(0, index - radius) : index + radius + 1]
        reference = [item.value for item in window if item.row not in excluded]
        if len(reference) < MIN_ROBUST_POINTS:
            continue
        center = median(reference)
        mad = median(abs(value - center) for value in reference)
        scale, basis = _scale(mad, baseline, center)
        score = 0.6744897501960817 * abs(point.value - center) / scale
        if score > params.robust_z_threshold:
            issue = _issue(
                "robust_z",
                column,
                [point],
                params.robust_z_threshold,
                score,
                f"Centered median={center:.6g}; local_mad={mad:.6g}; "
                f"noise_mad={baseline.noise_mad:.6g}; noise_floor={params.noise_floor}; "
                f"scale={scale:.6g} via {basis}; excluded_stuck={len(window) - len(reference)}",
            )
            issues.append(issue.model_copy(update={"window": len(reference)}))
    return issues
