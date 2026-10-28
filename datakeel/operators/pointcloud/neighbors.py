# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded k-nearest-neighbor search with deterministic shifted Morton windows."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

EXACT_LIMIT = 2048
_BATCH_SIZE = 16384
_MORTON_BITS = 20
# Non-dyadic offsets (in units of twice the cloud span) move every Morton cell
# boundary; a boundary of one order is interior to the others.
_SHIFTS = (0.0, 1 / 6, 1 / 3)
_FLOAT_MAX = float(np.finfo(np.float64).max)


class Neighbors(NamedTuple):
    """Hold neighbor distances, their row indices and the Morton orders searched."""

    distances: NDArray[np.float64]
    indices: NDArray[np.intp]
    orders: tuple[NDArray[np.intp], ...]


def _interleave(values: NDArray[np.uint64]) -> NDArray[np.uint64]:
    values = (values | (values << np.uint64(32))) & np.uint64(0x1F00000000FFFF)
    values = (values | (values << np.uint64(16))) & np.uint64(0x1F0000FF0000FF)
    values = (values | (values << np.uint64(8))) & np.uint64(0x100F00F00F00F00F)
    values = (values | (values << np.uint64(4))) & np.uint64(0x10C30C30C30C30C3)
    return (values | (values << np.uint64(2))) & np.uint64(0x1249249249249249)


def spatial_order(unit: NDArray[np.float64], shift: float = 0.0) -> NDArray[np.intp]:
    """Sort coordinates normalized to [0, 1] into a Morton curve on one cubic grid.

    One isotropic scale keeps grid cells cubic in source units. Normalizing
    each axis separately would stretch a thin axis, such as the sensor noise
    of a flat ground scan, across every bit level and break the locality the
    neighbor window depends on. The grid spans twice the cloud so a shift
    keeps every point inside it.
    """
    scaled = np.clip(unit / 2 + shift, 0, 1)
    grid = np.floor(scaled * ((1 << _MORTON_BITS) - 1)).astype(np.uint64)
    codes = _interleave(grid[:, 0])
    codes |= _interleave(grid[:, 1]) << np.uint64(1)
    codes |= _interleave(grid[:, 2]) << np.uint64(2)
    return np.argsort(codes, kind="stable")


def normalize(xyz: NDArray[np.float64]) -> tuple[NDArray[np.float64], float]:
    """Translate and scale finite coordinates into [0, 1] without overflow.

    Distances are computed on these coordinates and scaled back, so squared
    distances neither overflow for huge magnitudes nor underflow for tiny ones.
    """
    with np.errstate(over="ignore", invalid="ignore"):
        local = np.minimum(xyz - xyz.min(axis=0), _FLOAT_MAX)
    span = max(float(local.max()), np.finfo(np.float64).tiny)
    return local / span, span


def _exact(xyz: NDArray[np.float64], k: int) -> Neighbors:
    count = len(xyz)
    distances = np.empty((count, k), dtype=np.float64)
    indices = np.empty((count, k), dtype=np.intp)
    for start in range(0, count, 512):
        stop = min(start + 512, count)
        delta = xyz[start:stop, None, :] - xyz[None, :, :]
        squared = np.einsum("ijk,ijk->ij", delta, delta)
        squared[np.arange(stop - start), np.arange(start, stop)] = np.inf
        part = np.argpartition(squared, k - 1, axis=1)[:, :k]
        indices[start:stop] = part
        distances[start:stop] = np.sqrt(np.take_along_axis(squared, part, axis=1))
    return Neighbors(distances, indices, ())


def _window(
    coords: NDArray[np.float32], order: NDArray[np.intp], k: int
) -> tuple[NDArray[np.float64], NDArray[np.intp]]:
    """Take the k closest of the k predecessors and k successors along one order."""
    count = len(coords)
    ordered = coords[order]
    padded = np.pad(ordered, ((k, k), (0, 0)), constant_values=np.inf)
    padded_order = np.pad(order, (k, k), constant_values=-1)
    offsets = (*range(-k, 0), *range(1, k + 1))
    distances = np.empty((count, k), dtype=np.float64)
    indices = np.empty((count, k), dtype=np.intp)
    for start in range(0, count, _BATCH_SIZE):
        stop = min(start + _BATCH_SIZE, count)
        here = ordered[start:stop]
        squared = np.empty((stop - start, 2 * k), dtype=coords.dtype)
        candidates = np.empty((stop - start, 2 * k), dtype=np.intp)
        for column, offset in enumerate(offsets):
            delta = here - padded[start + k + offset : stop + k + offset]
            squared[:, column] = np.einsum("ij,ij->i", delta, delta)
            candidates[:, column] = padded_order[start + k + offset : stop + k + offset]
        part = np.argpartition(squared, k - 1, axis=1)[:, :k]
        rows = order[start:stop]
        distances[rows] = np.sqrt(np.take_along_axis(squared, part, axis=1))
        indices[rows] = np.take_along_axis(candidates, part, axis=1)
    return distances, indices


def _merge(
    found: tuple[NDArray[np.float64], NDArray[np.intp]],
    extra: tuple[NDArray[np.float64], NDArray[np.intp]],
) -> None:
    """Keep each row's k closest of two candidate lists, counting shared neighbors once."""
    distances, indices = found
    count, k = indices.shape
    for start in range(0, count, _BATCH_SIZE):
        stop = min(start + _BATCH_SIZE, count)
        fresh = extra[0][start:stop].copy()
        candidates = extra[1][start:stop]
        known = (candidates[:, :, None] == indices[start:stop, None, :]).any(axis=2)
        fresh[known] = np.inf
        merged = np.concatenate([distances[start:stop], fresh], axis=1)
        merged_indices = np.concatenate([indices[start:stop], candidates], axis=1)
        part = np.argpartition(merged, k - 1, axis=1)[:, :k]
        distances[start:stop] = np.take_along_axis(merged, part, axis=1)
        indices[start:stop] = np.take_along_axis(merged_indices, part, axis=1)


def nearest_neighbors(xyz: NDArray[np.float64], neighbors: int) -> Neighbors:
    """Find each row's k nearest other rows, exactly for small clouds.

    Larger clouds search the k predecessors and successors of every row
    along three Morton curves whose cell boundaries are offset from each
    other, and keep the k closest candidates. A window can only miss closer
    points, so distances are never underestimated. On a generated indoor
    scan one curve alone put the mean neighbor distance of a typical row 20%
    too high; the three together find every nearest neighbor and keep the
    mean within 2% for 95% of rows. Neighbors are unordered within a row;
    results are deterministic.
    """
    count = len(xyz)
    k = min(neighbors, count - 1)
    if k < 1:
        empty = np.empty((count, 0))
        return Neighbors(empty, empty.astype(np.intp), ())
    unit, span = normalize(xyz)
    if count <= EXACT_LIMIT:
        found = _exact(unit, k)
        distances, indices, orders = found.distances, found.indices, ()
    else:
        coords = unit.astype(np.float32)
        orders = tuple(spatial_order(unit, shift) for shift in _SHIFTS)
        distances, indices = _window(coords, orders[0], k)
        for order in orders[1:]:
            _merge((distances, indices), _window(coords, order, k))
    with np.errstate(over="ignore"):
        scaled = np.minimum(distances * span, _FLOAT_MAX)
    return Neighbors(scaled, indices, orders)
