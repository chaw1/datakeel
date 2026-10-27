# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded statistical neighbor distances with deterministic spatial ordering."""

import numpy as np
from numpy.typing import NDArray

_EXACT_LIMIT = 2048
_BATCH_SIZE = 16384
_MORTON_BITS = 20
_MIN_NEIGHBOR_POINTS = 2
_MIN_STATISTICAL_POINTS = 3


def _interleave(values: NDArray[np.uint64]) -> NDArray[np.uint64]:
    values = (values | (values << np.uint64(32))) & np.uint64(0x1F00000000FFFF)
    values = (values | (values << np.uint64(16))) & np.uint64(0x1F0000FF0000FF)
    values = (values | (values << np.uint64(8))) & np.uint64(0x100F00F00F00F00F)
    values = (values | (values << np.uint64(4))) & np.uint64(0x10C30C30C30C30C3)
    return (values | (values << np.uint64(2))) & np.uint64(0x1249249249249249)


def spatial_order(xyz: NDArray[np.float64]) -> NDArray[np.intp]:
    """Sort into a Morton locality curve using bounded 20-bit coordinates."""
    low, high = xyz.min(axis=0), xyz.max(axis=0)
    scale = np.maximum(high - low, np.finfo(np.float64).tiny)
    grid = np.floor(np.clip((xyz - low) / scale, 0, 1) * ((1 << _MORTON_BITS) - 1))
    unsigned = grid.astype(np.uint64)
    codes = _interleave(unsigned[:, 0])
    codes |= _interleave(unsigned[:, 1]) << np.uint64(1)
    codes |= _interleave(unsigned[:, 2]) << np.uint64(2)
    return np.argsort(codes, kind="stable")


def _exact_scores(xyz: NDArray[np.float64], neighbors: int) -> NDArray[np.float64]:
    scores = np.empty(len(xyz), dtype=np.float64)
    for start in range(0, len(xyz), _BATCH_SIZE // 32):
        stop = min(start + _BATCH_SIZE // 32, len(xyz))
        delta = xyz[start:stop, None, :] - xyz[None, :, :]
        distances = np.einsum("ijk,ijk->ij", delta, delta)
        distances[np.arange(stop - start), np.arange(start, stop)] = np.inf
        closest = np.partition(distances, neighbors - 1, axis=1)[:, :neighbors]
        scores[start:stop] = np.sqrt(closest).mean(axis=1)
    return scores


def neighbor_distances(xyz: NDArray[np.float64], neighbors: int = 16) -> NDArray[np.float64]:
    """Measure exact small-cloud or bounded Morton-window approximate kNN distances.

    Large clouds search up to twice k spatially adjacent candidates on each
    side. This deterministic approximation avoids quadratic memory and work;
    it can retain some isolated points near Morton discontinuities.
    """
    if len(xyz) < _MIN_NEIGHBOR_POINTS:
        return np.zeros(len(xyz), dtype=np.float64)
    neighbors = min(neighbors, len(xyz) - 1)
    if len(xyz) <= _EXACT_LIMIT:
        return _exact_scores(xyz, neighbors)
    order = spatial_order(xyz)
    ordered, result = xyz[order], np.empty(len(xyz), dtype=np.float64)
    window = min(neighbors * 2, len(xyz) - 1)
    padded = np.pad(ordered, ((window, window), (0, 0)), constant_values=np.inf)
    for start in range(0, len(xyz), _BATCH_SIZE):
        stop = min(start + _BATCH_SIZE, len(xyz))
        distances = np.full((stop - start, window * 2), np.inf, dtype=np.float64)
        for column, offset in enumerate((*range(-window, 0), *range(1, window + 1))):
            delta = ordered[start:stop] - padded[start + window + offset : stop + window + offset]
            distances[:, column] = np.einsum("ij,ij->i", delta, delta)
        closest = np.partition(distances, neighbors - 1, axis=1)[:, :neighbors]
        result[order[start:stop]] = np.sqrt(closest).mean(axis=1)
    return result


def outlier_mask(
    xyz: NDArray[np.float64], neighbors: int = 16, distance_ratio: float = 4.0
) -> NDArray[np.bool_]:
    """Mark nonfinite rows and mean-neighbor distances far above the typical spacing.

    The scale is the median mean-neighbor distance, which stays representative
    while fewer than half of the points are outliers. A mean-plus-deviation
    threshold always rejects the boundary tail of a clean scan and is inflated
    by heavy contamination. When most points repeat exactly, the mean replaces
    the zero median so isolated points are still compared with real spacing.
    """
    finite = np.isfinite(xyz).all(axis=1)
    result = ~finite
    if finite.sum() < _MIN_STATISTICAL_POINTS:
        return result
    distances = neighbor_distances(xyz[finite], neighbors)
    scale = float(np.median(distances)) or float(distances.mean())
    if scale > 0:
        result[finite] = distances > distance_ratio * scale
    return result
