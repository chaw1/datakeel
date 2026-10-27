# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Remove statistical neighbor-distance outliers with bounded NumPy work."""

from pathlib import Path

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, summarize
from datakeel.operators.pointcloud.artifacts import cloud_artifact
from datakeel.operators.pointcloud.io import load_cloud, select_cloud
from datakeel.operators.pointcloud.models import OutlierParams
from datakeel.operators.pointcloud.statistics import outlier_mask


def execute(files: list[FileItem], output_dir: Path, params: OutlierParams) -> OperatorResult:
    """Drop invalid points and points far sparser than the cloud's median spacing."""
    output: list[FileItem] = []
    for file in files:
        cloud = load_cloud(Path(file.path))
        reject = outlier_mask(cloud.xyz, params.neighbors, params.distance_ratio)
        output.append(
            cloud_artifact(
                file,
                output_dir,
                select_cloud(cloud, ~reject),
                "pointcloud.outliers",
                len(cloud.data),
            )
        )
    return summarize(files, output)


OPERATOR = Operator("pointcloud.outliers", "point-cloud", "transform", OutlierParams, execute)
