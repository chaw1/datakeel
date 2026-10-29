# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Balance class prevalence with deterministic whole-group transfers between partitions."""

from __future__ import annotations

from collections import Counter
from itertools import combinations
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from numpy.typing import NDArray

    from datakeel.core.training_models import SplitName, SplitRequest, TrainingSample

SPLITS: tuple[SplitName, ...] = ("train", "val", "test")
COUNT_TOLERANCE = 1
PREVALENCE_TOLERANCE = 0.02
MIN_CATEGORY = 50
EPSILON = 1e-9
EXCHANGE_BLOCK = 64


def proportion_cost(
    samples: tuple[TrainingSample, ...],
    result: dict[int, SplitName],
    request: SplitRequest,
) -> tuple[float, float, float]:
    """Score declared count and prevalence limits before overall set-ratio proximity."""
    totals: Counter[str | None] = Counter(label for sample in samples for label in sample.labels)
    totals[None] = sum(not sample.labels for sample in samples)
    count_cost, prevalence_cost, ratio_cost = 0.0, 0.0, 0.0
    for split in SPLITS:
        selected = [sample for index, sample in enumerate(samples) if result[index] == split]
        counts: Counter[str | None] = Counter(
            label for sample in selected for label in sample.labels
        )
        counts[None] = sum(not sample.labels for sample in selected)
        ratio = getattr(request.ratios, split)
        ratio_cost += (len(selected) - len(samples) * ratio) ** 2
        for label, total in totals.items():
            count_cost += max(abs(counts[label] - total * ratio) - 1 - EPSILON, 0) ** 2
            if label is not None and total >= MIN_CATEGORY and selected:
                difference = abs(counts[label] / len(selected) - total / len(samples))
                prevalence_cost += max(difference - PREVALENCE_TOLERANCE - EPSILON, 0) ** 2
    return round(count_cost, 12), round(prevalence_cost, 12), round(ratio_cost, 12)


