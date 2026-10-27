# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Validate exact neighbors and deterministic large-cloud approximation behavior."""

import numpy as np

from datakeel.operators.pointcloud.statistics import neighbor_distances, outlier_mask, spatial_order


def test_exact_neighbor_scores_match_independent_distance_reference() -> None:
    """Check every small-cloud kNN score against a direct all-pairs implementation."""
    xyz = np.random.default_rng(23).normal(size=(30, 3))
    distances = np.linalg.norm(xyz[:, None] - xyz[None, :], axis=-1)
    np.fill_diagonal(distances, np.inf)
    expected = np.sort(distances, axis=1)[:, :5].mean(axis=1)
    np.testing.assert_allclose(neighbor_distances(xyz, 5), expected)


def test_tiny_and_repeated_clouds_produce_no_spurious_outliers() -> None:
    """No division by zero or self-neighbor rejection occurs on tiny or identical clouds."""
    assert not neighbor_distances(np.zeros((1, 3))).any()
    assert not outlier_mask(np.zeros((2, 3))).any()
    assert not outlier_mask(np.zeros((50, 3))).any()


def test_large_cloud_approximation_finds_sparse_far_points_deterministically() -> None:
    """Exercise the scalable path with unseen generated geometry and obvious sparse outliers."""
    rng = np.random.default_rng(500)
    xyz = np.vstack((rng.normal(0, 0.1, size=(5000, 3)), rng.uniform(20, 100, size=(40, 3))))
    rejected = outlier_mask(xyz)
    assert rejected[-40:].sum() >= 38
    assert rejected[:5000].mean() < 0.02
    np.testing.assert_array_equal(outlier_mask(xyz), rejected)
    assert np.unique(spatial_order(xyz)).size == len(xyz)


def _surfaces(rng: np.random.Generator, count: int) -> np.ndarray:
    """Sample a box-shaped room's six faces with sensor-like jitter."""
    size = np.array([6.0, 5.0, 2.8])
    points = rng.uniform(0, 1, (count, 3)) * size
    axis = rng.integers(0, 3, count)
    points[np.arange(count), axis] = rng.integers(0, 2, count) * size[axis]
    return points + rng.normal(0, 0.004, points.shape)


def test_clean_surface_scan_has_no_statistical_outliers() -> None:
    """Boundary and corner points of a clean scan are not rejected as a fixed tail."""
    room = _surfaces(np.random.default_rng(1810), 12000)
    assert outlier_mask(room).mean() < 0.002


def test_heavy_scattered_contamination_is_found_without_masking() -> None:
    """A median spacing scale keeps detecting outliers when they are a large minority."""
    rng = np.random.default_rng(1811)
    room = _surfaces(rng, 12000)
    noise = rng.uniform(-15, 20, (4000, 3))
    rejected = outlier_mask(np.vstack((room, noise)))
    assert rejected[12000:].mean() > 0.9
    assert rejected[:12000].mean() < 0.01


def test_mostly_repeated_points_still_measure_isolated_points() -> None:
    """A zero median from duplicated returns falls back to the mean spacing."""
    xyz = np.vstack((np.zeros((80, 3)), np.ones((20, 3)) * 0.01, [[50.0, 50.0, 50.0]]))
    rejected = outlier_mask(xyz, neighbors=4)
    assert rejected[-1]
    assert not rejected[:-1].any()
