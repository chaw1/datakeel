# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded k-nearest-neighbor search with deterministic shifted Morton windows."""

from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

EXACT_LIMIT = 2048
_BATCH_SIZE = 16384
MORTON_BITS = 20
CELL_COUNT = (1 << MORTON_BITS) - 1
# Non-dyadic offsets (in units of twice the cloud span) move every Morton cell
# boundary; a boundary of one order is interior to the others.
_SHIFTS = (0.0, 1 / 6, 1 / 3)
_FLOAT_MAX = float(np.finfo(np.float64).max)
_LOW = np.uint64(0xFFFFFFFF)


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


def encode(cells: NDArray[np.uint64]) -> NDArray[np.uint64]:
    """Interleave integer cell coordinates into Morton codes."""
    codes = _interleave(cells[:, 0])
    codes |= _interleave(cells[:, 1]) << np.uint64(1)
    codes |= _interleave(cells[:, 2]) << np.uint64(2)
    return codes


def grid_cells(unit: NDArray[np.float64], shift: float = 0.0) -> NDArray[np.uint64]:
    """Return integer cells of coordinates normalized to [0, 1] on one cubic grid.

    One isotropic scale keeps grid cells cubic in source units. Normalizing
    each axis separately would stretch a thin axis, such as the sensor noise
    of a flat ground scan, across every bit level and break the locality the
    neighbor window depends on. The grid spans twice the cloud so a shift
    keeps every point inside it.
    """
    scaled = np.clip(unit / 2 + shift, 0, 1)
    return np.floor(scaled * CELL_COUNT).astype(np.uint64)


def spatial_order(unit: NDArray[np.float64], shift: float = 0.0) -> NDArray[np.intp]:
    """Sort coordinates normalized to [0, 1] into a Morton curve on one cubic grid."""
    return np.argsort(encode(grid_cells(unit, shift)), kind="stable")


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


def _keys(squared: NDArray[np.float32], rows: NDArray[np.intp]) -> NDArray[np.uint64]:
    """Pack squared distances above row indices so one partition orders both.

    Non-negative float32 values keep their order as unsigned bit patterns,
    so equal distances fall back to the smaller row index and every result
    is deterministic. Row indices fit the low 32 bits.
    """
    bits = squared.view(np.uint32).astype(np.uint64) << np.uint64(32)
    return bits | (rows.astype(np.uint64) & _LOW)


def _window(coords: NDArray[np.float32], order: NDArray[np.intp], k: int) -> NDArray[np.uint64]:
    """Take the k closest of the k predecessors and k successors along one order."""
    count = len(coords)
    ordered = coords[order]
    padded = np.pad(ordered, ((k, k), (0, 0)), constant_values=np.inf)
    padded_order = np.pad(order, (k, k), constant_values=-1)
    offsets = (*range(-k, 0), *range(1, k + 1))
    found = np.empty((count, k), dtype=np.uint64)
    for start in range(0, count, _BATCH_SIZE):
        stop = min(start + _BATCH_SIZE, count)
        here = ordered[start:stop]
        squared = np.empty((stop - start, 2 * k), dtype=np.float32)
        candidates = np.empty((stop - start, 2 * k), dtype=np.intp)
        for column, offset in enumerate(offsets):
            delta = here - padded[start + k + offset : stop + k + offset]
            squared[:, column] = np.einsum("ij,ij->i", delta, delta)
            candidates[:, column] = padded_order[start + k + offset : stop + k + offset]
        keys = _keys(squared, candidates)
        found[order[start:stop]] = np.partition(keys, k - 1, axis=1)[:, :k]
    return found


def _merge(found: NDArray[np.uint64], extra: NDArray[np.uint64]) -> None:
    """Keep each row's k closest of two candidate lists, counting shared neighbors once."""
    count, k = found.shape
    for start in range(0, count, _BATCH_SIZE):
        stop = min(start + _BATCH_SIZE, count)
        fresh = extra[start:stop].copy()
        known = ((fresh & _LOW)[:, :, None] == (found[start:stop] & _LOW)[:, None, :]).any(axis=2)
        fresh[known] = np.iinfo(np.uint64).max
        merged = np.concatenate([found[start:stop], fresh], axis=1)
        found[start:stop] = np.partition(merged, k - 1, axis=1)[:, :k]


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
        exact = _exact(unit, k)
        distances, indices, orders = exact.distances, exact.indices, ()
    else:
        coords = unit.astype(np.float32)
        orders = tuple(spatial_order(unit, shift) for shift in _SHIFTS)
        found = _window(coords, orders[0], k)
        for order in orders[1:]:
            _merge(found, _window(coords, order, k))
        indices = (found & _LOW).astype(np.intp)
        squared = (found >> np.uint64(32)).astype(np.uint32).view(np.float32)
        distances = np.sqrt(squared).astype(np.float64)
    with np.errstate(over="ignore"):
        scaled = np.minimum(distances * span, _FLOAT_MAX)
    return Neighbors(scaled, indices, orders)
