# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Bounded point-cloud file IO and schema-preserving row selection."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.errors import ValidationError
from datakeel.operators.pointcloud import pcd, ply
from datakeel.operators.pointcloud.codec import MAX_FILE_BYTES
from datakeel.operators.pointcloud.models import Encoding, PointCloud


def load_cloud(path: Path) -> PointCloud:
    """Detect supported point-cloud formats from content instead of filename alone."""
    if path.stat().st_size > MAX_FILE_BYTES:
        msg = f"Encoded point cloud exceeds {MAX_FILE_BYTES} bytes"
        raise ValidationError(msg)
    content = path.read_bytes()
    if content.startswith((b"ply\n", b"ply\r\n")):
        return ply.loads(content)
    return pcd.loads(content)


def dump_cloud(cloud: PointCloud, encoding: Encoding | None = None) -> bytes:
    """Encode a cloud in its original file format unless encoding is overridden."""
    return ply.dumps(cloud, encoding) if cloud.format == "ply" else pcd.dumps(cloud, encoding)


def select_cloud(cloud: PointCloud, indices: NDArray[np.bool_] | NDArray[np.intp]) -> PointCloud:
    """Select aligned rows while preserving field order, widths and source encoding."""
    return PointCloud(
        format=cloud.format, encoding=cloud.encoding, fields=cloud.fields, data=cloud.data[indices]
    )
