# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Create schema-preserving point-cloud artifacts with source quality attribution."""

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pydantic import JsonValue

from datakeel.core.models import FileItem
from datakeel.operators.base import artifact
from datakeel.operators.pointcloud.io import dump_cloud
from datakeel.operators.pointcloud.models import PointCloud
from datakeel.operators.pointcloud.probe import file_probe_params, inspect_cloud
from datakeel.operators.pointcloud.statistics import OutlierAnalysis


def cloud_artifact(
    file: FileItem,
    output_dir: Path,
    cloud: PointCloud,
    operator: str,
    source: tuple[PointCloud, OutlierAnalysis | None],
) -> FileItem:
    """Write transformed rows with refreshed quality and the earliest source probe.

    ``source`` is the loaded input and, when the operator already analysed
    all of its finite rows, that analysis; the source is only measured again
    when no earlier probe was recorded and no analysis is available.
    """
    params = file_probe_params(file)
    probe = inspect_cloud(cloud, params).model_dump(mode="json")
    original = file.metadata.get("pointcloud_probe")
    if original is None:
        original = inspect_cloud(source[0], params, source[1]).model_dump(mode="json")
    input_points = len(source[0].data)
    earliest: JsonValue = file.metadata.get("source_pointcloud_probe", original)
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
        source_pointcloud_probe=earliest,
        pointcloud_processing={
            "operator": operator,
            "input_points": input_points,
            "output_points": len(cloud.data),
            "removed_count": removed,
            "removed_ratio": removed / max(1, input_points),
        },
    )
