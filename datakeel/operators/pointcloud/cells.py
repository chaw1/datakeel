# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Exact nearby-point queries that only visit the Morton cells around a group of points."""

from math import ceil, log2
from typing import NamedTuple

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.neighbors import CELL_COUNT, MORTON_BITS, encode, grid_cells

_STEP = 2.0 / CELL_COUNT
_OFFSETS = np.array([(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1)])
_BLOCK = 512


class CellIndex(NamedTuple):
    """Hold every point's grid cell and the points sorted by Morton code."""

    cells: NDArray[np.uint64]
    codes: NDArray[np.uint64]
    order: NDArray[np.intp]


def cell_index(unit: NDArray[np.float64]) -> CellIndex:
    """Index coordinates normalized to [0, 1] on the unshifted Morton grid."""
    cells = grid_cells(unit)
    codes = encode(cells)
    order = np.argsort(codes, kind="stable")
    return CellIndex(cells, codes[order], order)


def _nearby(index: CellIndex, members: NDArray[np.intp], radius: float) -> NDArray[np.intp]:
    """Return every point in the cells around members on a grid at least radius wide.

    Cells of the coarsest grid whose width reaches the radius are prefixes of
    the Morton code, so each one is a contiguous range of the sorted codes and
    any point within the radius of a member lies in one of the 27 cells
    around that member's cell.
    """
    drop = min(MORTON_BITS, max(0, ceil(log2(max(radius / _STEP, 1.0)))))
    coarse = np.unique((index.cells[members] >> np.uint64(drop)).astype(np.int64), axis=0)
    around = np.unique((coarse[:, None, :] + _OFFSETS[None]).reshape(-1, 3), axis=0)
    around = around[((around >= 0) & (around <= CELL_COUNT >> drop)).all(axis=1)]
    prefix = encode(around.astype(np.uint64)) << np.uint64(3 * drop)
    start = np.searchsorted(index.codes, prefix, side="left")
    stop = np.searchsorted(index.codes, prefix + (np.uint64(1) << np.uint64(3 * drop)))
    sizes = stop - start
    positions = np.repeat(start - np.cumsum(sizes) + sizes, sizes) + np.arange(sizes.sum())
    return index.order[positions]


def isolated_group(
    index: CellIndex,
    unit: NDArray[np.float64],
    members: NDArray[np.intp],
    labels: NDArray[np.intp],
    radius: float,
) -> bool:
    """Return whether no point outside the members' component lies within radius of them."""
    nearby = _nearby(index, members, radius)
    points = unit[members]
    low, high = points.min(axis=0) - radius, points.max(axis=0) + radius
    inside = ((unit[nearby] >= low) & (unit[nearby] <= high)).all(axis=1)
    nearby = nearby[inside & (labels[nearby] != labels[members[0]])]
    for start in range(0, len(nearby), _BLOCK):
        other = unit[nearby[start : start + _BLOCK]]
        for first in range(0, len(points), _BLOCK):
            delta = points[first : first + _BLOCK, None, :] - other[None, :, :]
            if (np.einsum("ijk,ijk->ij", delta, delta) <= radius * radius).any():
                return False
    return True
