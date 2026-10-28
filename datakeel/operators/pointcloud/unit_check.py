# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Flag source extents that may indicate millimeters being interpreted as meters."""

from pathlib import Path

import numpy as np

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate, summarize
from datakeel.operators.pointcloud.io import load_cloud
from datakeel.operators.pointcloud.models import PointCloudProbe, ProbeParams, UnitCheckParams
from datakeel.operators.pointcloud.probe import (
    file_probe_params,
    inspect_cloud,
    unit_hint,
    unit_suspicion,
)

_MIN_BATCH = 2


def _measured(file: FileItem) -> PointCloudProbe:
    """Reuse the probe recorded with its policy instead of measuring again."""
    recorded = file.metadata.get("pointcloud_probe")
    if isinstance(recorded, dict) and "pointcloud_probe_params" in file.metadata:
        return PointCloudProbe.model_validate(recorded)
    return inspect_cloud(load_cloud(Path(file.path)), file_probe_params(file))


def _reference(probes: list[PointCloudProbe], params: UnitCheckParams) -> float | None:
    """Use the explicit reference or the median of the smaller half of the batch."""
    extents = sorted(item.body_extent for item in probes if item.body_extent > 0)
    if params.reference_extent is not None or len(extents) < _MIN_BATCH:
        return params.reference_extent
    return float(np.median(extents[: max(1, (len(extents) + 1) // 2)]))


def _suggested_scale(extent: float, policy: ProbeParams, *, hint: str | None) -> float | None:
    """Name the factor that would undo the suspected mismatch, without applying it."""
    if extent > policy.max_extent():
        return 1 / policy.scale_ratio
    if hint is None or policy.reference_extent is None:
        return None
    return 1 / policy.scale_ratio if extent > policy.reference_extent else policy.scale_ratio


def _checked(
    file: FileItem, measured: PointCloudProbe, params: UnitCheckParams, reference: float | None
) -> FileItem:
    recorded = file_probe_params(file)
    policy = recorded.model_copy(
        update={
            "expected_max_extent": params.expected_max_extent or recorded.expected_max_extent,
            "reference_extent": reference,
            "scale_ratio": params.scale_ratio,
            "scale_tolerance": params.scale_tolerance,
        }
    )
    suspected, reason = unit_suspicion(measured.body_extent, policy)
    hint = unit_hint(measured.body_extent, policy)
    probe = measured.model_copy(
        update={"unit_suspected": suspected, "unit_reason": reason, "unit_hint": hint}
    )
    return annotate(
        file,
        pointcloud_probe=probe.model_dump(mode="json"),
        pointcloud_probe_params=policy.model_dump(mode="json"),
        pointcloud_unit_check={
            "suspected": suspected,
            "reason": reason,
            "hint": hint,
            "expected_max_extent": policy.max_extent(),
            "reference_extent": reference,
            "suggested_scale": _suggested_scale(measured.body_extent, policy, hint=hint),
            "coordinates_changed": False,
        },
    )


def execute(files: list[FileItem], _output_dir: Path, params: UnitCheckParams) -> OperatorResult:
    """Report unit suspicion and batch-scale hints without guessing a conversion.

    Only an extent beyond the plausible maximum of the declared sensor form is
    a suspicion. A near-thousandfold difference from the rest of the batch is
    recorded as a hint, because mixed-scale batches are legitimate.
    """
    measured = [_measured(file) for file in files]
    reference = _reference(measured, params)
    return summarize(
        files,
        [
            _checked(file, probe, params, reference)
            for file, probe in zip(files, measured, strict=True)
        ],
    )


OPERATOR = Operator("pointcloud.unit_check", "point-cloud", "validation", UnitCheckParams, execute)
