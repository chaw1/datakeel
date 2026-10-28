# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Connected components on locally pruned neighbor links and separated outlier clusters."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.cells import cell_index, isolated_group
from datakeel.operators.pointcloud.neighbors import Neighbors
from datakeel.operators.pointcloud.shape import (
    closest,
    group_median,
    group_quantile,
    group_thinness,
    local_thickness,
)

_ORDER_STEPS = (1, 2)
_MAX_CANDIDATES = 4096
_SAMPLED_MEMBERS = 32
_ROUGHNESS_SAMPLE = 4096
_ROUGHNESS_QUANTILE = 0.9
# A neighborhood whose smallest spread is under 0.3 of its largest lies on a
# line or surface; a group of fewer than four points always does.
_VOLUME_THICKNESS = 0.3
_NOISE_FACTOR = 3.0
# Points of one scan line or flat patch: smallest spread under 5% of the largest.
_FLAT = 0.05
# The closest seven neighbors of a return on a scan line lie on that line's
# cone or plane: on generated scans they measured under 0.001, while those
# of 300 random filled blobs of 8 to 60 points all stayed above 0.10.
_SCAN_LINE_NEIGHBORS = 7
# A group is sparse only when even its densest quarter of rows is, so strays
# that link into real structure cannot take that structure down with them.
_DENSE_QUARTER = 0.25


class ClusterPolicy(NamedTuple):
    """Carry the link, separation and size limits for small-component detection."""

    link_ratio: float
    gap_ratio: float
    min_points: int
    min_fraction: float
    sparse_ratio: float


class _Groups(NamedTuple):
    """Candidate components, a bounded sample of each one's rows and every row's label."""

    ids: NDArray[np.intp]
    sizes: NDArray[np.intp]
    rows: NDArray[np.intp]
    owner: NDArray[np.intp]
    labels: NDArray[np.intp]
    members: tuple[NDArray[np.intp], NDArray[np.intp]]
    body: int
    limit: float

    def all_rows(self, group: int) -> NDArray[np.intp]:
        """Return every row of one candidate component."""
        order, bounds = self.members
        component = self.ids[group]
        return order[bounds[component] : bounds[component + 1]]


class _Evidence(NamedTuple):
    """Per-candidate medians over sampled rows; NaN where a candidate has no such value."""

    spacing: NDArray[np.float64]
    dense_quarter: NDArray[np.float64]
    outside: NDArray[np.float64]
    internal: NDArray[np.float64]
    relative: NDArray[np.float64]
    absolute: NDArray[np.float64]
    scan_line: NDArray[np.float64]


def connected(count: int, left: NDArray[np.intp], right: NDArray[np.intp]) -> NDArray[np.intp]:
    """Label undirected components by hooking larger roots onto smaller ones.

    Each round attaches every root that still shares an edge with another
    root, then compresses paths, so the number of rounds stays logarithmic in
    practice and the result does not depend on edge order. Labels are the
    smallest row index of each component.
    """
    parent = np.arange(count)
    np.minimum.at(parent, np.maximum(left, right), np.minimum(left, right))
    while True:
        while True:
            grand = parent[parent]
            if np.array_equal(grand, parent):
                break
            parent = grand
        roots_left, roots_right = parent[left], parent[right]
        live = roots_left != roots_right
        if not live.any():
            return parent
        left, right = left[live], right[live]
        np.minimum.at(
            parent,
            np.maximum(roots_left[live], roots_right[live]),
            np.minimum(roots_left[live], roots_right[live]),
        )


def _links(
    xyz: NDArray[np.float64], found: Neighbors, spacing: NDArray[np.float64], link_ratio: float
) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    """Keep neighbor links no longer than link_ratio times the smaller local spacing.

    Neighbors of the base Morton order rarely cross that order's cell
    boundaries, so near neighbors along the shifted orders are linked too.
    """
    count, k = found.indices.shape
    left: list[NDArray[np.intp]] = [np.repeat(np.arange(count, dtype=np.intp), k)]
    right: list[NDArray[np.intp]] = [found.indices.ravel()]
    length: list[NDArray[np.float64]] = [found.distances.ravel()]
    for order in found.orders[1:]:
        for step in _ORDER_STEPS:
            left.append(order[:-step])
            right.append(order[step:])
            length.append(np.linalg.norm(xyz[order[:-step]] - xyz[order[step:]], axis=1))
    joined_left, joined_right = np.concatenate(left), np.concatenate(right)
    joined_length = np.concatenate(length)
    keep = joined_length <= link_ratio * np.minimum(spacing[joined_left], spacing[joined_right])
    return joined_left[keep], joined_right[keep]


