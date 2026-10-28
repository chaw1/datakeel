# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Judge outlier detection on generated scans whose density falls with range."""

from functools import cache

import numpy as np
import pytest
from numpy.typing import NDArray

from datakeel.operators.pointcloud.models import ProbeParams, StatisticalParams
from datakeel.operators.pointcloud.statistics import analyse, outlier_mask
from tests.operators.pointcloud import scans

LIMIT = ProbeParams().max_outlier_ratio
DEFAULTS = StatisticalParams()


@cache
def _scan(name: str) -> NDArray[np.float64]:
    generators = {
        "indoor": scans.indoor_scan,
        "indoor-fine": lambda: scans.indoor_scan(step=0.5),
        "vehicle": scans.vehicle_scan,
        "vehicle-16": lambda: scans.vehicle_scan(rings=16),
        "depth": scans.depth_scan,
    }
    return generators[name]()


SCANS = ("indoor", "vehicle", "vehicle-16", "depth")


@pytest.mark.parametrize("name", SCANS)
def test_clean_scans_stay_under_the_file_limit_despite_their_density_gradient(name: str) -> None:
    """Far, sparse surfaces are judged against their own neighbors, not the dense near field."""
    points = _scan(name)
    measured = analyse(points, DEFAULTS)
    assert measured.mask.mean() <= LIMIT / 2
    # The gradient is real: one cloud-wide spacing cut would reject far surfaces.
    assert (measured.spacing > 3 * np.median(measured.spacing)).mean() > LIMIT * 5


@pytest.mark.parametrize("name", SCANS)
@pytest.mark.parametrize("fraction", [0.005, 0.02])
def test_scattered_outliers_push_a_scan_over_the_file_limit(name: str, fraction: float) -> None:
    """Uniform strays inside the scanned volume are found without flagging the scan itself."""
    points = _scan(name)
    mask = outlier_mask(scans.scatter(points, fraction), DEFAULTS)
    assert mask.mean() > 2 * LIMIT
    # At 2% the strays in a small room are close enough to neighbor each other and
    # only the most isolated stand out; the file still clears twice the limit.
    assert mask[len(points) :].mean() > (0.2 if fraction < 0.01 else 0.1)
    assert mask[: len(points)].mean() <= 0.001


@pytest.mark.parametrize("name", SCANS)
def test_strays_far_around_a_scan_are_found_by_their_sparseness(name: str) -> None:
    """Strays far outside the scene neighbor each other and still stand out as sparse."""
    points = _scan(name)
    noisy = scans.scatter(points, 0.02, seed=3, margin=10.0)
    assert outlier_mask(noisy, DEFAULTS)[len(points) :].all()
    assert not outlier_mask(noisy, DEFAULTS)[: len(points)].any()
    blind = StatisticalParams(sparse_cluster_ratio=1000)
    assert outlier_mask(noisy, blind)[len(points) :].mean() < 0.1


def test_floating_clusters_are_found_while_small_real_objects_stay() -> None:
    """Compact groups in the air are outliers; a cup on a table and a pillar are scene."""
    room = _scan("indoor-fine")
    count = len(room)
    cup = (np.abs(room[:, :2] - (2.95, 1.45)) <= 0.06).all(axis=1) & (room[:, 2] > 0.76)
    pillar = np.hypot(room[:, 0] - 6.5, room[:, 1] - 2.5) <= 0.17
    assert cup.sum() >= 20
    groups = [
        scans.blob((3.2, 1.6, 1.1), 30, 0.02),
        scans.blob((6, 6, 2.2), 30, 0.03, seed=4),
        scans.blob((3, 6, 1.2), 60, 0.03, seed=5),
    ]
    measured = analyse(np.vstack([room, *groups]), DEFAULTS)
    assert measured.clustered[count:].all()
    assert not measured.mask[:count][cup | pillar].any()
    assert measured.mask[:count].mean() <= LIMIT / 2


def test_cluster_size_limit_follows_its_parameters() -> None:
    """Groups at or above the minimum size are left to the sparseness test."""
    room = _scan("indoor")
    groups = np.vstack([scans.blob((6, 6, 2.2), 30, 0.03), scans.blob((3, 6, 1.2), 60, 0.03, 4)])
    points = np.vstack([room, groups])
    count = len(room)
    for minimum, flagged in ((100, [True, True]), (50, [True, False]), (20, [False, False])):
        params = StatisticalParams(min_cluster_points=minimum, min_cluster_fraction=0)
        mask = outlier_mask(points, params)
        assert [bool(mask[count : count + 30].all()), bool(mask[count + 30 :].all())] == flagged
        assert [bool(mask[count : count + 30].any()), bool(mask[count + 30 :].any())] == flagged
    fraction = StatisticalParams(min_cluster_points=2, min_cluster_fraction=0.002)
    assert outlier_mask(points, fraction)[count:].all()


def _patch(height: float, *, thin: bool, seed: int = 2) -> NDArray[np.float64]:
    """Return 200 points over a 0.3 m square above the floor, flat or filling a cube."""
    rng = np.random.default_rng(seed)
    across = rng.uniform(-0.15, 0.15, (200, 2))
    depth = rng.normal(0, 0.002, 200) if thin else rng.uniform(0, 0.3, 200)
    return np.column_stack([6 + across[:, 0], 6 + across[:, 1], height + depth])


