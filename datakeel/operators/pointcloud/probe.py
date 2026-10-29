# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Inspect point-cloud geometry and attach typed, serializable quality evidence."""

from math import sqrt
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from datakeel.core.models import FileItem
from datakeel.operators.base import Operator, OperatorResult, annotate
from datakeel.operators.pointcloud.batch import each_file
from datakeel.operators.pointcloud.io import load_cloud
from datakeel.operators.pointcloud.models import (
    BoundingBox,
    PointCloud,
    PointCloudProbe,
    ProbeParams,
)
from datakeel.operators.pointcloud.neighbors import normalize, spatial_order
from datakeel.operators.pointcloud.statistics import OutlierAnalysis, analyse

FULL_LIMIT = 500_000
_SAMPLE_SEED = 18
_WILSON_Z = 1.959963984540054
_FLOAT_MAX = float(np.finfo(np.float64).max)


def stratified_sample(xyz: NDArray[np.float64], limit: int) -> NDArray[np.intp]:
    """Pick one seeded random point from each of ``limit`` equal Morton-order strata.

    Spatial strata keep every region represented in proportion to its points,
    and the random pick inside each stratum avoids the aliasing that a fixed
    index stride produces on scan-ordered files.
    """
    order = spatial_order(normalize(xyz)[0])
    bounds = np.linspace(0, len(xyz), limit + 1).astype(np.intp)
    sizes = np.diff(bounds)
    offsets = np.floor(np.random.default_rng(_SAMPLE_SEED).random(limit) * sizes).astype(np.intp)
    return np.sort(order[bounds[:-1] + offsets])


def wilson_interval(flagged: int, total: int) -> tuple[float, float]:
    """Return the 95% Wilson score interval of a sampled proportion."""
    if total == 0:
        return 0.0, 0.0
    ratio = flagged / total
    scale = 1 + _WILSON_Z**2 / total
    center = (ratio + _WILSON_Z**2 / (2 * total)) / scale
    margin = _WILSON_Z * sqrt(ratio * (1 - ratio) / total + _WILSON_Z**2 / (4 * total**2)) / scale
    low = 0.0 if flagged == 0 else max(0.0, center - margin)
    high = 1.0 if flagged == total else min(1.0, center + margin)
    return low, high


def _body_geometry(body: NDArray[np.float64], points: float) -> tuple[float, float]:
    """Return a finite main-body extent and density for any finite coordinates.

    Extreme but finite values, such as byte-swapped doubles, can overflow an
    extent or underflow a volume to zero. Both are clamped so measurements stay
    JSON-compliant and density never divides by an exact zero.
    """
    if not len(body):
        return 0.0, 0.0
    with np.errstate(over="ignore", under="ignore"):
        extent = np.minimum(body.max(axis=0) - body.min(axis=0), _FLOAT_MAX)
        volume = float(np.prod(np.where(extent > 0, extent, 1.0)))
    density = min(points / volume, _FLOAT_MAX) if volume > 0 else _FLOAT_MAX
    return float(extent.max()), density


def unit_suspicion(extent: float, params: ProbeParams) -> tuple[bool, str | None]:
    """Flag a main body larger than any single capture of the declared sensor form."""
    if extent > params.max_extent():
        return True, "extent_exceeds_expected_maximum_possible_millimeters"
    return False, None


def unit_hint(extent: float, params: ProbeParams) -> str | None:
    """Note a near-thousandfold extent difference from the batch without judging units.

    A batch can legitimately mix a small part and a whole room, so this is
    only a hint for review and never a defect on its own. An extent already
    suspected on its own needs no second note.
    """
    if params.reference_extent is None or extent <= 0 or extent > params.max_extent():
        return None
    ratio = extent / params.reference_extent
    low = params.scale_ratio / params.scale_tolerance
    high = params.scale_ratio * params.scale_tolerance
    if low <= ratio <= high or low <= 1 / ratio <= high:
        return "batch_extent_ratio_possible_unit_mismatch"
    return None