def _candidates(
    labels: NDArray[np.intp], sizes: NDArray[np.intp], largest: int, limit: float
) -> _Groups:
    """Pick the smaller components, smallest first, with up to 32 evenly spread rows each."""
    ids = np.flatnonzero(sizes > 1)
    ids = ids[ids != largest]
    ids = ids[np.argsort(sizes[ids], kind="stable")][:_MAX_CANDIDATES]
    order = np.argsort(labels, kind="stable")
    bounds = np.searchsorted(labels[order], np.arange(len(sizes) + 1))
    take = np.minimum(sizes[ids], _SAMPLED_MEMBERS)
    owner = np.repeat(np.arange(len(ids)), take)
    rank = np.arange(int(take.sum())) - np.repeat(np.cumsum(take) - take, take)
    stride = sizes[ids][owner] / take[owner]
    rows = order[bounds[ids][owner] + np.floor(rank * stride).astype(np.intp)]
    return _Groups(ids, sizes[ids], rows, owner, labels, (order, bounds), largest, limit)


def _evidence(
    xyz: NDArray[np.float64], found: Neighbors, spacing: NDArray[np.float64], groups: _Groups
) -> _Evidence:
    """Measure spacing inside and next to each candidate and how thick it is at two scales."""
    count = len(groups.ids)
    neighbors = found.indices[groups.rows]
    distances = found.distances[groups.rows]
    outside = groups.labels[neighbors] != groups.labels[groups.rows][:, None]
    owners = np.repeat(groups.owner, neighbors.shape[1])
    flat_outside = outside.ravel()
    inside_distance = distances.ravel()[~flat_outside]
    relative, absolute = local_thickness(xyz, neighbors, groups.labels, groups.rows)
    nearest = closest(distances, neighbors, _SCAN_LINE_NEIGHBORS)
    scan_line, _ = local_thickness(xyz, nearest, groups.labels, groups.rows)
    return _Evidence(
        group_median(groups.owner, spacing[groups.rows], count),
        group_quantile(groups.owner, spacing[groups.rows], count, _DENSE_QUARTER),
        group_median(owners[flat_outside], spacing[neighbors.ravel()[flat_outside]], count),
        group_median(owners[~flat_outside], inside_distance, count),
        group_median(groups.owner, relative, count),
        group_median(groups.owner, absolute, count),
        group_median(groups.owner, scan_line, count),
    )


def _roughness(
    xyz: NDArray[np.float64], found: Neighbors, labels: NDArray[np.intp], body: NDArray[np.intp]
) -> float:
    """Return the thickness that 90% of the main body's neighborhoods stay within.

    Scanned surfaces are only as thin as the measurement noise, so this is
    the scale below which a group cannot be told from a piece of surface.
    """
    rows = body[np.linspace(0, len(body) - 1, min(len(body), _ROUGHNESS_SAMPLE)).astype(np.intp)]
    return float(
        np.quantile(local_thickness(xyz, found.indices[rows], labels, rows)[1], _ROUGHNESS_QUANTILE)
    )


def _gap_radius(
    xyz: NDArray[np.float64], members: NDArray[np.intp], internal: float, gap: float, *, noisy: bool
) -> float:
    """Scale the separation a group needs by its own spacing, and by its size if within noise."""
    radius = gap * internal
    if noisy:
        radius = max(radius, 2 * float((xyz[members].max(axis=0) - xyz[members].min(axis=0)).max()))
    return radius


def _all_rows(
    groups: _Groups, selected: NDArray[np.intp]
) -> tuple[NDArray[np.intp], NDArray[np.intp]]:
    """Return every row of the selected candidates and the candidate each row belongs to."""
    order, bounds = groups.members
    sizes = groups.sizes[selected]
    starts = bounds[groups.ids[selected]]
    owner = np.repeat(np.arange(len(selected)), sizes)
    positions = np.repeat(starts - np.cumsum(sizes) + sizes, sizes) + np.arange(int(sizes.sum()))
    return order[positions], owner


