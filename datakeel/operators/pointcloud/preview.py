# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Render deterministic top-down height or intensity PNG side artifacts."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.errors import ValidationError
from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate
from datakeel.operators.image.helpers import image_artifact
from datakeel.operators.pointcloud.io import load_cloud
from datakeel.operators.pointcloud.models import PointCloud, PointCloudProbe, PreviewParams
from datakeel.operators.pointcloud.probe import file_probe_params, inspect_cloud


def render_preview(cloud: PointCloud, params: PreviewParams) -> NDArray[np.uint8]:
    """Project XY coordinates with a stable color ramp and bounded raster allocation."""
    xyz = cloud.xyz
    finite = np.isfinite(xyz).all(axis=1)
    xyz = xyz[finite]
    image = np.full((params.size, params.size, 3), (18, 24, 32), dtype=np.uint8)
    if not len(xyz):
        return image
    values = xyz[:, 2]
    if params.color_by == "intensity":
        if not any(field.name == "intensity" and field.count == 1 for field in cloud.fields):
            msg = "Intensity preview requires a scalar intensity field"
            raise ValidationError(msg)
        values = np.asarray(cloud.data["intensity"][finite], dtype=np.float64)
        values = np.nan_to_num(values, nan=0.0, posinf=0.0, neginf=0.0)
    low, high = xyz[:, :2].min(axis=0), xyz[:, :2].max(axis=0)
    scale = max(float((high - low).max()), np.finfo(np.float64).tiny)
    pixels = np.rint((xyz[:, :2] - low) / scale * (params.size - 1)).astype(np.intp)
    normalized = (values - values.min()) / max(float(np.ptp(values)), np.finfo(np.float64).tiny)
    levels = np.full(params.size * params.size, -1.0)
    np.maximum.at(levels, (params.size - 1 - pixels[:, 1]) * params.size + pixels[:, 0], normalized)
    occupied = levels >= 0
    ramp = levels[occupied]
    image.reshape(-1, 3)[occupied] = np.column_stack(
        (255 * ramp, 180 * (1 - ramp), 255 * (1 - ramp))
    ).astype(np.uint8)
    return image


def execute(files: list[FileItem], output_dir: Path, params: PreviewParams) -> OperatorResult:
    """Keep point-cloud slots intact and attach a separately materialized PNG reference."""

    def render(file: FileItem) -> FileItem:
        cloud = load_cloud(Path(file.path))
        policy = file_probe_params(file)
        probe = (
            PointCloudProbe.model_validate(file.metadata["pointcloud_probe"])
            if "pointcloud_probe" in file.metadata
            else inspect_cloud(cloud, policy)
        )
        raster = render_preview(cloud, params)
        preview = image_artifact(
            file.model_copy(update={"modality": "image"}), output_dir, raster, "png"
        )
        return annotate(
            file,
            pointcloud_probe=probe.model_dump(mode="json"),
            pointcloud_probe_params=policy.model_dump(mode="json"),
            pointcloud_preview={
                "artifact_id": preview.id,
                "path": preview.path,
                "filename": preview.filename,
                "sha256": preview.sha256,
                "size": preview.size,
                "width": params.size,
                "height": params.size,
            },
        )

    output = [render(file) for file in files]
    return OperatorResult(
        files=output, quality={"input_count": len(files), "output_count": len(output)}
    )


OPERATOR = Operator("pointcloud.preview", "point-cloud", "visualization", PreviewParams, execute)
