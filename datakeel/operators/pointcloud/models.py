# Copyright 2026 Datakeel contributors
# SPDX-License-Identifier: Apache-2.0

"""Frozen point-cloud interchange and parameter contracts."""

from typing import Literal, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import ConfigDict, Field, field_validator, model_validator

from datakeel.core.errors import ValidationError
from datakeel.core.models import BoundaryModel
from datakeel.operators.base import Params

Encoding = Literal["ascii", "binary_little_endian", "binary_big_endian", "binary"]


class CloudField(BoundaryModel):
    """Preserve the scalar dtype and optional vector width of each source field."""

    name: str
    dtype: str
    count: int = Field(default=1, ge=1, le=1024)


class PointCloud(BoundaryModel):
    """Carry a read-only structured array without lossy numeric conversion."""

    model_config = ConfigDict(extra="forbid", frozen=True, arbitrary_types_allowed=True)
    format: Literal["ply", "pcd"]
    encoding: Encoding
    fields: tuple[CloudField, ...]
    data: NDArray[np.void]

    @model_validator(mode="after")
    def valid(self) -> "PointCloud":
        """Reject unstructured arrays and absent coordinate fields."""
        names = tuple(field.name for field in self.fields)
        if self.data.ndim != 1 or self.data.dtype.names != names:
            msg = "Point-cloud data must match its structured field schema"
            raise ValidationError(msg)
        if not {"x", "y", "z"}.issubset(names):
            msg = "Point clouds require x, y and z fields"
            raise ValidationError(msg)
        if any(field.count != 1 for field in self.fields if field.name in {"x", "y", "z"}):
            msg = "Coordinate fields must be scalar"
            raise ValidationError(msg)
        for field in self.fields:
            actual = self.data.dtype[field.name]
            base, shape = actual.subdtype or (actual, ())
            expected = np.dtype(field.dtype)
            if (base.kind, base.itemsize, shape) != (
                expected.kind,
                expected.itemsize,
                () if field.count == 1 else (field.count,),
            ):
                msg = "Point-cloud field dtypes and counts must match the structured array"
                raise ValidationError(msg)
        self.data.setflags(write=False)
        return self

    @property
    def xyz(self) -> NDArray[np.float64]:
        """Expose coordinates in a uniform floating-point computation array."""
        return np.column_stack([self.data[name] for name in ("x", "y", "z")]).astype(
            np.float64, copy=False
        )


class BoundingBox(BoundaryModel):
    """Describe finite coordinate coverage in source units."""

    min: tuple[float, float, float]
    max: tuple[float, float, float]


Sensor = Literal["unknown", "terrestrial", "vehicle_lidar", "depth_camera", "object"]


class SensorDefaults(BoundaryModel):
    """Plausible single-capture extent and point spacing for one sensor form."""

    max_extent: float
    max_relative_spacing: float
    sparse_penalized: bool


# Extents are in meters; relative spacing is the median nearest-neighbor
# distance divided by the main-body extent. The limits sit about four times
# above clean generated captures of each form (see docs/MEDIA_QUALITY.md).
SENSOR_DEFAULTS: dict[str, SensorDefaults] = {
    "unknown": SensorDefaults(max_extent=1000, max_relative_spacing=0.01, sparse_penalized=False),
    "terrestrial": SensorDefaults(
        max_extent=1000, max_relative_spacing=0.01, sparse_penalized=True
    ),
    "vehicle_lidar": SensorDefaults(
        max_extent=1000, max_relative_spacing=0.005, sparse_penalized=True
    ),
    "depth_camera": SensorDefaults(max_extent=50, max_relative_spacing=0.01, sparse_penalized=True),
    "object": SensorDefaults(max_extent=10, max_relative_spacing=0.01, sparse_penalized=True),
}


class PointCloudProbe(BoundaryModel):
    """Summarize format, finite geometry and actionable quality signals."""

    format: str
    encoding: str
    point_count: int
    fields: list[str]
    bounding_box: BoundingBox | None
    density: float
    nan_count: int
    inf_count: int
    invalid_count: int
    invalid_ratio: float
    outlier_ratio: float
    outlier_sample_count: int
    outlier_sampled: bool = False
    outlier_ci_low: float = 0.0
    outlier_ci_high: float = 0.0
    isolated_count: int = 0
    clustered_count: int = 0
    spacing: float = 0.0
    relative_spacing: float = 0.0
    spacing_limit: float = 0.0
    sparse_penalized: bool = False
    body_extent: float
    sensor: Sensor = "unknown"
    unit_suspected: bool
    unit_reason: str | None
    unit_hint: str | None = None


