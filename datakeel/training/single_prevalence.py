# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Find feasible integer single-label quotas when small partitions need different totals."""

from __future__ import annotations

import hashlib
import math
from collections import defaultdict, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from datakeel.core.training_models import SplitName, SplitRequest, TrainingSample

SPLITS: tuple[SplitName, ...] = ("train", "val", "test")
EPSILON = 1e-9
MIN_CATEGORY = 50
PREVALENCE_TOLERANCE = 0.02


@dataclass(frozen=True)
class _Stratum:
    indices: tuple[int, ...]
    labelled: bool


def _bounds(
    count: int, population: int, ratio: float, size: int, *, labelled: bool
) -> tuple[int, int]:
    low, high = (
        max(0, math.ceil(count * ratio - 1 - EPSILON)),
        min(count, math.floor(count * ratio + 1 + EPSILON)),
    )
    if size == 0:
        return low, 0
    if labelled and count >= MIN_CATEGORY:
        low = max(low, math.ceil((count / population - PREVALENCE_TOLERANCE) * size - EPSILON))
        high = min(high, math.floor((count / population + PREVALENCE_TOLERANCE) * size + EPSILON))
    return low, high


def _sizes(
    strata: tuple[_Stratum, ...], population: int, ratios: tuple[float, ...]
) -> Iterator[tuple[int, int, int]]:
    allowed: list[list[int]] = []
    for ratio in ratios:
        raw = [
            _bounds(len(row.indices), population, ratio, population, labelled=False)
            for row in strata
        ]
        low, high = sum(pair[0] for pair in raw), sum(pair[1] for pair in raw)
        possibilities: list[int] = []
        for size in range(low, min(population, high) + 1):
            if ratio == 0 and size:
                continue
            limits = [
                _bounds(len(row.indices), population, ratio, size, labelled=row.labelled)
                for row in strata
            ]
            if all(a <= b for a, b in limits) and sum(a for a, _ in limits) <= size <= sum(
                b for _, b in limits
            ):
                possibilities.append(size)
        allowed.append(possibilities)
    tests = set(allowed[2])
    candidates = [
        (a, b, population - a - b)
        for a in allowed[0]
        for b in allowed[1]
        if population - a - b in tests
    ]
    yield from sorted(
        candidates,
        key=lambda sizes: (
            sum(
                (size - population * ratio) ** 2 for size, ratio in zip(sizes, ratios, strict=True)
            ),
            sizes,
        ),
    )


def _edge(graph: list[dict[int, int]], left: int, right: int, capacity: int) -> None:
    graph[left][right] = capacity
    graph[right][left] = 0


def _flow(graph: list[dict[int, int]], sink: int) -> int:
    result = 0
    while True:
        parents = {0: 0}
        queue = deque([0])
        while queue and sink not in parents:
            left = queue.popleft()
            for right, capacity in graph[left].items():
                if capacity > 0 and right not in parents:
                    parents[right] = left
                    queue.append(right)
        if sink not in parents:
            return result
        cursor, amount = sink, sum(graph[0].values())
        while cursor:
            previous = parents[cursor]
            amount = min(amount, graph[previous][cursor])
            cursor = previous
        cursor = sink
        while cursor:
            previous = parents[cursor]
            graph[previous][cursor] -= amount
            graph[cursor][previous] += amount
            cursor = previous
        result += amount


def _allocate(
    strata: tuple[_Stratum, ...],
    population: int,
    ratios: tuple[float, ...],
    sizes: tuple[int, int, int],
) -> tuple[tuple[int, ...], ...] | None:
    limits = [
        [
            _bounds(len(row.indices), population, ratio, size, labelled=row.labelled)
            for ratio, size in zip(ratios, sizes, strict=True)
        ]
        for row in strata
    ]
    if any(low > high for row in limits for low, high in row):
        return None
    supplies = [
        len(stratum.indices) - sum(low for low, _ in row)
        for stratum, row in zip(strata, limits, strict=True)
    ]
    demands = [sizes[split] - sum(row[split][0] for row in limits) for split in range(3)]
    if any(value < 0 for value in (*supplies, *demands)) or sum(supplies) != sum(demands):
        return None
    sink = len(strata) + 4
    graph: list[dict[int, int]] = [{} for _ in range(sink + 1)]
    for index, (supply, row) in enumerate(zip(supplies, limits, strict=True), 1):
        _edge(graph, 0, index, supply)
        for split, (low, high) in enumerate(row):
            _edge(graph, index, len(strata) + 1 + split, high - low)
    for split, demand in enumerate(demands):
        _edge(graph, len(strata) + 1 + split, sink, demand)
    if _flow(graph, sink) != sum(demands):
        return None
    return tuple(
        tuple(
            high - graph[index + 1][len(strata) + 1 + split] for split, (_, high) in enumerate(row)
        )
        for index, row in enumerate(limits)
    )


def balance_single_labels(
    samples: tuple[TrainingSample, ...], result: dict[int, SplitName], request: SplitRequest
) -> dict[int, SplitName]:
    """Solve bounded single-label quotas exactly, preserving the closest feasible set totals."""
    grouped: dict[tuple[str, ...], list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        grouped[sample.labels].append(index)
    strata = tuple(
        _Stratum(tuple(indices), bool(label)) for label, indices in sorted(grouped.items())
    )
    ratios = (request.ratios.train, request.ratios.val, request.ratios.test)
    current = tuple(sum(value == split for value in result.values()) for split in SPLITS)
    valid = all(
        bounds[0] <= sum(result[index] == split for index in row.indices) <= bounds[1]
        for row in strata
        for split, ratio, size in zip(SPLITS, ratios, current, strict=True)
        for bounds in (_bounds(len(row.indices), len(samples), ratio, size, labelled=row.labelled),)
    )
    if valid:
        return result
    for sizes in _sizes(strata, len(samples), ratios):
        allocation = _allocate(strata, len(samples), ratios, sizes)
        if allocation is None:
            continue
        for row, quotas in zip(strata, allocation, strict=True):
            indices = sorted(
                row.indices,
                key=lambda index: hashlib.sha256(
                    f"{request.seed}:{samples[index].file.id}".encode()
                ).hexdigest(),
            )
            offset = 0
            for split, count in zip(SPLITS, quotas, strict=True):
                for index in indices[offset : offset + count]:
                    result[index] = split
                offset += count
        return result
    return result
