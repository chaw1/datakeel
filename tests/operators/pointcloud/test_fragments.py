# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Keep occluded, distant and hanging scene fragments while finding strays and blobs."""

from functools import cache

import numpy as np
import pytest
from numpy.typing import NDArray

from datakeel.operators.pointcloud.models import ProbeParams, StatisticalParams
from datakeel.operators.pointcloud.statistics import analyse
from tests.operators.pointcloud import scans

LIMIT = ProbeParams().max_outlier_ratio
DEFAULTS = StatisticalParams()
Origin = tuple[float, float, float]

STREETS: dict[str, tuple[Origin, dict[str, int | float | tuple[float, float]]]] = {
    "street": ((0.0, 0.0, 1.8), {}),
    "street-ahead": ((10.0, 2.0, 1.8), {"layout": 1, "seed": 1}),
    "street-behind": ((-20.0, -3.0, 1.8), {"layout": 2, "seed": 2}),
    "street-16-rings": ((5.0, -1.0, 1.8), {"rings": 16, "azimuth_step": 0.4, "seed": 3}),
    "street-64-rings": ((-8.0, 3.0, 1.9), {"rings": 64, "layout": 1, "seed": 4}),
    "dense-ring": ((0.0, 0.0, 1.8), {"azimuth_step": 0.01, "sector": (0.0, 40.0), "seed": 5}),
}
ROOMS: dict[str, Origin] = {
    "room": (5.0, 4.0, 1.5),
    "room-under-lamp": (4.3, 4.4, 2.0),
    "room-beside-fan": (7.2, 5.5, 1.8),
}
OUTDOOR = (*STREETS, "drive")
CAPTURES = (*OUTDOOR, *ROOMS, "depth")


@cache
def _scan(name: str) -> tuple[NDArray[np.float64], Origin]:
    if name in STREETS:
        origin, options = STREETS[name]
        return scans.street_scan(origin, **options), origin  # type: ignore[arg-type]
    if name in ROOMS:
        return scans.furnished_room(ROOMS[name], step=0.5, seed=len(name)), ROOMS[name]
    if name == "drive":
        return scans.drive(6), (0.0, 0.0, 1.8)
    return scans.depth_scan(), (0.0, 0.0, 1.2)


@pytest.mark.parametrize("name", CAPTURES)
def test_clean_and_dirty_files_are_separated_with_margin(name: str) -> None:
    """A clean capture stays under half the limit; 0.5% strays push it over twice the limit."""
    points, _ = _scan(name)
    clean = analyse(points, DEFAULTS)
    assert not clean.clustered.any()
    assert clean.mask.mean() <= LIMIT / 2
    dirty = analyse(scans.scatter(points, 0.005), DEFAULTS)
    assert dirty.mask.mean() >= 2 * LIMIT
    assert dirty.mask[: len(points)].mean() <= LIMIT / 2


def _near_axis(points: NDArray[np.float64], x: float, y: float, radius: float) -> NDArray[np.bool_]:
    return np.hypot(points[:, 0] - x, points[:, 1] - y) <= radius


def test_pole_tops_behind_parked_cars_far_corners_and_crowns_stay() -> None:
    """Fragments cut off by cars, cross streets or range are scene, metres from the rest."""
    points, _ = _scan("street")
    mask = analyse(points, DEFAULTS).mask
    poles = [_near_axis(points, x, 9.9, 0.15) & (points[:, 2] > 0.1) for x in (-27, -9, 6, 21)]
    hidden = [pole for pole in poles if pole.sum() >= 3 and points[pole, 2].min() > 1.3]
    assert hidden
    crowns = np.zeros(len(points), dtype=bool)
    for x in (-36, 2, 43):
        crowns |= np.linalg.norm(points - (x, -9.0, 4.6), axis=1) < 3.0
    street_end = points[:, 0] > 74
    for part in (*hidden, crowns, street_end):
        assert part.sum() >= 3
        assert not mask[part].any()
    behind, _ = _scan("street-behind")
    corner = behind[:, 1] < -50
    assert corner.sum() >= 20
    assert not analyse(behind, DEFAULTS).mask[corner].any()


def test_a_light_pole_and_object_edges_seen_ring_by_ring_stay() -> None:
    """A dozen returns per ring on a pole look filled at twelve neighbors, not on one ring.

    Two returns of an object edge on adjacent rings are far apart compared
    with the dense rings around them; two points prove nothing either way.
    """
    points = scans.street_scan(rings=64, azimuth_step=0.05, sector=(-10.0, 30.0), seed=4)
    pole = _near_axis(points, 28, 9.6, 0.25)
    assert pole.sum() >= 100
    measured = analyse(points, DEFAULTS)
    assert not measured.clustered.any()
    assert measured.mask.mean() <= LIMIT / 2


def test_strays_linked_into_far_structure_do_not_take_it_down() -> None:
    """Dense rings leave sparse far returns; strays linking to them mark only themselves."""
    points = scans.street_scan(azimuth_step=0.011, sector=(0.0, 90.0), seed=4)
    measured = analyse(scans.scatter(points, 0.005), DEFAULTS)
    assert measured.mask.mean() >= 2 * LIMIT
    assert measured.mask[: len(points)].mean() <= LIMIT / 2


@pytest.mark.parametrize("name", list(ROOMS))
def test_hanging_lamps_and_a_ceiling_fan_stay_from_any_tripod_position(name: str) -> None:
    """A round shade on a thin cord is a curved surface, near the sensor or not."""
    points, _ = _scan(name)
    mask = analyse(points, DEFAULTS).mask
    for center, radius in (((4.0, 5.0, 2.45), 0.3), ((9.0, 2.0, 2.45), 0.17)):
        lamp = np.linalg.norm(points - center, axis=1) <= radius
        assert lamp.sum() >= 30
        assert not mask[lamp].any()
    fan = (np.abs(points[:, :2] - (7.0, 6.0)) <= 0.6).all(axis=1) & (points[:, 2] < 2.7)
    fan &= points[:, 2] > 2.55
    assert fan.sum() >= 30
    assert not mask[fan].any()


@pytest.mark.parametrize("name", CAPTURES)
def test_floating_blobs_are_found_in_every_capture_form(name: str) -> None:
    """Compact blobs in open air are outliers at every range and density of the capture."""
    points, origin = _scan(name)
    sizes = [8, 12, 30, 60]
    outdoor = name in OUTDOOR
    spread, clearance = (0.15, 2.5) if outdoor else (0.01, 0.25)
    blobs = scans.floating_blobs(points, origin, sizes, spread=spread, clearance=clearance)
    mask = analyse(blobs, DEFAULTS).mask
    assert mask[len(points) :].all()
    assert mask[: len(points)].mean() <= LIMIT / 2


def test_dense_ring_noise_tails_are_not_isolated_but_a_stray_beside_them_is() -> None:
    """Range noise far wider than the in-ring spacing is no reason to isolate a return."""
    points, origin = _scan("dense-ring")
    measured = analyse(points, DEFAULTS)
    assert measured.isolated.mean() <= LIMIT / 2
    rng = np.random.default_rng(12)
    targets = points[rng.choice(len(points), 200, replace=False)]
    rays = targets - np.asarray(origin)
    candidates = targets - 0.3 * rays / np.linalg.norm(rays, axis=1, keepdims=True)
    strays = candidates[scans.nearest_distance(points, candidates) >= 0.25][:20]
    assert len(strays) == 20
    found = analyse(np.vstack([points, strays]), DEFAULTS)
    assert found.isolated[len(points) :].all()
    assert found.mask[: len(points)].mean() <= LIMIT / 2
