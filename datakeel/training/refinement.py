# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Improve iterative label balance through deterministic size-preserving group swaps."""

from __future__ import annotations

from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from collections.abc import Iterator

    from numpy.typing import NDArray

    from datakeel.core.training_models import SplitName, SplitRequest, TrainingSample

SPLITS: tuple[SplitName, ...] = ("train", "val", "test")
EPSILON = 1e-9
MAX_NEUTRAL_TRIALS = 256
LEFT_BLOCK = 128
RIGHT_BLOCK = 512


def _swap_scores(
    labels: NDArray[np.float64],
    assignments: NDArray[np.int64],
    sizes: NDArray[np.int64],
    residuals: NDArray[np.float64],
) -> Iterator[tuple[NDArray[np.int64], NDArray[np.int64], NDArray[np.float64]]]:
    for left_split, right_split in combinations(range(3), 2):
        left = np.flatnonzero(assignments == left_split)
        right = np.flatnonzero(assignments == right_split)
        if not left.size or not right.size:
            continue
        difference = residuals[left_split] - residuals[right_split]
        for offset in range(0, len(left), LEFT_BLOCK):
            left_block = left[offset : offset + LEFT_BLOCK]
            a = labels[left_block]
            for start in range(0, len(right), RIGHT_BLOCK):
                right_block = right[start : start + RIGHT_BLOCK]
                b = labels[right_block]
                gains = 2 * (
                    (a @ difference - np.sum(a * a, axis=1))[:, None]
                    - (b @ difference + np.sum(b * b, axis=1))[None, :]
                    + 2 * (a @ b.T)
                )
                gains = np.where(
                    sizes[left_block, None] == sizes[right_block][None, :], gains, -np.inf
                )
                yield left_block, right_block, gains


def _best_swap(
    labels: NDArray[np.float64],
    assignments: NDArray[np.int64],
    sizes: NDArray[np.int64],
    residuals: NDArray[np.float64],
) -> tuple[int, int, float] | None:
    best: tuple[int, int, float] | None = None
    for left, right, gains in _swap_scores(labels, assignments, sizes, residuals):
        offset = int(np.argmax(gains))
        row, column = divmod(offset, len(right))
        gain = float(gains[row, column])
        if gain > EPSILON and (best is None or gain > best[2] + EPSILON):
            best = int(left[row]), int(right[column]), gain
    return best


def _escape_swap(
    labels: NDArray[np.float64],
    assignments: NDArray[np.int64],
    sizes: NDArray[np.int64],
    residuals: NDArray[np.float64],
) -> tuple[int, int, float] | None:
    trials = 0
    for left, right, gains in _swap_scores(labels, assignments, sizes, residuals):
        for offset in np.flatnonzero(np.abs(gains) < EPSILON):
            trials += 1
            if trials > MAX_NEUTRAL_TRIALS:
                return None
            row, column = divmod(int(offset), len(right))
            a, b = int(left[row]), int(right[column])
            before, after = int(assignments[a]), int(assignments[b])
            change = labels[b] - labels[a]
            trial = residuals.copy()
            trial[before] += change
            trial[after] -= change
            assignments[a], assignments[b] = after, before
            improvement = _best_swap(labels, assignments, sizes, trial)
            assignments[a], assignments[b] = before, after
            if improvement is not None:
                return a, b, 0
    return None


def _lower_bound(targets: NDArray[np.float64]) -> float:
    quotas = np.floor(targets)
    for column in range(targets.shape[1]):
        remainder = round(float(targets[:, column].sum() - quotas[:, column].sum()))
        priority = np.argsort(-(targets[:, column] - quotas[:, column]), kind="stable")
        quotas[priority[:remainder], column] += 1
    return float(np.square(quotas - targets).sum())


def refine_assignments(
    samples: tuple[TrainingSample, ...],
    groups: list[list[int]],
    result: dict[int, SplitName],
    request: SplitRequest,
) -> dict[int, SplitName]:
    """Reduce global squared category residuals without changing sizes or breaking groups."""
    categories = sorted({label for sample in samples for label in sample.labels})
    if not request.stratify or not categories or not groups:
        return result
    labels = np.asarray(
        [
            [sum(label in samples[index].labels for index in group) for label in categories]
            for group in groups
        ],
        dtype=np.float64,
    )
    assignments = np.asarray([SPLITS.index(result[group[0]]) for group in groups], dtype=np.int64)
    sizes = np.asarray([len(group) for group in groups], dtype=np.int64)
    counts = np.asarray([labels[assignments == index].sum(axis=0) for index in range(3)])
    ratios = np.asarray([request.ratios.train, request.ratios.val, request.ratios.test])
    targets = ratios[:, None] * labels.sum(axis=0)[None, :]
    lower_bound = _lower_bound(targets)
    while True:
        residuals = counts - targets
        swap = _best_swap(labels, assignments, sizes, residuals)
        if swap is None and float(np.square(residuals).sum()) > lower_bound + EPSILON:
            swap = _escape_swap(labels, assignments, sizes, residuals)
        if swap is None:
            break
        left, right, _ = swap
        left_split, right_split = int(assignments[left]), int(assignments[right])
        change = labels[right] - labels[left]
        counts[left_split] += change
        counts[right_split] -= change
        assignments[left], assignments[right] = right_split, left_split
    for index, group in enumerate(groups):
        for sample in group:
            result[sample] = SPLITS[int(assignments[index])]
    return result
