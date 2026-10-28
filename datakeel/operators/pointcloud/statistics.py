# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Local density outliers and separated clusters measured on k-nearest-neighbor spacing."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.components import ClusterPolicy, separated_clusters
from datakeel.operators.pointcloud.models import StatisticalParams
from datakeel.operators.pointcloud.neighbors import nearest_neighbors, normalize

_MIN_STATISTICAL_POINTS = 3
_FLOAT_MAX = float(np.finfo(np.float64).max)


class OutlierAnalysis(NamedTuple):
    """Per-point evidence for isolated and clustered outliers and local spacing."""

    isolated: NDArray[np.bool_]
    clustered: NDArray[np.bool_]
    ratio: NDArray[np.float64]
    spacing: NDArray[np.float64]
    nearest: NDArray[np.float64]

    @property
    def mask(self) -> NDArray[np.bool_]:
        """Combine both outlier kinds."""
        return self.isolated | self.clustered


def _empty(count: int) -> OutlierAnalysis:
    zeros = np.zeros(count, dtype=np.float64)
    return OutlierAnalysis(
        np.zeros(count, dtype=bool), np.zeros(count, dtype=bool), zeros, zeros, zeros
    )


def local_ratio(spacing: NDArray[np.float64], indices: NDArray[np.intp]) -> NDArray[np.float64]:
    """Divide each mean neighbor distance by the median of its neighbors' own values.

    The reference is local, so the natural near-dense, far-sparse falloff of a
    scan cancels out. Points that coincide with their neighbors score zero; a
    point whose neighbors all coincide scores infinity unless it coincides too.
    """
    reference = np.median(spacing[indices], axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = spacing / reference
    return np.where(spacing == 0, 0.0, ratio)


def analyse(xyz: NDArray[np.float64], params: StatisticalParams) -> OutlierAnalysis:
    """Measure finite coordinates for isolated points and separated small clusters.

    A point is isolated when its mean distance to its k nearest neighbors is
    more than ``local_ratio`` times the median of the same measure over those
    neighbors, and its nearest-neighbor distance is too. The second scale
    keeps short ring fragments and thin poles, whose next point is close but
    whose wider neighborhood reaches other rings, from looking isolated.
    Groups of points that are each other's neighbors escape that test, so
    connected components of locally short links are also checked: a small
    component far from everything else, or one much sparser than the points
    its members neighbor, is marked as clustered.
    Coordinates are normalized first so extreme magnitudes cannot overflow.
    """
    count = len(xyz)
    if count < _MIN_STATISTICAL_POINTS:
        return _empty(count)
    unit, span = normalize(xyz)
    found = nearest_neighbors(unit, params.neighbors)
    spacing = found.distances.mean(axis=1)
    ratio = local_ratio(spacing, found.indices)
    closest = found.distances.min(axis=1)
    nearest_ratio = local_ratio(closest, found.indices)
    policy = ClusterPolicy(
        params.link_ratio,
        params.cluster_gap,
        params.min_cluster_points,
        params.min_cluster_fraction,
        params.sparse_cluster_ratio,
    )
    clustered = separated_clusters(unit, found, spacing, policy)
    with np.errstate(over="ignore"):
        scaled = np.minimum(spacing * span, _FLOAT_MAX)
        nearest = np.minimum(closest * span, _FLOAT_MAX)
    isolated = (ratio > params.local_ratio) & (nearest_ratio > params.local_ratio)
    return OutlierAnalysis(isolated, clustered, ratio, scaled, nearest)


def outlier_mask(xyz: NDArray[np.float64], params: StatisticalParams) -> NDArray[np.bool_]:
    """Mark nonfinite rows, isolated points and separated small clusters."""
    finite = np.isfinite(xyz).all(axis=1)
    result = ~finite
    result[finite] = analyse(xyz[finite], params).mask
    return result
