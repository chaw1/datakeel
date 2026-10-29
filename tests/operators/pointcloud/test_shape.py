# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Check scanned-surface thickness, grouped statistics and bounded nearby-point queries."""

import numpy as np
import pytest
from numpy.typing import NDArray

from datakeel.operators.pointcloud.cells import cell_index, isolated_group
from datakeel.operators.pointcloud.neighbors import nearest_neighbors, normalize
from datakeel.operators.pointcloud.shape import (
    closest,
    group_median,
    group_quantile,
    group_thinness,
    local_thickness,
)

RNG = np.random.default_rng(31)


def _cap(count: int) -> NDArray[np.float64]:
    """Return the near half of a 0.3 m sphere, as one sensor position sees a round shade."""
    direction = RNG.normal(size=(count, 3))
    direction[:, 0] = -np.abs(direction[:, 0])
    return 0.3 * direction / np.linalg.norm(direction, axis=1, keepdims=True)


def _corner(count: int) -> NDArray[np.float64]:
    """Return two perpendicular 1 m faces meeting at an edge, like a car corner."""
    u, v = RNG.uniform(0, 1, (2, count))
    side = RNG.random(count) < 0.5
    return np.column_stack([np.where(side, u, 0.0), np.where(side, 0.0, u), v])


SHAPES = {
    "line": lambda count: np.column_stack(
        [np.linspace(0, 1, count), np.zeros(count), np.zeros(count)]
    ),
    "plane": lambda count: np.column_stack([RNG.uniform(0, 1, (count, 2)), np.zeros(count)]),
    "cap": _cap,
    "corner": _corner,
    "blob": lambda count: RNG.normal(0, 0.3, (count, 3)),
}


def _thickness(points: NDArray[np.float64]) -> tuple[float, float]:
    unit, _ = normalize(points)
    found = nearest_neighbors(unit, 12)
    labels = np.zeros(len(points), dtype=np.intp)
    relative, absolute = local_thickness(unit, found.indices, labels, np.arange(len(points)))
    return float(np.median(relative)), float(np.median(absolute))


@pytest.mark.parametrize("shape", ["line", "plane", "cap", "corner"])
def test_curved_and_bent_surfaces_are_thin_at_neighbor_scale(shape: str) -> None:
    """Lines, planes, round shades and corners are surfaces even when not flat overall."""
    points = SHAPES[shape](3000)
    assert _thickness(points)[0] < 0.15
    if shape in {"cap", "corner"}:
        rows = np.arange(len(points))
        unit = normalize(points)[0]
        assert group_thinness(unit, rows, np.zeros(len(points), dtype=np.intp), 1)[0][0] > 0.3


def test_volume_filling_blob_is_thick_and_noise_sets_the_absolute_scale() -> None:
    """A filled blob is thick; a noisy plane is thick relative to neighbors but only as noise."""
    assert _thickness(SHAPES["blob"](3000))[0] > 0.4
    plane = SHAPES["plane"](3000)
    noisy = plane + np.column_stack([np.zeros((3000, 2)), RNG.normal(0, 0.01, 3000)])
    relative, absolute = _thickness(noisy)
    assert relative > 0.3
    assert absolute < 3 * _thickness(plane)[1] + 0.02


def test_neighbors_from_other_components_and_tiny_groups_do_not_count() -> None:
    """Only same-component neighbors shape a neighborhood; under four points has no shape."""
    xyz = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1], [0.5, 0.5, 0.5]], dtype=float)
    indices = np.array([[1, 2, 3, 4]] * 5)
    together = np.zeros(5, dtype=np.intp)
    relative, absolute = local_thickness(xyz, indices[:1], together, np.array([0]))
    assert relative[0] > 0.5
    assert absolute[0] > 0.1
    apart = np.array([0, 0, 0, 1, 1])
    assert local_thickness(xyz, indices[:1], apart, np.array([0])) == (0.0, 0.0)
    rows = np.arange(5)
    owner = np.array([0, 0, 0, 1, 1])
    thinness, coincident = group_thinness(xyz, rows, owner, 2)
    assert np.isnan(thinness).all()
    assert not coincident.any()
    stacked = np.full((6, 3), 0.4)
    thinness, coincident = group_thinness(stacked, np.arange(6), np.zeros(6, dtype=np.intp), 1)
    assert np.isnan(thinness[0])
    assert coincident[0]


