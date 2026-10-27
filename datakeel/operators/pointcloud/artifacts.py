# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create schema-preserving point-cloud artifacts with source quality attribution."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

from datakeel.core.models import FileItem
from datakeel.operators.base import artifact
from datakeel.operators.pointcloud.io import dump_cloud, load_cloud
from datakeel.operators.pointcloud.models import PointCloud
from datakeel.operators.pointcloud.probe import file_probe_params, inspect_cloud


def cloud_artifact(
    file: FileItem, output_dir: Path, cloud: PointCloud, operator: str, input_points: int
) -> FileItem:
    """Write transformed rows with refreshed quality and the earliest source probe."""
    params = file_probe_params(file)
    probe = inspect_cloud(cloud, params).model_dump(mode="json")
    original = file.metadata.get("pointcloud_probe")
    if original is None:
        original = inspect_cloud(load_cloud(Path(file.path)), params).model_dump(mode="json")
    source: JsonValue = file.metadata.get("source_pointcloud_probe", original)
    removed = input_points - len(cloud.data)
    refreshed = file.model_copy(
        update={
            "metadata": {
                key: value
                for key, value in file.metadata.items()
                if key not in {"pointcloud_preview", "pointcloud_unit_check"}
            }
        }
    )
    return artifact(
        refreshed,
        output_dir,
        dump_cloud(cloud),
        cloud.format,
        pointcloud_probe=probe,
        pointcloud_probe_params=params.model_dump(mode="json"),
        source_pointcloud_probe=source,
        pointcloud_processing={
            "operator": operator,
            "input_points": input_points,
            "output_points": len(cloud.data),
            "removed_count": removed,
            "removed_ratio": removed / max(1, input_points),
        },
    )