def _row_costs(
    counts: NDArray[np.float64],
    sizes: NDArray[np.float64],
    targets: NDArray[np.float64],
    prevalence: NDArray[np.float64],
    checked: NDArray[np.bool_],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    count_error = np.maximum(np.abs(counts - targets) - COUNT_TOLERANCE - EPSILON, 0)
    proportions = counts / np.maximum(sizes, 1)[:, None]
    error = np.maximum(np.abs(proportions - prevalence) - PREVALENCE_TOLERANCE - EPSILON, 0)
    error = np.where(checked[None, :] & (sizes > 0)[:, None], error, 0)
    return np.square(count_error).sum(axis=1), np.square(error).sum(axis=1)


def _best_transfer(
    labels: NDArray[np.float64],
    group_sizes: NDArray[np.float64],
    assignments: NDArray[np.int64],
    counts: NDArray[np.float64],
    sizes: NDArray[np.float64],
    ratios: NDArray[np.float64],
) -> tuple[int, int] | None:
    totals = labels.sum(axis=0)
    population = float(group_sizes.sum())
    prevalence = totals / population
    checked = totals >= MIN_CATEGORY
    checked[0] = False
    targets = ratios[:, None] * totals[None, :]
    old_count, old_prevalence = _row_costs(counts, sizes, targets, prevalence, checked)
    old_ratio: NDArray[np.float64] = np.square(sizes - population * ratios)
    baseline = tuple(
        round(float(value.sum()), 12) for value in (old_count, old_prevalence, old_ratio)
    )
    source = assignments
    source_sizes = sizes[source] - group_sizes
    a, b = _row_costs(counts[source] - labels, source_sizes, targets[source], prevalence, checked)
    c = np.square(source_sizes - population * ratios[source])
    best: tuple[tuple[float, ...], int, int] | None = None
    for destination in range(3):
        if ratios[destination] == 0:
            continue
        destination_sizes = sizes[destination] + group_sizes
        d, e = _row_costs(
            counts[destination] + labels,
            destination_sizes,
            np.broadcast_to(targets[destination], labels.shape),
            prevalence,
            checked,
        )
        f = np.square(destination_sizes - population * ratios[destination])
        objectives: list[NDArray[np.float64]] = [
            np.round(old.sum() - old[source] - old[destination] + left + right, 12)
            for old, left, right in ((old_count, a, d), (old_prevalence, b, e), (old_ratio, c, f))
        ]
        eligible = np.flatnonzero(source != destination)
        if not eligible.size:
            continue
        order = np.lexsort(tuple(objective[eligible] for objective in reversed(objectives)))
        group = int(eligible[int(order[0])])
        cost = tuple(float(objective[group]) for objective in objectives)
        if cost < baseline and (best is None or cost < best[0]):
            best = cost, group, destination
    return None if best is None else (best[1], best[2])


def _best_exchange(
    labels: NDArray[np.float64],
    group_sizes: NDArray[np.float64],
    assignments: NDArray[np.int64],
    counts: NDArray[np.float64],
    sizes: NDArray[np.float64],
    ratios: NDArray[np.float64],
) -> tuple[int, int] | None:
    totals, population = labels.sum(axis=0), float(group_sizes.sum())
    prevalence = totals / population
    checked = totals >= MIN_CATEGORY
    checked[0] = False
    targets = ratios[:, None] * totals[None, :]
    original = _row_costs(counts, sizes, targets, prevalence, checked)
    old_ratio: NDArray[np.float64] = np.square(sizes - population * ratios)
    baseline = tuple(round(float(value.sum()), 12) for value in (*original, old_ratio))
    if baseline[0] == 0 and baseline[1] == 0:
        return None
    best: tuple[tuple[float, ...], int, int] | None = None
    for a, b in combinations(range(3), 2):
        left, right = np.flatnonzero(assignments == a), np.flatnonzero(assignments == b)
        for offset in range(0, len(left), EXCHANGE_BLOCK):
            lblock = left[offset : offset + EXCHANGE_BLOCK]
            for start in range(0, len(right), EXCHANGE_BLOCK):
                rblock = right[start : start + EXCHANGE_BLOCK]
                change = labels[rblock][None, :, :] - labels[lblock][:, None, :]
                size_change = group_sizes[rblock][None, :] - group_sizes[lblock][:, None]
                shape = (-1, labels.shape[1])
                acounts, bcounts = (
                    (counts[a] + change).reshape(shape),
                    (counts[b] - change).reshape(shape),
                )
                asizes, bsizes = (sizes[a] + size_change).ravel(), (sizes[b] - size_change).ravel()
                acost = _row_costs(
                    acounts, asizes, np.broadcast_to(targets[a], acounts.shape), prevalence, checked
                )
                bcost = _row_costs(
                    bcounts, bsizes, np.broadcast_to(targets[b], bcounts.shape), prevalence, checked
                )
                ratio: NDArray[np.float64] = np.square(asizes - population * ratios[a]) + np.square(
                    bsizes - population * ratios[b]
                )
                objectives: list[NDArray[np.float64]] = [
                    np.round(old.sum() - old[a] - old[b] + first + second, 12)
                    for old, first, second in zip(original, acost, bcost, strict=True)
                ]
                ratio_objective = old_ratio.sum() - old_ratio[a] - old_ratio[b] + ratio
                np.round(ratio_objective, 12, out=ratio_objective)
                objectives.append(ratio_objective)
                order = np.lexsort(tuple(reversed(objectives)))
                chosen = int(order[0])
                cost = tuple(float(value[chosen]) for value in objectives)
                row, column = divmod(chosen, len(rblock))
                if cost < baseline and (best is None or cost < best[0]):
                    best = cost, int(lblock[row]), int(rblock[column])
    return None if best is None else (best[1], best[2])


def balance_proportions(
    samples: tuple[TrainingSample, ...],
    groups: list[list[int]],
    result: dict[int, SplitName],
    request: SplitRequest,
) -> dict[int, SplitName]:
    """Prioritize count and prevalence limits, allowing set totals to vary when necessary."""
    if not samples or not request.stratify:
        return result
    categories = sorted({label for sample in samples for label in sample.labels})
    labels = np.asarray(
        [
            [
                sum(not samples[index].labels for index in group),
                *(sum(label in samples[index].labels for index in group) for label in categories),
            ]
            for group in groups
        ],
        dtype=np.float64,
    )
    assignments = np.asarray([SPLITS.index(result[group[0]]) for group in groups], dtype=np.int64)
    group_sizes = np.asarray([len(group) for group in groups], dtype=np.float64)
    counts = np.asarray([labels[assignments == index].sum(axis=0) for index in range(3)])
    sizes = np.asarray([group_sizes[assignments == index].sum() for index in range(3)])
    ratios = np.asarray([request.ratios.train, request.ratios.val, request.ratios.test])
    while True:
        transfer = _best_transfer(labels, group_sizes, assignments, counts, sizes, ratios)
        if transfer is not None:
            group, destination = transfer
            source = int(assignments[group])
            counts[source] -= labels[group]
            counts[destination] += labels[group]
            sizes[source] -= group_sizes[group]
            sizes[destination] += group_sizes[group]
            assignments[group] = destination
            continue
        exchange = _best_exchange(labels, group_sizes, assignments, counts, sizes, ratios)
        if exchange is None:
            break
        left, right = exchange
        a, b = int(assignments[left]), int(assignments[right])
        counts[a] += labels[right] - labels[left]
        counts[b] += labels[left] - labels[right]
        sizes[a] += group_sizes[right] - group_sizes[left]
        sizes[b] += group_sizes[left] - group_sizes[right]
        assignments[left], assignments[right] = b, a
    for group, indices in enumerate(groups):
        for index in indices:
            result[index] = SPLITS[int(assignments[group])]
    return result
