# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Flag source extents that may indicate millimeters being interpreted as meters."""

from pathlib import Path

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate, summarize
from datakeel.operators.pointcloud.io import load_cloud
from datakeel.operators.pointcloud.models import UnitCheckParams
from datakeel.operators.pointcloud.probe import file_probe_params, inspect_cloud, unit_suspicion


def execute(files: list[FileItem], _output_dir: Path, params: UnitCheckParams) -> OperatorResult:
    """Report unit suspicion conservatively without guessing a coordinate conversion."""
    probes = [inspect_cloud(load_cloud(Path(file.path)), file_probe_params(file)) for file in files]
    extents = sorted(item.body_extent for item in probes if item.body_extent > 0)
    reference = params.reference_extent
    if reference is None and len(extents) > 1:
        reference = float(np.median(extents[: max(1, (len(extents) + 1) // 2)]))
    output: list[FileItem] = []
    for file, measured in zip(files, probes, strict=True):
        policy = file_probe_params(file).model_copy(
            update={
                "expected_max_extent": params.expected_max_extent,
                "reference_extent": reference,
                "scale_ratio": params.scale_ratio,
                "scale_tolerance": params.scale_tolerance,
            }
        )
        suspected, reason = unit_suspicion(measured.body_extent, policy)
        probe = measured.model_copy(update={"unit_suspected": suspected, "unit_reason": reason})
        output.append(
            annotate(
                file,
                pointcloud_probe=probe.model_dump(mode="json"),
                pointcloud_probe_params=policy.model_dump(mode="json"),
                pointcloud_unit_check={
                    "suspected": probe.unit_suspected,
                    "reason": probe.unit_reason,
                    "expected_max_extent": params.expected_max_extent,
                    "reference_extent": reference,
                    "suggested_scale": 1 / policy.scale_ratio if probe.unit_suspected else None,
                    "coordinates_changed": False,
                },
            )
        )
    return summarize(files, output)


OPERATOR = Operator("pointcloud.unit_check", "point-cloud", "validation", UnitCheckParams, execute)