def _measurements(
    valid: NDArray[np.float64], sample: NDArray[np.float64], measured: OutlierAnalysis
) -> dict[str, float | int | bool]:
    sampled = len(sample) < len(valid)
    flagged = int(measured.mask.sum())
    ratio = flagged / max(1, len(sample))
    low, high = wilson_interval(flagged, len(sample)) if sampled else (ratio, ratio)
    body = sample[~measured.mask]
    extent, density = _body_geometry(body, len(valid) * (1 - ratio))
    nearest = measured.nearest[~measured.mask]
    # A uniform sample of a surface widens its spacing by the square root of
    # the sampling fraction; undo that so sampled and full files compare.
    spacing = float(np.median(nearest)) * sqrt(len(sample) / len(valid)) if len(nearest) else 0.0
    return {
        "outlier_ratio": ratio,
        "outlier_sample_count": len(sample),
        "outlier_sampled": sampled,
        "outlier_ci_low": low,
        "outlier_ci_high": high,
        "isolated_count": int(measured.isolated.sum()),
        "clustered_count": int((measured.clustered & ~measured.isolated).sum()),
        "spacing": spacing,
        "relative_spacing": min(spacing / extent, _FLOAT_MAX) if extent > 0 else 0.0,
        "body_extent": extent,
        "density": density,
    }


def inspect_cloud(
    cloud: PointCloud, params: ProbeParams | None = None, analysis: OutlierAnalysis | None = None
) -> PointCloudProbe:
    """Measure finite coverage, invalid rows, local outliers, spacing and unit plausibility.

    Up to ``FULL_LIMIT`` finite points are analysed in full; larger clouds use
    a seeded, spatially stratified sample and report a 95% interval. Extent,
    spacing and density describe the main body without outliers, so a few
    stray points cannot make a dense scan look sparse or mis-scaled. Spacing
    is relative to the extent and therefore independent of the unit.
    A caller that already analysed every finite row may pass that analysis.
    Coordinates are never rescaled.
    """
    selected = params or ProbeParams()
    xyz = cloud.xyz
    finite = np.isfinite(xyz).all(axis=1)
    valid = xyz[finite]
    invalid_count = int((~finite).sum())
    if analysis is None:
        rows = stratified_sample(valid, FULL_LIMIT) if len(valid) > FULL_LIMIT else None
        sample = valid if rows is None else valid[rows]
        measured = _measurements(valid, sample, analyse(sample, selected))
    else:
        measured = _measurements(valid, valid, analysis)
    bounds = None
    if len(valid):
        bounds = BoundingBox(
            min=tuple(valid.min(axis=0).tolist()), max=tuple(valid.max(axis=0).tolist())
        )
    suspected, unit_reason = unit_suspicion(float(measured["body_extent"]), selected)
    return PointCloudProbe.model_validate(
        {
            **measured,
            "format": cloud.format,
            "encoding": cloud.encoding,
            "point_count": len(xyz),
            "fields": [field.name for field in cloud.fields],
            "bounding_box": bounds,
            "nan_count": int(np.isnan(xyz).any(axis=1).sum()),
            "inf_count": int(np.isinf(xyz).any(axis=1).sum()),
            "invalid_count": invalid_count,
            "invalid_ratio": invalid_count / max(1, len(xyz)),
            "sensor": selected.sensor,
            "spacing_limit": selected.spacing_limit(),
            "sparse_penalized": selected.sparse_penalized(),
            "unit_suspected": suspected,
            "unit_reason": unit_reason,
            "unit_hint": unit_hint(float(measured["body_extent"]), selected),
        }
    )


def file_probe_params(file: FileItem) -> ProbeParams:
    """Recover the validated measurement policy associated with source metadata."""
    return ProbeParams.model_validate(file.metadata.get("pointcloud_probe_params", {}))


def execute(files: list[FileItem], _output_dir: Path, params: ProbeParams) -> OperatorResult:
    """Annotate source files with current probe results without modifying bytes."""

    def probe(file: FileItem) -> FileItem:
        measured = inspect_cloud(load_cloud(Path(file.path)), params)
        return annotate(
            file,
            pointcloud_probe=measured.model_dump(mode="json"),
            pointcloud_probe_params=params.model_dump(mode="json"),
        )

    return each_file(files, "pointcloud.probe", probe)


OPERATOR = Operator("pointcloud.probe", "point-cloud", "quality", ProbeParams, execute)