class StatisticalParams(Params):
    """Tune the local density ratio and the separated-cluster test.

    Defaults come from generated ray-cast scans with density gradients:
    indoor terrestrial, 16 to 64 line vehicle lidar, oblique depth cameras
    and a small structured-light part. With 12 neighbors and a ratio of 3 no
    clean scan had more than 0.04% of points flagged, while every scan with
    0.5% scattered outliers had at least 0.16% flagged. A small component
    has at least two linked points and fewer than max(50, 1% of the cloud).
    It is an outlier cluster when its spacing is more than 10 times that of
    the points its members neighbor, as with strays spread far around a
    scene, or when no other point lies within 5 times its link spacing. A
    group with no outside neighbors at all is compared with the main body
    instead, unless it is a piece of surface such as a far facade.
    Pieces of scanned surface, which are thin in some direction, must also
    be more than twice their own extent away, so ring segments and far wall
    patches stay. Sparse-cluster ratios of 9 to 30 gave identical results.
    """

    neighbors: int = Field(default=12, ge=2, le=64)
    local_ratio: float = Field(default=3.0, gt=1, le=100)
    link_ratio: float = Field(default=3.0, gt=1, le=100)
    cluster_gap: float = Field(default=5.0, gt=1, le=1000)
    min_cluster_points: int = Field(default=50, ge=2)
    min_cluster_fraction: float = Field(default=0.01, ge=0, le=0.5)
    sparse_cluster_ratio: float = Field(default=10.0, gt=1, le=1000)

    def statistics(self) -> "StatisticalParams":
        """Return only the fields that decide which points are outliers."""
        return StatisticalParams.model_validate(
            self.model_dump(include=set(StatisticalParams.model_fields))
        )


class ProbeParams(StatisticalParams):
    """Control statistical, sparse-coverage and unit-suspicion file-level policy.

    ``max_outlier_ratio`` defaults to 0.04%, near the geometric middle of
    the worst clean generated scan (0.029%, a sparse 32-ring street) and the
    least flagged generated scan with 0.5% embedded outliers (0.060%, a
    2.6-million-point drive of 24 frames). Sampled files are judged by the
    lower end of the 95% interval, so sampling error alone cannot raise an
    issue.
    """

    sensor: Sensor = "unknown"
    max_outlier_ratio: float = Field(default=0.0004, ge=0, le=1)
    max_relative_spacing: float | None = Field(default=None, gt=0)
    expected_max_extent: float | None = Field(default=None, gt=0)
    reference_extent: float | None = Field(default=None, gt=0)
    scale_ratio: float = Field(default=1000.0, gt=1)
    scale_tolerance: float = Field(default=2.0, gt=1)

    def max_extent(self) -> float:
        """Return the explicit or sensor-form plausible maximum extent."""
        return self.expected_max_extent or SENSOR_DEFAULTS[self.sensor].max_extent

    def spacing_limit(self) -> float:
        """Return the explicit or sensor-form maximum relative spacing."""
        return self.max_relative_spacing or SENSOR_DEFAULTS[self.sensor].max_relative_spacing

    def sparse_penalized(self) -> bool:
        """Penalize sparse coverage only for a declared sensor form or an explicit limit."""
        return (
            self.max_relative_spacing is not None or SENSOR_DEFAULTS[self.sensor].sparse_penalized
        )


class CleanParams(Params):
    """Remove invalid coordinates and optionally clip an inclusive source-unit box."""

    remove_invalid: bool = True
    min_bound: tuple[float, float, float] | None = None
    max_bound: tuple[float, float, float] | None = None

    @field_validator("min_bound", "max_bound", mode="before")
    @classmethod
    def json_bounds(cls, value: object) -> object:
        """Accept JSON arrays at the otherwise strict tuple parameter boundary."""
        return tuple(cast("list[object]", value)) if isinstance(value, list) else value

    @model_validator(mode="after")
    def bounds(self) -> "CleanParams":
        """Reject inverted coordinate bounds."""
        if (
            self.min_bound
            and self.max_bound
            and any(low > high for low, high in zip(self.min_bound, self.max_bound, strict=True))
        ):
            msg = "min_bound must not exceed max_bound"
            raise ValidationError(msg)
        return self


class DownsampleParams(Params):
    """Select the source-unit voxel size for stable first-point sampling."""

    voxel_size: float = Field(default=0.1, gt=0)


class OutlierParams(StatisticalParams):
    """Remove isolated points and separated small clusters with the probe's rule."""


class UnitCheckParams(Params):
    """Flag implausibly large extents without rewriting ambiguous coordinates."""

    expected_max_extent: float | None = Field(default=None, gt=0)
    reference_extent: float | None = Field(default=None, gt=0)
    scale_ratio: float = Field(default=1000.0, gt=1)
    scale_tolerance: float = Field(default=2.0, gt=1)


class PreviewParams(Params):
    """Bound a deterministic top-down PNG projection."""

    size: int = Field(default=512, ge=32, le=2048)
    color_by: Literal["height", "intensity"] = "height"