def test_group_median_matches_numpy_per_group() -> None:
    """Medians are exact for odd and even groups and NaN for an empty group."""
    owner = np.array([2, 0, 0, 2, 0, 2, 2])
    values = np.array([4.0, 3.0, 1.0, 1.0, 2.0, 9.0, 2.0])
    result = group_median(owner, values, 4)
    np.testing.assert_allclose(result[[0, 2]], [2.0, 3.0])
    assert np.isnan(result[[1, 3]]).all()


@pytest.mark.parametrize("quantile", [0.0, 0.25, 0.9, 1.0])
def test_group_quantile_interpolates_like_numpy(quantile: float) -> None:
    """Each group's quantile equals NumPy's linear interpolation over that group alone."""
    owner = RNG.integers(0, 5, 200)
    values = RNG.normal(size=200)
    result = group_quantile(owner, values, 6, quantile)
    expected = [np.quantile(values[owner == group], quantile) for group in range(5)]
    np.testing.assert_allclose(result[:5], expected)
    assert np.isnan(result[5])


def test_closest_returns_the_nearest_neighbors_first() -> None:
    """Neighbor rows are unordered; closest sorts each row by distance."""
    distances = np.array([[0.3, 0.1, 0.2], [0.5, 0.4, 0.6]])
    indices = np.array([[7, 8, 9], [4, 5, 6]])
    assert closest(distances, indices, 2).tolist() == [[8, 9], [5, 4]]


def _ring_pole(azimuth_step: float) -> NDArray[np.float64]:
    """Scan a 0.15 m pole 28 m away ring by ring, 0.6 degrees apart, with 2 cm range noise."""
    azimuth = np.radians(np.arange(-0.5, 0.5, azimuth_step))
    direction = np.column_stack([np.cos(azimuth), np.sin(azimuth)])
    half = direction[:, 0] * 28.0
    discriminant = half**2 - (28.0**2 - 0.15**2)
    hit = discriminant > 0
    reach = half[hit] - np.sqrt(discriminant[hit])
    rings = []
    for elevation in np.radians(np.arange(0, 7.5, 0.6)):
        noisy = reach + RNG.normal(0, 0.02, len(reach))
        rings.append(np.column_stack([direction[hit] * noisy[:, None], noisy * np.tan(elevation)]))
    return np.vstack(rings)


def test_a_pole_scanned_ring_by_ring_is_thin_at_its_closest_returns() -> None:
    """Twelve neighbors reach the next ring and look filled; the closest seven stay on one."""
    unit, _ = normalize(_ring_pole(0.06))
    found = nearest_neighbors(unit, 12)
    labels = np.zeros(len(unit), dtype=np.intp)
    rows = np.arange(len(unit))
    wide, _ = local_thickness(unit, found.indices, labels, rows)
    nearest = closest(found.distances, found.indices, 7)
    narrow, _ = local_thickness(unit, nearest, labels, rows)
    assert np.median(wide) > 0.2
    assert np.median(narrow) < 0.01


def _isolated_by_brute(
    unit: NDArray[np.float64], members: NDArray[np.intp], labels: NDArray[np.intp], radius: float
) -> bool:
    others = np.flatnonzero(labels != labels[members[0]])
    delta = unit[members, None, :] - unit[None, others, :]
    return not (np.einsum("ijk,ijk->ij", delta, delta) <= radius * radius).any()


@pytest.mark.parametrize("radius", [1e-5, 0.003, 0.02, 0.1, 0.4, 2.0])
def test_cell_query_agrees_with_brute_force(radius: float) -> None:
    """Visiting only the 27 cells around each member is exact at every grid level."""
    unit = RNG.uniform(0, 1, (6000, 3))
    labels = (np.arange(6000) // 40).astype(np.intp)
    index = cell_index(unit)
    for group in range(0, 150, 7):
        members = np.flatnonzero(labels == group)
        expected = _isolated_by_brute(unit, members, labels, radius)
        assert isolated_group(index, unit, members, labels, radius) is expected


def test_cell_query_finds_a_point_just_inside_the_radius_across_a_cell_border() -> None:
    """A neighbor in the next coarse cell counts; one just beyond the radius does not."""
    unit = np.array([[0.25, 0.25, 0.25], [0.25 + 0.0099, 0.25, 0.25], [0.9, 0.9, 0.9]])
    labels = np.array([0, 1, 2], dtype=np.intp)
    index = cell_index(unit)
    members = np.array([0])
    assert isolated_group(index, unit, members, labels, 0.0098)
    assert not isolated_group(index, unit, members, labels, 0.01)