def _judge(
    xyz: NDArray[np.float64],
    found: Neighbors,
    spacing: NDArray[np.float64],
    groups: _Groups,
    policy: ClusterPolicy,
) -> NDArray[np.bool_]:
    """Decide for each candidate whether it is an outlier cluster."""
    evidence = _evidence(xyz, found, spacing, groups)
    order, bounds = groups.members
    body = order[bounds[groups.body] : bounds[groups.body + 1]]
    everything = np.arange(len(groups.ids))
    thinness, coincident = group_thinness(xyz, *_all_rows(groups, everything), len(everything))
    noisy = coincident | (
        evidence.absolute <= _NOISE_FACTOR * _roughness(xyz, found, groups.labels, body)
    )
    volume = (
        ~np.isnan(thinness)
        & (evidence.relative >= _VOLUME_THICKNESS)
        & (evidence.scan_line >= _FLAT)
    )
    alone = np.isnan(evidence.outside)
    ratio = policy.sparse_ratio
    flagged = ~alone & (thinness >= _FLAT) & (evidence.dense_quarter > ratio * evidence.outside)
    flagged |= (
        alone & volume & ~noisy & (evidence.spacing > ratio * float(np.median(spacing[body])))
    )
    test = np.flatnonzero((volume | coincident) & ~flagged & (groups.sizes < groups.limit))
    if not len(test):
        return flagged
    positive = spacing[spacing > 0]
    typical = float(np.median(positive)) if len(positive) else 0.0
    index = cell_index(xyz)
    for group in test.tolist():
        members = groups.all_rows(group)
        internal = float(evidence.internal[group])
        scale = internal if np.isfinite(internal) and internal > 0 else typical
        radius = _gap_radius(xyz, members, scale, policy.gap_ratio, noisy=bool(noisy[group]))
        flagged[group] = isolated_group(index, xyz, members, groups.labels, radius)
    return flagged


def separated_clusters(
    xyz: NDArray[np.float64], found: Neighbors, spacing: NDArray[np.float64], policy: ClusterPolicy
) -> NDArray[np.bool_]:
    """Mark connected groups that are much sparser than their surroundings or float apart.

    Components are joined by neighbor links no longer than link_ratio times
    the smaller local spacing; every component except the largest is a
    candidate, smallest first and at most 4096, judged on up to 32 evenly
    spread rows. A scanner samples surfaces along lines, beams or a pixel
    grid, so a real fragment cut off by an occluder or by range, such as a
    pole top behind a car, a far car side, a wall corner or a hanging lamp,
    is thin at the scale of its own neighbors even when curved or bent, and
    its points are as far apart as the scan's sampling at its range.

    A candidate of at least four distinct points is marked when three
    quarters of its sampled rows are more than sparse_ratio times as far
    apart as the outside points they neighbor, unless it is a single scan
    line or flat patch; this catches strays spread around a scene, and not
    real structure that some strays have linked into. A group with no
    outside neighbors is compared with the largest component, but only when
    it fills a volume beyond the measurement noise.

    Distance alone never marks a fragment: occluded and distant structure is
    often metres from anything else. A small group is marked for separation
    only when its points fill a volume, which a scan does not produce: at
    least four points whose twelve-neighbor neighborhoods are thick in every
    direction and whose closest seven neighbors are too. A narrow curved
    object such as a pole or a trunk can look filled at twelve neighbors
    when they span several scan lines, but its closest returns lie on one
    scan line and are thin. Such a group is marked when no other point lies
    within gap_ratio times its own internal spacing, the sampling the scan
    has at that group's range. If its thickness is within the noise of the
    scan's own surfaces, it must also be more than twice its own extent
    away. A stack of coincident points needs gap_ratio times the typical
    spacing. Groups lying on lines or surfaces, and groups of two or three
    distinct points such as the returns of a wire, a branch or an object
    edge, are never marked; single points are left to the isolation test.
    """
    count = len(xyz)
    result = np.zeros(count, dtype=bool)
    if count == 0 or found.indices.shape[1] == 0:
        return result
    left, right = _links(xyz, found, spacing, policy.link_ratio)
    _, labels, sizes = np.unique(
        connected(count, left, right), return_inverse=True, return_counts=True
    )
    limit = max(policy.min_points, policy.min_fraction * count)
    largest = int(np.argmax(sizes))
    if sizes[largest] < limit:
        return result
    groups = _candidates(labels, sizes, largest, limit)
    if not len(groups.ids):
        return result
    marked = np.zeros(len(sizes), dtype=bool)
    marked[groups.ids[_judge(xyz, found, spacing, groups, policy)]] = True
    return marked[labels]
