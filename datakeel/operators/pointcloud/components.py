# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Connected components on locally pruned neighbor links and separated small clusters."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.neighbors import Neighbors

_ORDER_STEPS = (1, 2)
_MAX_CANDIDATES = 4096
_DISTANCE_BLOCK = 4096
_MIN_VOLUME_POINTS = 3
_VOLUME_SPREAD = 0.2


class ClusterPolicy(NamedTuple):
    """Carry the link, separation and size limits for small-component detection."""

    link_ratio: float
    gap_ratio: float
    min_points: int
    min_fraction: float
    sparse_ratio: float


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
) -> tuple[NDArray[np.intp], NDArray[np.intp], NDArray[np.float64]]:
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
    return joined_left[keep], joined_right[keep], joined_length[keep]


def _separated(
    xyz: NDArray[np.float64],
    members: NDArray[np.intp],
    labels: NDArray[np.intp],
    sorted_x: tuple[NDArray[np.intp], NDArray[np.float64]],
    radius: float,
) -> bool:
    """Return whether no point outside the component lies within radius of it."""
    points = xyz[members]
    low: NDArray[np.float64] = points.min(axis=0) - radius
    high: NDArray[np.float64] = points.max(axis=0) + radius
    order, values = sorted_x
    start = int(np.searchsorted(values, float(low[0]), side="left"))
    stop = int(np.searchsorted(values, float(high[0]), side="right"))
    nearby = order[start:stop]
    inside = ((xyz[nearby, 1:] >= low[1:]) & (xyz[nearby, 1:] <= high[1:])).all(axis=1)
    nearby = nearby[inside & (labels[nearby] != labels[members[0]])]
    for block in range(0, len(nearby), _DISTANCE_BLOCK):
        delta = points[:, None, :] - xyz[nearby[block : block + _DISTANCE_BLOCK]][None, :, :]
        if (np.einsum("ijk,ijk->ij", delta, delta) <= radius * radius).any():
            return False
    return True


def _surface_like(points: NDArray[np.float64]) -> bool:
    """Return whether points are thin in some direction, like a scanned line or patch.

    Scanners sample surfaces, so an isolated piece of real scene, such as a
    ring segment or a patch of a far wall, has a thinnest spread far below
    its largest. A group that fills a volume about evenly does not.
    """
    if len(points) <= _MIN_VOLUME_POINTS:
        return True
    spread = np.clip(np.linalg.eigvalsh(np.cov(points, rowvar=False)), 0, None)
    return bool(spread[0] < _VOLUME_SPREAD**2 * spread[2])


def _sparser(
    xyz: NDArray[np.float64],
    members: NDArray[np.intp],
    labels: NDArray[np.intp],
    found: Neighbors,
    reference: tuple[NDArray[np.float64], float, float],
) -> bool:
    """Return whether members are far sparser than the outside points they neighbor.

    A group none of whose neighbors lie outside it is compared with the main
    body instead, but only when it fills a volume: a scanned surface that far
    away is real scene seen at long range.
    """
    spacing, body, ratio = reference
    outside = found.indices[members].ravel()
    outside = outside[labels[outside] != labels[members[0]]]
    if len(outside):
        return float(np.median(spacing[members])) > ratio * float(np.median(spacing[outside]))
    if _surface_like(xyz[members]):
        return False
    return float(np.median(spacing[members])) > ratio * body


def separated_clusters(
    xyz: NDArray[np.float64], found: Neighbors, spacing: NDArray[np.float64], policy: ClusterPolicy
) -> NDArray[np.bool_]:
    """Mark components much sparser than their surroundings and small ones far from them.

    Every component except the largest is marked when the median spacing of
    its members exceeds sparse_ratio times that of the outside points in
    their neighborhoods, which catches strays spread around a scene however
    many there are; a group that fills a volume with no outside neighbors is
    compared with the largest component. A component is small when it has fewer points than the
    larger of the absolute and proportional minimum; it is also marked when
    no other point lies within gap_ratio times its internal link spacing,
    which catches compact floating clusters. A small piece of scanned
    surface, thin in some direction, must also be more than twice its own
    extent away, so ring segments and far wall patches stay. A stack of
    repeated points has no link spacing of its own and uses the typical
    nonzero spacing of the cloud instead. Single points are left to the
    local density ratio.
    """
    count = len(xyz)
    result = np.zeros(count, dtype=bool)
    if count == 0 or found.indices.shape[1] == 0:
        return result
    left, right, length = _links(xyz, found, spacing, policy.link_ratio)
    _, inverse, sizes = np.unique(
        connected(count, left, right), return_inverse=True, return_counts=True
    )
    limit = max(policy.min_points, policy.min_fraction * count)
    largest = int(np.argmax(sizes))
    if sizes[largest] < limit:
        return result
    candidates = np.flatnonzero(sizes > 1)
    candidates = candidates[candidates != largest]
    linked = inverse[left]
    order = np.argsort(linked, kind="stable")
    bounds = np.searchsorted(linked[order], np.arange(len(sizes) + 1))
    member_order = np.argsort(inverse, kind="stable")
    member_bounds = np.searchsorted(inverse[member_order], np.arange(len(sizes) + 1))
    x_order = np.argsort(xyz[:, 0], kind="stable")
    sorted_x = (x_order, xyz[x_order, 0])
    body = member_order[member_bounds[largest] : member_bounds[largest + 1]]
    positive = spacing[spacing > 0]
    typical = float(np.median(positive)) if len(positive) else 0.0
    reference = (spacing, float(np.median(spacing[body])), policy.sparse_ratio)
    for component in candidates[np.argsort(sizes[candidates], kind="stable")][:_MAX_CANDIDATES]:
        members = member_order[member_bounds[component] : member_bounds[component + 1]]
        if _sparser(xyz, members, inverse, found, reference):
            result[members] = True
            continue
        edges = length[order[bounds[component] : bounds[component + 1]]]
        if sizes[component] >= limit or not len(edges):
            continue
        radius = policy.gap_ratio * (float(np.median(edges)) or typical)
        if _surface_like(xyz[members]):
            extent = float((xyz[members].max(axis=0) - xyz[members].min(axis=0)).max())
            radius = max(radius, 2 * extent)
        if _separated(xyz, members, inverse, sorted_x, radius):
            result[members] = True
    return result
