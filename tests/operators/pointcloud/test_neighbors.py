# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check neighbor search, component labels and the local ratio against direct references."""

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.components import connected
from datakeel.operators.pointcloud.neighbors import EXACT_LIMIT, nearest_neighbors, spatial_order
from datakeel.operators.pointcloud.statistics import local_ratio, typical_spacing
from tests.operators.pointcloud import scans


def _brute(xyz: NDArray[np.float64], rows: NDArray[np.intp], k: int) -> NDArray[np.float64]:
    delta = xyz[rows, None, :] - xyz[None, :, :]
    distances = np.sqrt(np.einsum("ijk,ijk->ij", delta, delta))
    distances[np.arange(len(rows)), rows] = np.inf
    return np.sort(distances, axis=1)[:, :k]


def test_small_clouds_use_exact_neighbors() -> None:
    """Every row of a small cloud gets exactly its k closest other rows."""
    xyz = np.random.default_rng(23).normal(size=(300, 3))
    found = nearest_neighbors(xyz, 5)
    rows = np.arange(len(xyz))
    np.testing.assert_allclose(np.sort(found.distances, axis=1), _brute(xyz, rows, 5))
    direct = np.linalg.norm(xyz[found.indices] - xyz[:, None, :], axis=2)
    np.testing.assert_allclose(direct, found.distances)
    assert not (found.indices == rows[:, None]).any()
    assert found.orders == ()


def test_large_scan_neighbors_match_exact_search_on_sampled_rows() -> None:
    """Merged Morton windows find the true neighbors of a scan with a density gradient."""
    xyz = scans.indoor_scan()
    assert len(xyz) > EXACT_LIMIT
    found = nearest_neighbors(xyz, 12)
    rows = np.random.default_rng(5).choice(len(xyz), 600, replace=False)
    exact = _brute(xyz, rows, 12)
    approximate = np.sort(found.distances[rows], axis=1)
    ratio = approximate.mean(axis=1) / exact.mean(axis=1)
    assert ratio.min() >= 1 - 1e-4
    assert np.median(ratio) < 1.001
    assert np.quantile(ratio, 0.95) < 1.03
    assert np.quantile(ratio, 0.99) < 1.08
    assert (np.abs(approximate[:, 0] - exact[:, 0]) <= 1e-4 * exact[:, 0] + 1e-6).mean() > 0.99
    assert len(found.orders) == 3
    assert all(np.array_equal(np.sort(order), np.arange(len(xyz))) for order in found.orders)


def test_flat_noisy_ground_keeps_isotropic_locality() -> None:
    """A thin axis must not be stretched to full Morton resolution and scramble locality."""
    rng = np.random.default_rng(1828)
    xyz = rng.uniform([0, 0, 0], [100, 100, 0.5], (4000, 3))
    found = nearest_neighbors(xyz, 12)
    rows = rng.choice(len(xyz), 600, replace=False)
    exact = _brute(xyz, rows, 12)
    ratio = found.distances[rows].mean(axis=1) / exact.mean(axis=1)
    assert ratio.min() >= 1 - 1e-4
    assert np.median(ratio) < 1.02
    assert np.quantile(ratio, 0.95) < 1.1


def test_large_cloud_neighbors_are_unique_other_rows() -> None:
    """A row's list never repeats a neighbor or includes the row itself."""
    xyz = scans.vehicle_scan(rings=16)
    found = nearest_neighbors(xyz, 8)
    ordered = np.sort(found.indices, axis=1)
    assert not (np.diff(ordered, axis=1) == 0).any()
    assert not (found.indices == np.arange(len(xyz))[:, None]).any()
    direct = np.linalg.norm(xyz[found.indices] - xyz[:, None, :], axis=2)
    span = float((xyz.max(axis=0) - xyz.min(axis=0)).max())
    np.testing.assert_allclose(direct, found.distances, rtol=0, atol=1e-6 * span)


def test_tight_group_split_across_curve_cells_is_found_whole() -> None:
    """A group straddling a cell boundary of one curve still sees all of its members."""
    rng = np.random.default_rng(8)
    background = rng.uniform(0, 1, (6000, 3))
    group = 0.5 + rng.normal(0, 1e-4, (12, 3))
    xyz = np.vstack([background, group])
    found = nearest_neighbors(xyz, 11)
    members = np.arange(6000, 6012)
    assert all(set(found.indices[row]) == set(members) - {row} for row in members)


def test_spatial_order_is_a_permutation_independent_of_translation() -> None:
    """Shifted curves stay inside the grid and ignore where the cloud sits."""
    unit = np.random.default_rng(4).uniform(0, 1, (500, 3))
    for shift in (0.0, 1 / 6, 1 / 3):
        order = spatial_order(unit, shift)
        assert np.array_equal(np.sort(order), np.arange(500))
    xyz = unit * 7
    np.testing.assert_array_equal(
        nearest_neighbors(xyz + 1e6, 4).indices, nearest_neighbors(xyz, 4).indices
    )


def test_degenerate_neighbor_counts() -> None:
    """A single point has no neighbors; k is capped at the other rows available."""
    assert nearest_neighbors(np.zeros((1, 3)), 5).distances.shape == (1, 0)
    assert nearest_neighbors(np.zeros((3, 3)), 5).distances.shape == (3, 2)


def _union_find(count: int, left: NDArray[np.intp], right: NDArray[np.intp]) -> list[int]:
    parent = list(range(count))

    def root(node: int) -> int:
        while parent[node] != node:
            parent[node] = parent[parent[node]]
            node = parent[node]
        return node

    for a, b in zip(left.tolist(), right.tolist(), strict=True):
        high, low = sorted((root(a), root(b)), reverse=True)
        parent[high] = low
    return [root(node) for node in range(count)]


def test_component_labels_match_union_find() -> None:
    """Labels are the smallest row of each component regardless of edge order."""
    rng = np.random.default_rng(31)
    for count, edges in ((200, 150), (500, 480), (50, 0)):
        left = rng.integers(0, count, edges)
        right = rng.integers(0, count, edges)
        expected = _union_find(count, left, right)
        np.testing.assert_array_equal(connected(count, left, right), expected)
        shuffled = rng.permutation(edges)
        np.testing.assert_array_equal(connected(count, right[shuffled], left[shuffled]), expected)


def test_long_chain_collapses_to_one_label() -> None:
    """Path compression joins a chain whose edges arrive in the worst order."""
    count = 4097
    left = np.arange(count - 1)[::-1]
    np.testing.assert_array_equal(connected(count, left, left + 1), np.zeros(count))


def test_local_ratio_compares_with_neighbors_and_handles_zero_spacing() -> None:
    """Coincident points score zero; a point among coincident neighbors scores infinity."""
    spacing = np.array([1.0, 1.0, 4.0, 0.0, 0.0, 2.0])
    indices = np.array([[1, 2], [0, 2], [0, 1], [4, 5], [3, 5], [3, 4]])
    ratio = local_ratio(spacing, typical_spacing(spacing, indices))
    np.testing.assert_allclose(ratio[:3], [1 / 2.5, 1 / 2.5, 4.0])
    assert ratio[3] == ratio[4] == 0
    assert np.isinf(ratio[5])
