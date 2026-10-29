# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Remove local-density outliers and separated clusters with bounded NumPy work."""

from pathlib import Path

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult
from datakeel.operators.pointcloud.artifacts import cloud_artifact
from datakeel.operators.pointcloud.batch import each_file
from datakeel.operators.pointcloud.io import load_cloud, select_cloud
from datakeel.operators.pointcloud.models import OutlierParams
from datakeel.operators.pointcloud.probe import file_probe_params
from datakeel.operators.pointcloud.statistics import analyse


def execute(files: list[FileItem], output_dir: Path, params: OutlierParams) -> OperatorResult:
    """Drop invalid rows, locally isolated points and separated small clusters."""

    def reusable(file: FileItem) -> bool:
        return file_probe_params(file).statistics() == params.statistics()

    def remove(file: FileItem) -> FileItem:
        cloud = load_cloud(Path(file.path))
        xyz = cloud.xyz
        finite = np.isfinite(xyz).all(axis=1)
        analysis = analyse(xyz[finite], params)
        keep = finite.copy()
        keep[finite] = ~analysis.mask
        return cloud_artifact(
            file,
            output_dir,
            select_cloud(cloud, keep),
            "pointcloud.outliers",
            (cloud, analysis if finite.all() and reusable(file) else None),
        )

    return each_file(files, "pointcloud.outliers", remove)


OPERATOR = Operator("pointcloud.outliers", "point-cloud", "transform", OutlierParams, execute)
