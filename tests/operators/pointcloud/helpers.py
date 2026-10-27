# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Generate portable structured point records without external fixture data."""

import numpy as np
from numpy.typing import NDArray

from datakeel.operators.pointcloud.models import CloudField, Encoding, PointCloud


def make_cloud(xyz: NDArray[np.float64], encoding: Encoding = "binary_little_endian") -> PointCloud:
    """Create labeled points with independently testable intensity and packed colors."""
    fields = tuple(
        CloudField(name=name, dtype=dtype)
        for name, dtype in (
            ("x", "f8"),
            ("y", "f8"),
            ("z", "f8"),
            ("intensity", "f4"),
            ("rgb", "u4"),
            ("label", "u2"),
        )
    )
    data = np.empty(len(xyz), dtype=[(field.name, field.dtype) for field in fields])
    for index, name in enumerate(("x", "y", "z")):
        data[name] = xyz[:, index]
    data["intensity"] = np.arange(len(xyz)) * 0.25
    data["rgb"] = np.arange(len(xyz)) + 0xFF2030
    data["label"] = np.arange(len(xyz)) % 32
    return PointCloud(format="ply", encoding=encoding, fields=fields, data=data)