@pytest.mark.parametrize("height", [0.45, 0.9])
def test_floating_surface_pieces_stay_and_volume_filling_groups_go(height: float) -> None:
    """A floating patch of surface is real scene at any clearance; a filled cube is not."""
    room = _scan("indoor")
    count = len(room)
    for thin in (True, False):
        mask = outlier_mask(np.vstack([room, _patch(height, thin=thin)]), DEFAULTS)
        assert bool(mask[count:].all()) is not thin
        assert bool(mask[count:].any()) is not thin
        assert not mask[:count].any()


def _noisy_wall(offset: float, rng: np.random.Generator) -> NDArray[np.float64]:
    """Return a 1 m wall at 5 mm spacing with 1 cm noise and an 8 cm piece of it in front."""
    grid = np.stack(np.meshgrid(np.arange(0, 1, 0.005), np.arange(0, 1, 0.005)), -1)
    piece = np.stack(np.meshgrid(np.arange(0, 0.08, 0.005), np.arange(0, 0.08, 0.005)), -1)
    wall = np.column_stack([rng.normal(0, 0.01, grid[..., 0].size), grid.reshape(-1, 2)])
    front = np.column_stack(
        [offset + rng.normal(0, 0.01, piece[..., 0].size), piece.reshape(-1, 2) + 0.46]
    )
    return np.vstack([wall, front])


def test_pieces_as_thick_as_the_surface_noise_need_twice_their_extent_of_clearance() -> None:
    """A noisy piece looks filled at its own scale; beside its surface it stays, far off it goes."""
    for offset, expected in ((0.15, False), (0.35, True)):
        points = _noisy_wall(offset, np.random.default_rng(8))
        mask = outlier_mask(points, DEFAULTS)
        assert bool(mask[-256:].all()) is expected
        assert bool(mask[-256:].any()) is expected
        assert not mask[:-256].any()


def test_self_contained_groups_are_compared_with_the_main_body_only_when_volumetric() -> None:
    """A far facade with no outside neighbors stays; a sparse cloud filling space does not."""
    room = _scan("indoor")
    count = len(room)
    rng = np.random.default_rng(6)
    grid = np.stack(np.meshgrid(np.arange(25.0), np.arange(25.0)), axis=-1).reshape(-1, 2)
    facade = np.column_stack([100 + rng.normal(0, 0.01, len(grid)), grid - (12, 5)])
    volume = rng.uniform((100, -12, -5), (125, 13, 20), (len(grid), 3))
    assert len(grid) > DEFAULTS.min_cluster_fraction * (count + len(grid))
    assert not outlier_mask(np.vstack([room, facade]), DEFAULTS).any()
    mask = outlier_mask(np.vstack([room, volume]), DEFAULTS)
    assert mask[count:].all()
    assert not mask[:count].any()


def test_a_lone_point_is_isolated_and_a_close_pair_is_kept() -> None:
    """A lone stray is isolated; two points together may be a wire or a branch and stay."""
    room = _scan("indoor")
    count = len(room)
    single = analyse(np.vstack([room, [[6.0, 6.0, 0.5]]]), DEFAULTS)
    assert single.isolated[count:].all()
    pair = analyse(np.vstack([room, [[6.0, 6.0, 0.5], [6.003, 6.0, 0.5]]]), DEFAULTS)
    assert pair.ratio[count:].min() > DEFAULTS.local_ratio
    assert not pair.mask[count:].any()
    assert not pair.mask[:count].any()


def test_tiny_and_repeated_clouds_produce_no_spurious_outliers() -> None:
    """No division by zero or self-neighbor rejection occurs on tiny or identical clouds."""
    for count in (0, 1, 2, 50):
        assert not outlier_mask(np.zeros((count, 3)), DEFAULTS).any()
    assert analyse(np.zeros((2, 3)), DEFAULTS).spacing.tolist() == [0.0, 0.0]


def test_mostly_repeated_points_still_measure_isolated_points() -> None:
    """Duplicated returns score zero instead of making a far point look normal."""
    xyz = np.vstack((np.zeros((80, 3)), np.ones((20, 3)) * 0.01, [[50.0, 50.0, 50.0]]))
    rejected = outlier_mask(xyz, StatisticalParams(neighbors=4))
    assert rejected[-1]
    assert not rejected[:-1].any()


def test_stack_of_repeated_points_in_the_air_is_a_cluster() -> None:
    """Invalid returns written as one repeated coordinate have no spacing but are separated."""
    room = _scan("indoor")
    count = len(room)
    stacked = analyse(np.vstack([room, np.tile([5.0, 4.0, 1.5], (30, 1))]), DEFAULTS)
    assert stacked.clustered[count:].all()
    assert not stacked.isolated[count:].any()
    assert not stacked.mask[:count].any()


def test_nonfinite_rows_are_rejected_without_disturbing_the_rest() -> None:
    """Invalid rows are outliers by definition and are left out of the neighbor search."""
    room = _scan("depth")
    broken = np.vstack([room, [[np.nan, 0, 0], [np.inf, 1, 1]]])
    mask = outlier_mask(broken, DEFAULTS)
    assert mask[-2:].all()
    np.testing.assert_array_equal(mask[:-2], outlier_mask(room, DEFAULTS))
