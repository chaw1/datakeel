# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect point-cloud geometry and attach typed, serializable quality evidence."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate, summarize
from datakeel.operators.pointcloud.io import load_cloud
from datakeel.operators.pointcloud.models import (
    BoundingBox,
    PointCloud,
    PointCloudProbe,
    ProbeParams,
)
from datakeel.operators.pointcloud.statistics import outlier_mask

_SAMPLE_LIMIT = 8192
_FLOAT_MAX = float(np.finfo(np.float64).max)


def _body_geometry(body: NDArray[np.float64], points: float) -> tuple[float, float]:
    """Return a finite main-body extent and density for any finite coordinates.

    Extreme but finite values, such as byte-swapped doubles, can overflow an
    extent or underflow a volume to zero. Both are clamped so measurements stay
    JSON-compliant and density never divides by an exact zero.
    """
    with np.errstate(over="ignore", under="ignore"):
        extent = np.minimum(body.max(axis=0) - body.min(axis=0), _FLOAT_MAX)
        volume = float(np.prod(np.where(extent > 0, extent, 1.0)))
    density = min(points / volume, _FLOAT_MAX) if volume > 0 else _FLOAT_MAX
    return float(extent.max()), density


def unit_suspicion(extent: float, params: ProbeParams) -> tuple[bool, str | None]:
    """Flag absolute implausibility or a near-thousandfold batch scale difference."""
    if extent > params.expected_max_extent:
        return True, "extent_exceeds_expected_maximum_possible_millimeters"
    if params.reference_extent is not None:
        ratio = extent / params.reference_extent
        if (
            params.scale_ratio / params.scale_tolerance
            <= ratio
            <= (params.scale_ratio * params.scale_tolerance)
        ):
            return True, "batch_extent_ratio_possible_unit_mismatch"
    return False, None


def inspect_cloud(cloud: PointCloud, params: ProbeParams | None = None) -> PointCloudProbe:
    """Measure finite coverage, invalid rows and conservative unit suspicion.

    The bounding box covers every finite point. Density and the unit extent
    describe the main body: estimated outliers are excluded so a few distant
    stray points cannot make a dense scan look sparse or mis-scaled. Density
    uses a unit-width floor on degenerate axes so planar and linear clouds
    remain measurable. Coordinates are never silently rescaled.
    """
    selected = params or ProbeParams()
    xyz = cloud.xyz
    finite = np.isfinite(xyz).all(axis=1)
    valid = xyz[finite]
    invalid_count = int((~finite).sum())
    sample = valid[np.linspace(0, len(valid) - 1, min(len(valid), _SAMPLE_LIMIT), dtype=np.intp)]
    outliers = outlier_mask(sample, selected.neighbors, selected.distance_ratio)
    outlier_ratio = int(outliers.sum()) / max(1, len(sample))
    bounds, density, body_extent, suspected, unit_reason = None, 0.0, 0.0, False, None
    if len(valid):
        bounds = BoundingBox(
            min=tuple(valid.min(axis=0).tolist()), max=tuple(valid.max(axis=0).tolist())
        )
        body_extent, density = _body_geometry(sample[~outliers], len(valid) * (1 - outlier_ratio))
        suspected, unit_reason = unit_suspicion(body_extent, selected)
    return PointCloudProbe(
        format=cloud.format,
        encoding=cloud.encoding,
        point_count=len(xyz),
        fields=[field.name for field in cloud.fields],
        bounding_box=bounds,
        density=density,
        nan_count=int(np.isnan(xyz).any(axis=1).sum()),
        inf_count=int(np.isinf(xyz).any(axis=1).sum()),
        invalid_count=invalid_count,
        invalid_ratio=invalid_count / max(1, len(xyz)),
        outlier_ratio=outlier_ratio,
        outlier_sample_count=len(sample),
        body_extent=body_extent,
        unit_suspected=suspected,
        unit_reason=unit_reason,
    )


def file_probe_params(file: FileItem) -> ProbeParams:
    """Recover the validated measurement policy associated with source metadata."""
    return ProbeParams.model_validate(file.metadata.get("pointcloud_probe_params", {}))


def execute(files: list[FileItem], _output_dir: Path, params: ProbeParams) -> OperatorResult:
    """Annotate source files with current probe results without modifying bytes."""
    output: list[FileItem] = []
    for file in files:
        probe = inspect_cloud(load_cloud(Path(file.path)), params)
        output.append(
            annotate(
                file,
                pointcloud_probe=probe.model_dump(mode="json"),
                pointcloud_probe_params=params.model_dump(mode="json"),
            )
        )
    return summarize(files, output)


OPERATOR = Operator("pointcloud.probe", "point-cloud", "quality", ProbeParams, execute)
