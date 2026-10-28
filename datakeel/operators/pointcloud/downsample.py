# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Retain the first complete point record in each source-unit voxel."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.pointcloud.artifacts import cloud_artifact
from datakeel.operators.pointcloud.io import load_cloud, select_cloud
from datakeel.operators.pointcloud.models import DownsampleParams


def voxel_indices(xyz: NDArray[np.float64], voxel_size: float) -> NDArray[np.intp]:
    """Find stable voxel representatives in O(N log N) time with bounded arrays."""
    finite_indices = np.flatnonzero(np.isfinite(xyz).all(axis=1))
    if not len(finite_indices):
        return finite_indices
    scaled = np.floor(xyz[finite_indices] / voxel_size)
    if np.abs(scaled).max() >= np.iinfo(np.int64).max:
        msg = "Coordinates exceed the representable voxel grid; increase voxel_size"
        raise ValidationError(msg)
    voxels = scaled.astype(np.int64)
    _, first = np.unique(voxels, axis=0, return_index=True)
    return np.sort(finite_indices[first])


def execute(files: list[FileItem], output_dir: Path, params: DownsampleParams) -> OperatorResult:
    """Downsample finite points deterministically, retaining all optional fields."""

    def thin(file: FileItem) -> FileItem:
        cloud = load_cloud(Path(file.path))
        selected = select_cloud(cloud, voxel_indices(cloud.xyz, params.voxel_size))
        return cloud_artifact(file, output_dir, selected, "pointcloud.downsample", (cloud, None))

    return summarize(files, [thin(file) for file in files])


OPERATOR = Operator("pointcloud.downsample", "point-cloud", "transform", DownsampleParams, execute)
