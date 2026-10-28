# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Vectorized per-group statistics and the local thickness of scanned neighborhoods.

Coordinates are normalized to [0, 1]; spreads below about 1e-12 of that span
are rounding error, so such points count as coincident.
"""

import numpy as np
from numpy.typing import NDArray

_MIN_SPREAD_POINTS = 4
_COINCIDENT = 1e-24


def group_quantile(
    owner: NDArray[np.intp], values: NDArray[np.float64], groups: int, quantile: float
) -> NDArray[np.float64]:
    """Return one linearly interpolated quantile per group, NaN for a group without values."""
    order = np.lexsort((values, owner))
    owner, values = owner[order], values[order]
    bounds = np.searchsorted(owner, np.arange(groups + 1))
    counts = np.diff(bounds)
    result = np.full(groups, np.nan)
    present = counts > 0
    position = quantile * (counts[present] - 1)
    low = np.floor(position).astype(np.intp)
    high = np.ceil(position).astype(np.intp)
    start = bounds[:-1][present]
    below, above = values[start + low], values[start + high]
    result[present] = below + (above - below) * (position - low)
    return result


def group_median(
    owner: NDArray[np.intp], values: NDArray[np.float64], groups: int
) -> NDArray[np.float64]:
    """Return the median value of each group, NaN for a group without values."""
    return group_quantile(owner, values, groups, 0.5)


def _spread(
    points: NDArray[np.float64], weights: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Return weighted covariance eigenvalues, smallest first, and each row's weight."""
    total = weights.sum(axis=1)
    mean = np.einsum("nk,nki->ni", weights, points) / total[:, None]
    offset = points - mean[:, None, :]
    covariance = np.einsum("nk,nki,nkj->nij", weights, offset, offset) / total[:, None, None]
    spread = np.clip(np.linalg.eigvalsh(covariance), 0, None).astype(np.float64)
    return spread, total


def closest(
    distances: NDArray[np.float64], indices: NDArray[np.intp], count: int
) -> NDArray[np.intp]:
    """Return each row's ``count`` closest neighbors, nearest first."""
    order = np.argsort(distances, axis=1, kind="stable")[:, :count]
    return np.take_along_axis(indices, order, axis=1)


def local_thickness(
    xyz: NDArray[np.float64],
    neighbors: NDArray[np.intp],
    labels: NDArray[np.intp],
    rows: NDArray[np.intp],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    """Measure how far each row's neighborhood in its own component departs from a surface.

    ``neighbors`` holds the neighbor indices of each of ``rows``. The
    neighborhood is the row and those neighbors that share its component.
    The first result is the smallest spread over the largest, near zero on a
    scanned line or surface, curved or not, and large where points fill a
    volume; the second is the smallest spread itself, which a noisy surface
    keeps at about its measurement noise. Neighborhoods of fewer than four
    points have no thickness.
    """
    same = labels[neighbors] == labels[rows][:, None]
    points = np.concatenate([xyz[rows][:, None, :], xyz[neighbors]], axis=1)
    weights = np.concatenate([np.ones((len(rows), 1), dtype=bool), same], axis=1)
    spread, total = _spread(points, weights.astype(np.float64))
    valid = (total >= _MIN_SPREAD_POINTS) & (spread[:, 2] > _COINCIDENT)
    largest = np.where(valid, spread[:, 2], 1.0)
    relative = np.where(valid, np.sqrt(spread[:, 0] / largest), 0.0)
    return relative, np.where(valid, np.sqrt(spread[:, 0]), 0.0)


def group_thinness(
    xyz: NDArray[np.float64], rows: NDArray[np.intp], owner: NDArray[np.intp], groups: int
) -> tuple[NDArray[np.float64], NDArray[np.bool_]]:
    """Return the smallest over the largest spread of each whole group, and which coincide.

    A group of fewer than four points, or of coincident points, has no shape
    and scores NaN.
    """
    count = np.bincount(owner, minlength=groups).astype(np.float64)
    safe = np.maximum(count, 1)
    points = xyz[rows]
    mean = np.stack([np.bincount(owner, points[:, axis], groups) for axis in range(3)], 1)
    offset = points - (mean / safe[:, None])[owner]
    covariance = np.empty((groups, 3, 3))
    for first in range(3):
        for second in range(first, 3):
            value = np.bincount(owner, offset[:, first] * offset[:, second], groups) / safe
            covariance[:, first, second] = covariance[:, second, first] = value
    spread = np.clip(np.linalg.eigvalsh(covariance), 0, None).astype(np.float64)
    coincident = spread[:, 2] <= _COINCIDENT
    valid = (count >= _MIN_SPREAD_POINTS) & ~coincident
    ratio = np.sqrt(spread[:, 0] / np.where(valid, spread[:, 2], 1.0))
    return np.where(valid, ratio, np.nan), coincident
