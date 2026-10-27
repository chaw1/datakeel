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
    body_extent: float
    unit_suspected: bool
    unit_reason: str | None


class ProbeParams(Params):
    """Control statistical probe, sparse-coverage and unit-suspicion thresholds."""

    neighbors: int = Field(default=16, ge=1, le=64)
    distance_ratio: float = Field(default=4.0, gt=1, le=100)
    min_density: float = Field(default=1.0, ge=0)
    expected_max_extent: float = Field(default=1000.0, gt=0)
    reference_extent: float | None = Field(default=None, gt=0)
    scale_ratio: float = Field(default=1000.0, gt=1)
    scale_tolerance: float = Field(default=2.0, gt=1)


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


class OutlierParams(Params):
    """Reject points whose mean neighbor distance exceeds a multiple of the median."""

    neighbors: int = Field(default=16, ge=1, le=64)
    distance_ratio: float = Field(default=4.0, gt=1, le=100)


class UnitCheckParams(Params):
    """Flag implausibly large extents without rewriting ambiguous coordinates."""

    expected_max_extent: float = Field(default=1000.0, gt=0)
    reference_extent: float | None = Field(default=None, gt=0)
    scale_ratio: float = Field(default=1000.0, gt=1)
    scale_tolerance: float = Field(default=2.0, gt=1)


class PreviewParams(Params):
    """Bound a deterministic top-down PNG projection."""

    size: int = Field(default=512, ge=32, le=2048)
    color_by: Literal["height", "intensity"] = "height"
