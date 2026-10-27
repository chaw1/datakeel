# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Remove nonfinite coordinates and clip point clouds to inclusive bounds."""

from pathlib import Path

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.pointcloud.artifacts import cloud_artifact
from datakeel.operators.pointcloud.io import load_cloud, select_cloud
from datakeel.operators.pointcloud.models import CleanParams


def execute(files: list[FileItem], output_dir: Path, params: CleanParams) -> OperatorResult:
    """Filter aligned rows without losing intensity, color, labels or numeric types."""
    output: list[FileItem] = []
    for file in files:
        cloud = load_cloud(Path(file.path))
        xyz = cloud.xyz
        keep = np.isfinite(xyz).all(axis=1) if params.remove_invalid else np.ones(len(xyz), bool)
        if params.min_bound is not None:
            keep &= (xyz >= params.min_bound).all(axis=1)
        if params.max_bound is not None:
            keep &= (xyz <= params.max_bound).all(axis=1)
        output.append(
            cloud_artifact(
                file, output_dir, select_cloud(cloud, keep), "pointcloud.clean", len(xyz)
            )
        )
    return summarize(files, output)


OPERATOR = Operator("pointcloud.clean", "point-cloud", "transform", CleanParams, execute)
